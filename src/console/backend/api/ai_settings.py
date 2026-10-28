"""AI model settings API — admin-only configuration for Anthropic API key and model."""

import json

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services import ai_settings as ai_settings_service
from services.audit_chain_service import create_chained_audit_log

router = APIRouter(prefix="/ai-config", tags=["AI Settings"])


class AiConfig(BaseModel):
    model_name: str
    enabled: bool
    has_api_key: bool  # never return actual key


class AiConfigUpdate(BaseModel):
    model_name: Optional[str] = None
    api_key: Optional[str] = None  # write-only, never returned
    enabled: Optional[bool] = None


class AiConfigTestResult(BaseModel):
    ok: bool
    message: str
    model: Optional[str] = None


def _to_public(row) -> AiConfig:
    return AiConfig(
        model_name=row.model_name or "claude-haiku-4-5-20251001",
        enabled=bool(row.enabled),
        has_api_key=bool(row.api_key_enc),
    )


@router.get("", response_model=AiConfig)
def get_ai_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = ai_settings_service.get_ai_setting_row(db)
    return _to_public(row)


@router.put("", response_model=AiConfig)
def update_ai_config(
    body: AiConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        row = ai_settings_service.update_ai_setting(
            db,
            model_name=body.model_name,
            api_key=body.api_key,
            enabled=body.enabled,
            updated_by=current_user.id,
        )
    except ai_settings_service.AiSettingsError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    # Who turned AI on/off and who replaced the API key is exactly the audit
    # question this switch exists for; the key value itself is never recorded.
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="ai.config.updated",
        resource_type="ai_settings",
        resource_id="1",
        detail=json.dumps(
            {
                "model_name": row.model_name,
                "enabled": row.enabled,
                "api_key_changed": body.api_key is not None,
                "has_api_key": bool(row.api_key_enc),
            },
            ensure_ascii=False,
        ),
        ip_address=None,
    )
    db.commit()
    return _to_public(row)


@router.post("/test", response_model=AiConfigTestResult)
def test_ai_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Verify the Anthropic API key by making a minimal API call.

    Subject to the same environment gate as every other direct call
    (ADR-0007): refused with 503 in production / staging, before the key is
    read.
    """
    if not ai_settings_service.direct_call_allowed():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ai_settings_service.DIRECT_CALL_BLOCKED_DETAIL,
        )
    api_key = ai_settings_service.get_api_key(db)
    if not api_key:
        return AiConfigTestResult(
            ok=False,
            message="APIキーが設定されていません。APIキーを入力して保存してください。",
        )

    if anthropic is None:
        return AiConfigTestResult(
            ok=False,
            message="anthropic パッケージがインストールされていません。",
        )

    try:
        row = ai_settings_service.get_ai_setting_row(db)
        model = row.model_name or "claude-haiku-4-5-20251001"

        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        return AiConfigTestResult(
            ok=True,
            message=f"接続成功。モデル: {model}",
            model=model,
        )
    except Exception as exc:
        return AiConfigTestResult(
            ok=False,
            message=f"接続失敗: {exc}",
        )
