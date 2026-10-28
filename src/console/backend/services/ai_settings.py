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


def _read_setting_row(db: Session) -> AiSetting | None:
    """Read-only lookup for request paths (search, AI calls).

    Unlike get_ai_setting_row it never inserts, and on any DB error it rolls
    the session back so the caller's later queries still work (a failed
    statement would otherwise leave the transaction aborted and turn an
    unrelated search into a 500).
    """
    try:
        return db.query(AiSetting).filter(AiSetting.id == 1).first()
    except Exception:
        db.rollback()
        return None


# 直接呼び出しを許可しうる実行環境（許可リスト）。これ以外の値 — production・
# staging・空・未知の値 — はすべて本番相当として扱い、拒否する（fail closed）。
_DIRECT_CALL_ENVIRONMENTS = frozenset({"development", "test", "local"})

DIRECT_CALL_BLOCKED_DETAIL = (
    "この実行環境では AI Provider の直接呼び出しは無効です（ADR-0007）"
)


def direct_call_allowed(cfg=None) -> bool:
    """Single gate for every direct AI Provider call (ADR-0007).

    Allowed only when the explicit flag ``AI_DIRECT_CALL_ALLOWED`` is true
    *and* ``ENVIRONMENT`` is a non-production value on the allow-list.
    Production, staging and any unknown/empty environment are refused even
    with the flag set. Any error while reading the configuration also refuses.
    This is checked before the admin kill switch, the API key and the
    document text, and it is independent of both.
    """
    try:
        cfg = cfg or settings
        if cfg.ai_direct_call_allowed is not True:
            return False
        environment = str(cfg.environment or "").strip().lower()
        return environment in _DIRECT_CALL_ENVIRONMENTS
    except Exception:
        return False


def is_ai_enabled(db: Session) -> bool:
    """Admin kill switch: AI calls are allowed only when explicitly enabled.

    Fail closed — a missing/unreadable settings row counts as disabled, so a
    configured API key alone never turns AI on.
    """
    row = _read_setting_row(db)
    return bool(row is not None and row.enabled)


def get_model_name(db: Session, default: str) -> str:
    """Return the configured model name, falling back to ``default``."""
    row = _read_setting_row(db)
    if row is not None and row.model_name:
        return row.model_name
    return default


def get_api_key(db: Session) -> str:
    """Return decrypted API key: DB row first, then env var fallback."""
    row = _read_setting_row(db)
    if row is not None and row.api_key_enc:
        key = decrypt_key(row.api_key_enc)
        if key:
            return key
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
