from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from sqlalchemy import text

from config import settings, validate_production_settings
from database import engine, Base
from api import (
    apps_router,
    electronic_delivery_router,
    organizations_router,
    auth_router,
    users_router,
    documents_router,
    workflows_router,
    projects_router,
    audit_logs_router,
    stats_router,
    m365_router,
    ocr_router,
    privacy_router,
    ai_router,
    ai_settings_router,
    search_router,
    editor_router,
    revisions_router,
    notifications_router,
)
from middleware import AuditMiddleware, DxSyncMetricsMiddleware
from middleware.security import SecurityHeadersMiddleware
from middleware.rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.debug:
        validate_production_settings(settings)

    # Create tables on startup (dev convenience; Alembic owns the schema in any
    # deployed environment — civilpdf-backend.service runs `alembic upgrade head`
    # in ExecStartPre). A database outage must NOT stop the process from
    # starting: refusing to boot turns a recoverable outage into a crash loop
    # and hides the cause, whereas starting and answering 503 on /health/ready
    # makes the outage visible to monitoring. Observed on 2026-09-18, when an
    # invalid PostgreSQL credential made every connection attempt fail.
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as exc:  # noqa: BLE001 — startup must survive a DB outage
        logger.error(
            "Database not reachable at startup (%s). Serving anyway; "
            "/health/ready will report 503 until the database recovers.",
            exc,
        )

    if settings.debug:
        # Ensure the dev-bypass admin exists so unauthenticated requests work.
        from database import SessionLocal
        from auth.dependencies import _get_or_create_dev_user

        db = SessionLocal()
        try:
            _get_or_create_dev_user(db)
            logger.warning(
                "⚠️  DEV AUTH BYPASS ACTIVE — all unauthenticated requests run as dev-admin. "
                "Set DEBUG=false in production."
            )
        finally:
            db.close()

    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="建設業特化PDFプラットフォーム 管理コンソール API",
    lifespan=lifespan,
)

# Rate limiter is registered first so it runs innermost: its 429 responses
# still traverse the security-header and audit layers on the way out.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(DxSyncMetricsMiddleware)
app.add_middleware(AuditMiddleware)

# API routes
API_PREFIX = "/api/v1"
app.include_router(apps_router, prefix=API_PREFIX)
app.include_router(electronic_delivery_router, prefix=API_PREFIX)
app.include_router(organizations_router, prefix=API_PREFIX)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(documents_router, prefix=API_PREFIX)
app.include_router(workflows_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(audit_logs_router, prefix=API_PREFIX)
app.include_router(stats_router, prefix=API_PREFIX)
app.include_router(m365_router, prefix=API_PREFIX)
app.include_router(ocr_router, prefix=API_PREFIX)
app.include_router(privacy_router, prefix=API_PREFIX)
app.include_router(ai_router, prefix=API_PREFIX)
app.include_router(ai_settings_router, prefix=API_PREFIX)
app.include_router(search_router, prefix=API_PREFIX)
app.include_router(editor_router, prefix=API_PREFIX)
app.include_router(revisions_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)


@app.get("/health")
def health_check():
    """Liveness probe. Deliberately does not touch the database.

    Use ``/health/ready`` to decide whether the service can actually serve
    requests.
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/health/ready")
def readiness_check():
    """Readiness probe: verifies the database answers before reporting healthy.

    A database outage used to be invisible to monitoring, because ``/health``
    only reports that the process is running. That let production serve HTTP 500
    for every database-backed request for three weeks while the health check
    stayed green. This probe fails (503) whenever the database is unreachable.
    """
    started = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready"
        logger.error("Readiness check failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {
        "status": "ok",
        "database": engine.dialect.name,
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
    }


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.app_name} API",
        "docs": "/docs",
        "health": "/health",
    }
