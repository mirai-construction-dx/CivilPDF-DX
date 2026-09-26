from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json
import os

# Cross-platform default: <user home>/civildx/uploads
# Override with UPLOAD_DIR env var or .env file.
_DEFAULT_UPLOAD_DIR = str(Path.home() / "civildx" / "uploads")


class Settings(BaseSettings):
    # extra="ignore": .env is shared with docker-compose (POSTGRES_DB,
    # FRONTEND_PORT, UVICORN_WORKERS, etc.) and Settings should not fail to
    # load just because compose-only keys are present alongside app keys.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CivilPDF-DX"
    app_version: str = "0.10.0"
    debug: bool = False

    # MVP 公開デモ用のログイン認証バイパス。true のとき、トークン無しの
    # リクエストをデモ用の管理ユーザーとして扱う（＝ログイン画面を出さない）。
    # 既定は False で、環境変数 AUTH_BYPASS=true を明示した環境でのみ有効。
    # 本番構成 (docker-compose.prod.yml) では設定しないこと。
    auth_bypass: bool = False

    # Development default: SQLite (cross-platform, zero config)
    # Production: set DATABASE_URL=postgresql://... in .env
    database_url: str = "sqlite:///./civilpdf_dev.db"
    redis_url: str = "redis://localhost:6379/0"

    # Seconds to wait for a PostgreSQL connection before failing. Keeps
    # /health/ready and DB-backed requests bounded when the database is
    # unreachable instead of hanging until the client gives up.
    db_connect_timeout_seconds: int = 5

    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # M365 login bridge: only trust X-Forwarded-For when the app runs behind a
    # reverse proxy that strips client-supplied headers (e.g. Cloudflare Tunnel).
    trust_proxy_headers: bool = False

    timestamp_hmac_key: str = "change-me-in-production"

    # Entra ID / OpenID Connect SSO (Phase 1)
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_discovery_url: str = ""
    oidc_redirect_uri: str = ""
    oidc_scope: str = "openid profile email"
    oidc_auto_provision: bool = True
    # Origin of the SPA that receives the callback tokens (e.g. https://civilpdf.mirai-dx-platform.com)
    frontend_origin: str = ""

    cors_origins: str = (
        '["http://localhost:5173","http://localhost:3000",'
        '"tauri://localhost","http://tauri.localhost"]'
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    upload_dir: str = _DEFAULT_UPLOAD_DIR
    max_file_size_mb: int = 100

    anthropic_api_key: str = ""

    # Microsoft 365 integration — Fernet key for client_secret encryption.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    m365_fernet_key: str = ""


settings = Settings()


def validate_production_settings(cfg: Settings | None = None) -> None:
    """Fail fast when production-critical secrets still use insecure defaults.

    Called from the FastAPI lifespan when DEBUG=false. Without this guard a
    misconfigured deployment silently runs with forgeable JWT/HMAC keys.
    """
    cfg = cfg or settings
    insecure_defaults = {
        "change-this-in-production",
        "change-me-in-production",
        "change-this-to-a-secure-random-string-in-production",
        "",
    }
    if cfg.secret_key in insecure_defaults:
        raise RuntimeError(
            "SECRET_KEY must be set to a strong random value in production "
            "(generate with: openssl rand -hex 32)"
        )
    hmac_key = cfg.timestamp_hmac_key or os.environ.get(
        "TIMESTAMP_HMAC_KEY", "change-me-in-production"
    )
    if hmac_key in insecure_defaults:
        raise RuntimeError(
            "TIMESTAMP_HMAC_KEY must be set to a strong random value in production "
            "(generate with: openssl rand -hex 32). It protects the timestamp "
            "fallback used when TSA_URL is not configured."
        )
