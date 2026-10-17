"""Integration API: discovery catalog and HMAC-signed service calls (ADR-0006).

Two things are verified here:

1. The advertised catalog matches ``infra/integration/system.json`` — otherwise
   the governance manifest and the running service drift apart silently.
2. The HMAC scheme rejects unsigned, unknown, stale, tampered and replayed
   requests, and fails closed (503) when no peer secret is configured.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from config import settings
from services import service_auth

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "infra" / "integration" / "system.json"

SYSTEM = "civil-docs-platform"
SECRET = "test-integration-secret"


@pytest.fixture(autouse=True)
def _reset_nonces():
    service_auth.reset_nonce_cache()
    yield
    service_auth.reset_nonce_cache()


def _sign(
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes = b"",
    secret: str = SECRET,
) -> str:
    message = (
        f"{method}\n{path}\n{timestamp}\n{nonce}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    ).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _headers(
    method: str,
    path: str,
    *,
    timestamp: int | None = None,
    nonce: str = "0123456789abcdef0123456789abcdef",
    secret: str = SECRET,
    system: str = SYSTEM,
    body: bytes = b"",
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    return {
        "X-CivilPDF-System": system,
        "X-CivilPDF-Timestamp": str(ts),
        "X-CivilPDF-Nonce": nonce,
        "X-CivilPDF-Signature": _sign(method, path, ts, nonce, body, secret),
    }


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "integration_hmac_secrets", {SYSTEM: SECRET})
    return settings


class TestCatalog:
    def test_catalog_is_public(self, client):
        response = client.get("/api/v1/integration/catalog")
        assert response.status_code == 200

    def test_catalog_identity(self, client):
        body = client.get("/api/v1/integration/catalog").json()
        assert body["systemId"] == "civilpdf"
        assert body["repository"] == "mirai-construction-dx/CivilPDF-DX"
        assert body["version"] == settings.app_version
        assert body["authentication"]["scheme"] == "hmac-sha256"

    def test_catalog_matches_manifest(self, client):
        """The running service must not advertise a different interface set."""
        body = client.get("/api/v1/integration/catalog").json()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        assert body["systemId"] == manifest["systemId"]
        assert body["repository"] == manifest["repository"]
        assert body["registration"] == manifest["registration"]
        for section in ("provides", "consumes"):
            advertised = {
                (item["id"], item["protocol"], item["status"])
                for item in body["interfaces"][section]
            }
            declared = {
                (item["id"], item["protocol"], item["status"])
                for item in manifest[section]
            }
            assert advertised == declared, section


class TestPingAuthentication:
    def test_unconfigured_secrets_fail_closed(self, client, monkeypatch):
        monkeypatch.setattr(settings, "integration_hmac_secrets", {})
        response = client.get("/api/v1/integration/ping")
        assert response.status_code == 503

    def test_missing_headers(self, client, configured):
        assert client.get("/api/v1/integration/ping").status_code == 401

    def test_unknown_system(self, client, configured):
        headers = _headers("GET", "/api/v1/integration/ping", system="unknown-system")
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 401
        )

    def test_valid_signature(self, client, configured):
        headers = _headers("GET", "/api/v1/integration/ping")
        response = client.get("/api/v1/integration/ping", headers=headers)
        assert response.status_code == 200
        assert response.json()["caller"] == SYSTEM

    def test_tampered_signature(self, client, configured):
        headers = _headers("GET", "/api/v1/integration/ping")
        headers["X-CivilPDF-Signature"] = "0" * 64
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 401
        )

    def test_expired_timestamp(self, client, configured):
        stale = int(time.time()) - settings.integration_clock_skew_seconds - 60
        headers = _headers("GET", "/api/v1/integration/ping", timestamp=stale)
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 401
        )

    def test_replayed_nonce(self, client, configured):
        headers = _headers("GET", "/api/v1/integration/ping")
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 200
        )
        # Same nonce (and therefore the same signature) must be rejected.
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 401
        )

    def test_signature_is_bound_to_path(self, client, configured):
        headers = _headers("GET", "/api/v1/integration/other", nonce="a" * 32)
        assert (
            client.get("/api/v1/integration/ping", headers=headers).status_code == 401
        )
