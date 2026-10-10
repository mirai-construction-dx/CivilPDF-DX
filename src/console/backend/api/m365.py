"""Microsoft 365 integration — admin config + Graph lookup, backed by m365_settings.

Replaces the prior in-memory stub. Persists tenant/client_id and the Fernet
ciphertext of client_secret (never returned by the API). Provides a
test-connection probe and a Graph user lookup.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services import m365 as m365_service
from services.audit_chain_service import create_chained_audit_log

router = APIRouter(prefix="/m365", tags=["M365"])


class M365Config(BaseModel):
    tenant_id: str
    client_id: str
    enabled: bool
    auto_provision: bool
    default_role: str
    has_client_secret: bool


class M365ConfigUpdate(BaseModel):
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None  # write-only, never returned
    enabled: Optional[bool] = None
    auto_provision: Optional[bool] = None
    default_role: Optional[str] = None


def _to_public(row) -> M365Config:
    return M365Config(
        tenant_id=row.tenant_id or "",
        client_id=row.client_id or "",
        enabled=bool(row.enabled),
        auto_provision=bool(row.auto_provision),
        default_role=row.default_role or "viewer",
        has_client_secret=bool(row.client_secret_enc),
    )


@router.get("/config", response_model=M365Config)
def get_m365_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = m365_service.get_settings_row(db)
    return _to_public(row)


@router.put("/config", response_model=M365Config)
def update_m365_config(
    body: M365ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = m365_service.update_settings(
        db,
        tenant_id=body.tenant_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        enabled=body.enabled,
        auto_provision=body.auto_provision,
        default_role=body.default_role,
        updated_by=current_user.id,
    )
    # Credential/tenant changes decide which Microsoft identity can sign in;
    # record who changed them (the secret value is never recorded).
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="m365.config.updated",
        resource_type="m365_settings",
        resource_id="1",
        detail=json.dumps(
            {
                "tenant_id": row.tenant_id,
                "client_id": row.client_id,
                "enabled": row.enabled,
                "auto_provision": row.auto_provision,
                "default_role": row.default_role,
                "client_secret_changed": body.client_secret is not None,
                "has_client_secret": bool(row.client_secret_enc),
            },
            ensure_ascii=False,
        ),
        ip_address=None,
    )
    db.commit()
    return _to_public(row)


@router.post("/test-connection")
def test_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = m365_service.test_connection(db)
    if not result.get("ok"):
        stage = result.get("stage", "unknown")
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if stage == "config"
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=http_status, detail=result)
    return result


@router.get("/users/lookup")
def lookup_m365_user(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return m365_service.lookup_user(db, email)
    except m365_service.M365ConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except m365_service.M365UserNotFound:
        return {"email": email, "exists": False}
    except m365_service.M365AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
