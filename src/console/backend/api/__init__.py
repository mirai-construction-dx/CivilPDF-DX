from api.apps import router as apps_router
from api.electronic_delivery import router as electronic_delivery_router
from api.organizations import router as organizations_router
from api.auth import router as auth_router
from api.users import router as users_router
from api.documents import router as documents_router
from api.workflows import router as workflows_router
from api.projects import router as projects_router
from api.audit_logs import router as audit_logs_router
from api.stats import router as stats_router
from api.m365 import router as m365_router
from api.ocr import router as ocr_router
from api.privacy import router as privacy_router
from api.ai import router as ai_router
from api.ai_settings import router as ai_settings_router
from api.search import router as search_router
from api.editor import router as editor_router
from api.revisions import router as revisions_router
from api.notifications import router as notifications_router
from api.integration import router as integration_router

__all__ = [
    "apps_router",
    "electronic_delivery_router",
    "organizations_router",
    "auth_router",
    "users_router",
    "documents_router",
    "workflows_router",
    "projects_router",
    "audit_logs_router",
    "stats_router",
    "m365_router",
    "ocr_router",
    "privacy_router",
    "ai_router",
    "ai_settings_router",
    "search_router",
    "editor_router",
    "revisions_router",
    "notifications_router",
    "integration_router",
]
