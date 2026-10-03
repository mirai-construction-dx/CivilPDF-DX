"""Hash chain service for tamper-evident audit logs.

Implements a blockchain-inspired hash chain where each AuditLog record
contains the SHA-256 hash of the previous record, creating a chain that
makes tampering detectable.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from services.request_context import current_client_ip

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64  # sentinel for first record in chain


def _normalize_dt(dt: Optional[datetime]) -> str:
    """Return canonical UTC ISO-8601 string for hashing, regardless of DB storage format."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _compute_record_hash(
    prev_hash: str,
    sequence_number: int,
    user_id: Optional[str],
    action: str,
    resource_type: Optional[str],
    resource_id: Optional[str],
    detail: Optional[str],
    ip_address: Optional[str],
    created_at_iso: str,
) -> str:
    """Compute SHA-256 over chain-relevant fields."""
    data = json.dumps(
        {
            "prev_hash": prev_hash,
            "seq": sequence_number,
            "user_id": user_id or "",
            "action": action,
            "resource_type": resource_type or "",
            "resource_id": resource_id or "",
            "detail": detail or "",
            "ip_address": ip_address or "",
            "created_at": created_at_iso,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(data).hexdigest()


# Arbitrary fixed key for pg_advisory_xact_lock: serializes all audit-chain
# appends on PostgreSQL ("CIVLAUDT" as ASCII, fits in a signed 64-bit int).
_AUDIT_CHAIN_LOCK_KEY = 0x4349564C41554454


def _serialize_chain_appends(db: Session) -> None:
    """Serialize audit-chain appends across sessions (PostgreSQL only).

    SELECT ... FOR UPDATE on the last row is not enough under READ COMMITTED:
    a waiter that gets the lock re-checks the *old* last row and computes the
    same next sequence_number, so N concurrent appends cost up to N-1 retries.
    Viewing a document is an append since 2026-10-03 (document.viewed), which
    makes that contention common. A transaction-scoped advisory lock taken
    *before* reading the last row means each appender reads the committed tip.
    The lock is released at the end of the caller's transaction (commit or
    rollback). SQLite (tests, MVP) serializes writes itself; nothing to do.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _AUDIT_CHAIN_LOCK_KEY},
        )


def get_last_record(db: Session, *, for_update: bool = False) -> Optional[AuditLog]:
    """Return the most recent AuditLog by sequence_number.

    for_update=True takes a row lock (SELECT ... FOR UPDATE) so concurrent
    callers serialize on the same row instead of both computing the same
    next sequence_number. On backends without row-level locking (SQLite,
    used in tests) this is a no-op; the UNIQUE constraint on
    sequence_number (migration m3n4o5p6q7r8) is the backstop there and for
    the case where the table is empty and there is no row to lock yet.
    """
    q = db.query(AuditLog).filter(AuditLog.sequence_number != None)  # noqa: E711
    if for_update:
        q = q.with_for_update()
    return q.order_by(AuditLog.sequence_number.desc()).first()


def create_chained_audit_log(
    db: Session,
    *,
    user_id: Optional[str],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    _retries: int = 3,
) -> AuditLog:
    """Create a new AuditLog record with hash chain linkage.

    Retries up to _retries times on a UNIQUE-constraint collision on
    sequence_number, which can only happen when two callers raced to insert
    the first record (no row to lock via for_update) or against a legacy
    row inserted before migration m3n4o5p6q7r8. See
    services/audit_chain_service.py module docstring / that migration's
    docstring for the full race description.

    A collision is recovered via a SAVEPOINT (db.begin_nested()) rather than
    db.rollback(), so only this function's own insert is undone — any
    changes the caller already made on the same session (e.g. the resource
    this audit entry is about, if not yet committed) survive the retry.
    """
    if ip_address is None:
        # Routers that never see the Request pass ip_address=None; use the IP
        # AuditMiddleware stored for the current HTTP request (requirements
        # §5.4). Outside a request (scheduled jobs) this stays None.
        ip_address = current_client_ip()

    for attempt in range(_retries):
        _serialize_chain_appends(db)
        last = get_last_record(db, for_update=True)
        prev_hash = last.record_hash if (last and last.record_hash) else GENESIS_HASH
        next_seq = (
            (last.sequence_number + 1)
            if (last and last.sequence_number is not None)
            else 1
        )

        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
            sequence_number=next_seq,
            prev_hash=prev_hash,
            record_hash="pending",  # placeholder; replaced below after DB assigns created_at
        )
        try:
            with db.begin_nested():
                db.add(log)
                db.flush()  # DB assigns created_at via server_default
        except IntegrityError:
            if attempt == _retries - 1:
                raise
            logger.warning(
                "audit_chain: sequence_number %s collided, retrying (attempt %s/%s)",
                next_seq,
                attempt + 1,
                _retries,
            )
            continue
        db.refresh(log)  # reload to get the actual DB-stored created_at

        # Compute hash using the exact created_at value stored in DB
        record_hash = _compute_record_hash(
            prev_hash=prev_hash,
            sequence_number=next_seq,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
            created_at_iso=_normalize_dt(log.created_at),
        )
        log.record_hash = record_hash
        db.commit()
        db.refresh(log)
        return log

    raise RuntimeError("unreachable")  # loop always returns or raises


VERIFY_BATCH_SIZE = 1000

_CHAIN_COLUMNS = (
    AuditLog.sequence_number,
    AuditLog.prev_hash,
    AuditLog.record_hash,
    AuditLog.user_id,
    AuditLog.action,
    AuditLog.resource_type,
    AuditLog.resource_id,
    AuditLog.detail,
    AuditLog.ip_address,
    AuditLog.created_at,
)


def verify_chain(db: Session, limit: Optional[int] = None) -> dict:
    """Verify the integrity of the hash chain.

    Args:
        db: SQLAlchemy session.
        limit: Verify only the first ``limit`` records (by sequence_number).
            ``None`` (default) verifies the whole chain. Records are read in
            batches of ``VERIFY_BATCH_SIZE`` so a long chain is not loaded at
            once. Previously the default silently stopped after 1,000 records
            and still reported ``chain_valid=True``, so tampering beyond that
            point was never detected.

    Returns:
    - chain_valid: bool — no break found in the records checked
    - records_checked: int
    - first_broken_sequence: int | None
    - error: str | None
    - total_records: int — chained records counted when the call began
    - complete: bool — True when every record counted at the start of the
      call was checked (a ``chain_valid`` of a partial check says nothing
      about later records). Records appended concurrently while the check is
      running are outside that snapshot and are not verified by this call;
      run the check again to cover them.
    """
    total = (
        db.query(AuditLog)
        .filter(AuditLog.sequence_number != None)  # noqa: E711
        .count()
    )
    target = total if limit is None else min(limit, total)

    def _result(valid: bool, checked: int, broken, error) -> dict:
        return {
            "chain_valid": valid,
            "records_checked": checked,
            "first_broken_sequence": broken,
            "error": error,
            "total_records": total,
            "complete": checked >= total,
        }

    prev_hash = GENESIS_HASH
    checked = 0
    last_seq: Optional[int] = None
    while checked < target:
        # Column tuples (not ORM entities): nothing is added to the session's
        # identity map, so memory stays bounded on long chains and objects the
        # caller already holds are left untouched.
        q = db.query(*_CHAIN_COLUMNS).filter(
            AuditLog.sequence_number != None  # noqa: E711
        )
        if last_seq is not None:
            q = q.filter(AuditLog.sequence_number > last_seq)
        batch = (
            q.order_by(AuditLog.sequence_number.asc())
            .limit(min(VERIFY_BATCH_SIZE, target - checked))
            .all()
        )
        if not batch:
            break
        for record in batch:
            if record.prev_hash != prev_hash:
                return _result(
                    False,
                    checked + 1,
                    record.sequence_number,
                    f"prev_hash mismatch at sequence {record.sequence_number}",
                )

            expected_hash = _compute_record_hash(
                prev_hash=record.prev_hash or GENESIS_HASH,
                sequence_number=record.sequence_number,
                user_id=record.user_id,
                action=record.action,
                resource_type=record.resource_type,
                resource_id=record.resource_id,
                detail=record.detail,
                ip_address=record.ip_address,
                created_at_iso=_normalize_dt(record.created_at),
            )
            if record.record_hash != expected_hash:
                return _result(
                    False,
                    checked + 1,
                    record.sequence_number,
                    f"record_hash tampered at sequence {record.sequence_number}",
                )

            prev_hash = record.record_hash
            checked += 1
            last_seq = record.sequence_number

    return _result(True, checked, None, None)
