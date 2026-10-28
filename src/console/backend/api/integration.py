"""Integration API: discovery catalog and a signed ping (ADR-0006).

The job API defined in ``docs/api/cdp-if-09-contract.md`` is still *planned*
(``civilpdf.pdf-postprocess``); what exists here is the runtime surface that lets
another system discover CivilPDF-DX and verify that its HMAC signing works
before it depends on a job endpoint.

``CATALOG`` is the in-process declaration this service advertises. The repository
test ``tests/console/test_integration_api.py`` asserts it matches
``infra/integration/system.json``, so the governance manifest and the running
service cannot drift silently.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from config import settings
from services.service_auth import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    SYSTEM_HEADER,
    TIMESTAMP_HEADER,
    ServiceIdentity,
    require_service,
)

router = APIRouter(prefix="/integration", tags=["Integration"])

# Keep in sync with infra/integration/system.json (enforced by a test).
CATALOG: dict = {
    "systemId": "civilpdf",
    "displayName": "CivilPDF-DX",
    "repository": "mirai-construction-dx/CivilPDF-DX",
    "interfaces": {
        "provides": [
            {
                "id": "civilpdf.integration-discovery",
                "protocol": "http",
                "status": "implemented",
                "endpoint": "GET /api/v1/integration/catalog",
            },
            {
                "id": "civilpdf.pdf-postprocess",
                "protocol": "http",
                "status": "planned",
                "endpoint": "POST /api/v1/integration/pdf-jobs",
            },
            {
                "id": "civilpdf.mcp",
                "protocol": "mcp",
                "status": "not-implemented",
                "endpoint": "mcp://civilpdf",
            },
        ],
        "consumes": [
            {
                "id": "core.contracts",
                "protocol": "vendored-contracts",
                "status": "not-integrated",
            },
            {
                "id": "cdp.cde-registration",
                "protocol": "http",
                "status": "not-implemented",
            },
        ],
    },
    "registration": {
        "platformInfra": "registered",
        "harnessCore": "pending",
        "civilDocsPlatform": "pending",
    },
}


@router.get("/catalog")
def get_catalog() -> dict:
    """Public, read-only discovery document (no secrets, no authentication).

    A peer uses this to learn the system id, version and which interfaces are
    actually implemented before it configures signing or calls a job endpoint.
    """
    return {
        **CATALOG,
        "version": settings.app_version,
        "environment": settings.environment,
        "authentication": {
            "scheme": "hmac-sha256",
            "headers": [
                SYSTEM_HEADER,
                TIMESTAMP_HEADER,
                NONCE_HEADER,
                SIGNATURE_HEADER,
            ],
            "clockSkewSeconds": settings.integration_clock_skew_seconds,
            "contract": "docs/api/integration-api.md",
        },
    }


@router.get("/ping")
def ping(identity: ServiceIdentity = Depends(require_service)) -> dict:
    """Signed round-trip used by a peer to validate its HMAC implementation."""
    return {
        "status": "ok",
        "systemId": "civilpdf",
        "caller": identity.system_id,
        "serverTime": int(time.time()),
    }
