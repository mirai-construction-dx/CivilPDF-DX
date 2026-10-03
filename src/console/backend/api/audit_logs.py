from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Optional
import math

from database import get_db
from models.user import User, UserRole
from models.audit_log import AuditLog
from auth.dependencies import get_current_user
from api.schemas import AuditLogResponse
from api.csv_export import (
    DEFAULT_CHUNK_ROWS,
    csv_stream_response,
    ensure_export_within_limit,
)
from services.audit_chain_service import create_chained_audit_log, verify_chain

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


def _require_admin(current_user: User) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.get("/", response_model=Any)
def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List audit logs (admin only).

    ``date_from`` / ``date_to`` use the same names and inclusive semantics as
    ``/audit-logs/export.csv`` (WEB-AUDIT-003 / AT-AUDIT-004).
    """
    _require_admin(current_user)

    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.filter(AuditLog.resource_id == resource_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if date_from is not None:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        q = q.filter(AuditLog.created_at <= date_to)

    total = q.count()
    logs = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = [AuditLogResponse.model_validate(log) for log in logs]

    # resource_id filter: return flat list for Editor polling compatibility
    if resource_id:
        return items

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/export.csv")
def export_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export (filtered) audit logs as CSV. Admin only; the export itself is audited.

    Audit logs accumulate for the whole retention period, so the export is
    streamed in bounded batches and refused (413) above ``MAX_EXPORT_ROWS``
    rather than silently truncated — a partial compliance export that looks
    complete is a worse failure than a clear error.
    """
    _require_admin(current_user)

    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.filter(AuditLog.resource_id == resource_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if date_from is not None:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        q = q.filter(AuditLog.created_at <= date_to)

    row_count = q.count()
    ensure_export_within_limit(row_count, label="監査ログ")

    logs = q.order_by(AuditLog.sequence_number.asc()).yield_per(DEFAULT_CHUNK_ROWS)
    headers = [
        "sequence_number",
        "created_at",
        "user_id",
        "action",
        "resource_type",
        "resource_id",
        "detail",
        "ip_address",
        "record_hash",
        "prev_hash",
    ]

    def rows():
        for log in logs:
            created_at = log.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            yield [
                log.sequence_number,
                created_at.isoformat() if created_at else "",
                log.user_id,
                log.action,
                log.resource_type,
                log.resource_id,
                log.detail,
                log.ip_address,
                log.record_hash,
                log.prev_hash,
            ]

    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="audit.exported",
        resource_type="audit_log",
        resource_id=None,
        detail=f"audit log CSV export ({row_count} rows)",
        ip_address=None,
    )
    return csv_stream_response(
        headers,
        rows(),
        f"audit-logs-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv",
    )


class ChainVerifyResponse(BaseModel):
    chain_valid: bool
    records_checked: int
    first_broken_sequence: Optional[int]
    error: Optional[str]
    # Added 2026-10: lets callers tell a full verification from a partial one.
    total_records: int
    complete: bool


@router.get(
    "/verify",
    response_model=ChainVerifyResponse,
    summary="監査ログ ハッシュチェーン検証 (NIS2/ISO 19650)",
    description=(
        "監査ログのハッシュチェーン整合性を検証します。"
        "既定では全レコードを検証します。limit を指定した場合は先頭から limit 件のみを"
        "検証し、complete=false（records_checked < total_records）になります。"
        "chain_valid=true かつ complete=true の場合に、記録済みの全ログについて"
        "改ざんが検出されなかったことを示します。"
    ),
)
def verify_audit_chain(
    limit: Optional[int] = Query(
        None,
        ge=1,
        description="検証するレコード数の上限（省略時は全件検証）",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    result = verify_chain(db, limit=limit)
    return ChainVerifyResponse(**result)
