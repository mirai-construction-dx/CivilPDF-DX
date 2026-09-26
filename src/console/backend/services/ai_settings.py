"""AI settings service — Fernet-encrypted API key storage and retrieval."""

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from config import settings
from models.ai_setting import AiSetting


class AiSettingsError(Exception):
    pass


def _fernet() -> Fernet:
    key = settings.m365_fernet_key
    if not key:
        raise AiSettingsError(
            "M365_FERNET_KEY is not configured (used for AI key encryption)"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_key(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def get_ai_setting_row(db: Session) -> AiSetting:
    """Return the singleton AI settings row, creating it if absent."""
    row = db.query(AiSetting).filter(AiSetting.id == 1).first()
    if row is None:
        row = AiSetting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def is_ai_enabled(db: Session) -> bool:
    """Admin kill switch: AI calls are allowed only when explicitly enabled.

    Fail closed — a missing/unreadable settings row counts as disabled, so a
    configured API key alone never turns AI on.
    """
    try:
        return bool(get_ai_setting_row(db).enabled)
    except Exception:
        return False


def get_model_name(db: Session, default: str) -> str:
    """Return the configured model name, falling back to ``default``."""
    try:
        row = get_ai_setting_row(db)
        if row.model_name:
            return row.model_name
    except Exception:
        pass
    return default


def get_api_key(db: Session) -> str:
    """Return decrypted API key: DB row first, then env var fallback."""
    try:
        row = get_ai_setting_row(db)
        if row.api_key_enc:
            key = decrypt_key(row.api_key_enc)
            if key:
                return key
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "") or settings.anthropic_api_key


def update_ai_setting(
    db: Session,
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
    updated_by: str | None = None,
) -> AiSetting:
    row = get_ai_setting_row(db)
    if model_name is not None:
        row.model_name = model_name
    if api_key is not None:
        row.api_key_enc = encrypt_key(api_key) if api_key else ""
    if enabled is not None:
        row.enabled = enabled
    if updated_by is not None:
        row.updated_by = updated_by
    db.commit()
    db.refresh(row)
    return row
