"""Physical deletion background job — GDPR Art.17 / 電子帳簿保存法.

Scans documents flagged with deletion_requested_at older than the grace period
and permanently removes the file from disk plus soft-deletes the DB record.
Audit logs are intentionally preserved (法的証跡保持義務).

Usage:
  Run via Celery: `celery -A services.deletion_job worker --loglevel=info`
  Or call `run_deletion_job(db)` directly from a scheduled endpoint / cron.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.document import Document
from services.audit_chain_service import create_chained_audit_log

logger = logging.getLogger(__name__)

DEFAULT_GRACE_DAYS = 30  # configurable; 30-day cooling-off period

# Grace-period days are counted on the Japanese calendar (業務上の日付基準は JST).
JST = timezone(timedelta(hours=9), "JST")

PHYSICAL_DELETION_ACTION = "gdpr_physical_deletion"


def deletion_cutoff(now: datetime, grace_days: int) -> datetime:
    """Return the exclusive UTC cutoff for "grace_days 経過後" in JST calendar days.

    A document whose deletion was requested on JST date ``D`` becomes eligible
    on JST date ``D + grace_days`` (the 30th day is included), from 00:00 JST,
    regardless of the time of day of the request. Eligible means
    ``deletion_requested_at < cutoff`` where ``cutoff`` is 00:00 JST of
    ``today_jst - grace_days + 1``.

    Example (grace_days=30): requested 2026-01-30 23:59 JST → kept through
    2026-02-28 (29日目), deleted from 2026-03-01 00:00 JST (30日目).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today_jst: date = now.astimezone(JST).date()
    first_kept_day = today_jst - timedelta(days=grace_days - 1)
    return datetime.combine(first_kept_day, time(0, 0), tzinfo=JST).astimezone(
        timezone.utc
    )


def run_deletion_job(
    db: Session,
    grace_days: int = DEFAULT_GRACE_DAYS,
    *,
    dry_run: bool = False,
    now: Optional[datetime] = None,
) -> dict:
    """Execute one pass of the physical deletion job.

    Args:
        db: SQLAlchemy session.
        grace_days: Days after deletion_requested_at before physical deletion,
            counted in JST calendar days with the grace_days-th day included
            (see :func:`deletion_cutoff`).
        dry_run: When True, only report what would be deleted; nothing is
            removed from disk or changed in the database.
        now: Reference time (tests / reproducible runs). Defaults to the
            current time.

    The pass is idempotent: a document that already has a
    ``gdpr_physical_deletion`` entry in the audit chain is not processed again,
    so re-running the job neither rewrites ``archived_at`` nor duplicates the
    audit record. (Previously every run re-processed every past-grace
    document, because ``deletion_requested_at`` stays set after erasure.)

    Returns:
        dict with counts: processed, deleted_files, errors.
    """
    reference = now or datetime.now(timezone.utc)
    cutoff = deletion_cutoff(reference, grace_days)

    already_deleted = db.query(AuditLog.resource_id).filter(
        AuditLog.action == PHYSICAL_DELETION_ACTION,
        AuditLog.resource_type == "document",
        AuditLog.resource_id.isnot(None),
    )
    candidates = (
        db.query(Document)
        .filter(
            Document.deletion_requested_at != None,  # noqa: E711
            Document.deletion_requested_at < cutoff,
            Document.id.notin_(already_deleted),
        )
        .order_by(Document.deletion_requested_at.asc(), Document.id.asc())
        .all()
    )

    if dry_run:
        logger.info(
            "Deletion job dry-run: %d candidate(s) past %d-day grace",
            len(candidates),
            grace_days,
        )
        return {
            "processed": len(candidates),
            "deleted_files": 0,
            "errors": 0,
            "grace_days": grace_days,
            "dry_run": True,
            "candidate_ids": [doc.id for doc in candidates],
            "run_at": datetime.now(timezone.utc).isoformat(),
        }

    deleted_files = 0
    errors = 0

    for doc in candidates:
        try:
            _physically_delete(db, doc)
            deleted_files += 1
        except Exception as exc:
            logger.error("Failed to delete document %s: %s", doc.id, exc, exc_info=True)
            errors += 1

    logger.info(
        "Deletion job complete: processed=%d deleted=%d errors=%d grace_days=%d",
        len(candidates),
        deleted_files,
        errors,
        grace_days,
    )
    return {
        "processed": len(candidates),
        "deleted_files": deleted_files,
        "errors": errors,
        "grace_days": grace_days,
        "dry_run": False,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


def _physically_delete(db: Session, doc: Document) -> None:
    """Remove file from disk and mark document as deleted in DB."""
    doc_id = doc.id
    file_path: Optional[str] = doc.file_path

    # Remove file from disk
    if file_path:
        p = Path(file_path)
        if p.exists():
            p.unlink()
            logger.info("Deleted file from disk: %s", file_path)
        else:
            logger.warning("File not found on disk (already removed?): %s", file_path)

    # Null out personal data fields — retain record skeleton for audit linkage
    doc.file_path = None  # type: ignore[assignment]
    doc.ocr_text = None
    doc.extra_data = {}
    doc.is_archived = True
    doc.archived_at = datetime.now(timezone.utc)

    db.commit()

    # Immutable audit trail entry (not deleted even after GDPR erasure)
    create_chained_audit_log(
        db,
        user_id=None,  # system job, no user actor
        action=PHYSICAL_DELETION_ACTION,
        resource_type="document",
        resource_id=doc_id,
        detail="physical deletion executed after grace period; file_path nulled",
        ip_address=None,
    )
    logger.info("Physical deletion complete for document %s", doc_id)
