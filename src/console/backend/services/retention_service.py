"""Retention policy service — enforces document retention rules."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.document import Document, DocumentType, DocumentStatus
from models.retention_policy import RetentionPolicy, DEFAULT_POLICIES

logger = logging.getLogger(__name__)

# Default retention years by document type when no specific policy is found.
# Counted from the upload date (Document.created_at). Contract and drawing
# follow decision B-2 (2026-10-03) and match DEFAULT_POLICIES; the other types
# are not yet decided and keep their earlier values.
_DEFAULT_RETENTION_MAP: dict[str, int] = {
    DocumentType.CONTRACT.value: 7,
    DocumentType.INSPECTION.value: 10,
    DocumentType.DRAWING.value: 10,
    DocumentType.SAFETY.value: 3,
    DocumentType.REPORT.value: 7,
    DocumentType.PHOTO.value: 5,
    DocumentType.CORRECTION.value: 3,
    DocumentType.OTHER.value: 7,
}


def get_policy_for_document(
    db: Session, document_type: str
) -> Optional[RetentionPolicy]:
    """Return the first RetentionPolicy matching the document type."""
    return (
        db.query(RetentionPolicy)
        .filter(RetentionPolicy.document_type == document_type)
        .first()
    )


def calculate_expiry(
    created_at: datetime,
    retention_years: int,
    is_permanent: bool = False,
) -> Optional[datetime]:
    """Return the expiry datetime, or None if permanent.

    Retention years are calendar years: the expiry is the same month/day/time
    ``retention_years`` years after ``created_at`` (2025-04-01 + 7 years →
    2032-04-01). Previously ``retention_years * 365`` days was used, which ended
    retention one day early for every leap day crossed (2025-04-01 + 7 years
    → 2032-03-30).

    Leap day: when ``created_at`` is 29 February and the target year has no
    29 February, the expiry is moved forward to 1 March of the target year
    (same time of day), so the retention period is never shorter than
    ``retention_years`` calendar years (2024-02-29 + 7 years → 2031-03-01).
    """
    if is_permanent or retention_years < 0:
        return None
    if retention_years == 0:
        # Immediate purpose — expires at creation (delete as soon as purpose is met)
        return created_at
    target_year = created_at.year + retention_years
    try:
        return created_at.replace(year=target_year)
    except ValueError:  # 29 Feb → non-leap target year
        return created_at.replace(year=target_year, month=3, day=1)


def apply_retention_policy(db: Session, doc: Document) -> None:
    """Attach a retention policy to a document and compute its expiry date."""
    policy = get_policy_for_document(
        db,
        doc.document_type.value
        if hasattr(doc.document_type, "value")
        else doc.document_type,
    )

    if policy:
        doc.retention_policy_id = policy.id
        doc.retention_expires_at = calculate_expiry(
            doc.created_at or datetime.now(timezone.utc),
            policy.retention_years,
            policy.is_permanent,
        )
    else:
        # Fallback to default map
        years = _DEFAULT_RETENTION_MAP.get(
            doc.document_type.value
            if hasattr(doc.document_type, "value")
            else str(doc.document_type),
            7,
        )
        doc.retention_expires_at = calculate_expiry(
            doc.created_at or datetime.now(timezone.utc),
            years,
        )


def get_expired_documents(db: Session) -> list[Document]:
    """Return documents whose retention period has expired and are not yet archived."""
    now = datetime.now(timezone.utc)
    return (
        db.query(Document)
        .filter(
            Document.retention_expires_at <= now,
            Document.is_archived == False,  # noqa: E712
            Document.deletion_requested_at == None,  # noqa: E711
        )
        .all()
    )


def archive_expired_documents(db: Session, *, dry_run: bool = False) -> int:
    """Archive all documents past their retention expiry. Returns count archived.

    With ``dry_run=True`` the matching documents are counted but nothing is
    written, which is what the scheduled retention job uses to report intent
    before it is allowed to mutate the database.
    """
    expired = get_expired_documents(db)
    if dry_run:
        logger.info(
            "Retention dry-run: %d document(s) past retention expiry", len(expired)
        )
        return len(expired)

    now = datetime.now(timezone.utc)
    for doc in expired:
        doc.is_archived = True
        doc.archived_at = now
        doc.status = DocumentStatus.ARCHIVED
        logger.info(
            "Document %s archived — retention expired at %s",
            doc.id,
            doc.retention_expires_at,
        )
    db.commit()
    return len(expired)


def run_retention_cycle(
    db: Session,
    *,
    grace_days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Run one full retention pass: seed policies, archive expiries, purge deletions.

    This is the entry point the scheduled job (``scripts/retention-job.py``)
    calls. Auditing that the code *can* enforce retention is not the same as
    retention actually happening, so the pass is packaged here where it can be
    tested and scheduled, rather than only reachable through admin HTTP calls.

    Args:
        db: SQLAlchemy session.
        grace_days: Cooling-off period after a deletion request before the file
            is physically removed (GDPR Art.17 / 電子帳簿保存法).
        dry_run: Report what would change without writing anything.

    Returns:
        JSON-serialisable summary of the pass.
    """
    from services.deletion_job import run_deletion_job

    started_at = datetime.now(timezone.utc)

    seeded = 0 if dry_run else seed_default_policies(db)
    archived = archive_expired_documents(db, dry_run=dry_run)
    deletion = run_deletion_job(db, grace_days=grace_days, dry_run=dry_run)

    summary = {
        "dry_run": dry_run,
        "grace_days": grace_days,
        "seeded_policies": seeded,
        "expired_documents": archived,
        "deletion_processed": deletion["processed"],
        "deletion_deleted_files": deletion["deleted_files"],
        "deletion_errors": deletion["errors"],
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Retention cycle %s", summary)
    return summary


def seed_default_policies(db: Session) -> int:
    """Seed DEFAULT_POLICIES if the table is empty. Returns count inserted."""
    existing = db.query(RetentionPolicy).count()
    if existing > 0:
        return 0
    for policy_data in DEFAULT_POLICIES:
        policy = RetentionPolicy(**policy_data)
        db.add(policy)
    db.commit()
    logger.info("Seeded %d default retention policies", len(DEFAULT_POLICIES))
    return len(DEFAULT_POLICIES)
