"""M365 integration API tests — config CRUD + lookup error paths.

Auth bridge tests live in test_m365_auth.py.
"""

import pytest
from cryptography.fernet import Fernet

from services import m365 as m365_service


@pytest.fixture
def fernet_key(monkeypatch):
    """Provide a valid Fernet key for tests that exercise encrypt/decrypt."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(m365_service.settings, "m365_fernet_key", key)
    return key


class TestM365Config:
    def test_get_config_admin_returns_full_shape(self, client, admin_token):
        resp = client.get(
            "/api/v1/m365/config",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Public shape (no client_secret ever exposed)
        assert set(data.keys()) == {
            "tenant_id",
            "client_id",
            "enabled",
            "auto_provision",
            "default_role",
            "has_client_secret",
        }
        # Defaults from the singleton row
        assert data["tenant_id"] == ""
        assert data["client_id"] == ""
        assert data["enabled"] is False
        assert data["auto_provision"] is True
        assert data["default_role"] == "viewer"
        assert data["has_client_secret"] is False

    def test_get_config_unauthenticated(self, client):
        resp = client.get("/api/v1/m365/config")
        assert resp.status_code == 401

    def test_get_config_non_admin(self, client, viewer_token):
        resp = client.get(
            "/api/v1/m365/config",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_update_config_basic_fields(self, client, admin_token):
        resp = client.put(
            "/api/v1/m365/config",
            json={
                "tenant_id": "test-tenant",
                "client_id": "test-client",
                "enabled": False,
                "auto_provision": False,
                "default_role": "engineer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "test-tenant"
        assert data["client_id"] == "test-client"
        assert data["enabled"] is False
        assert data["auto_provision"] is False
        assert data["default_role"] == "engineer"
        assert data["has_client_secret"] is False

    def test_update_config_with_secret_encrypts(
        self, client, admin_token, fernet_key, db_session
    ):
        resp = client.put(
            "/api/v1/m365/config",
            json={
                "tenant_id": "tid",
                "client_id": "cid",
                "client_secret": "super-secret-value",
                "enabled": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Secret is never returned via the API
        assert "client_secret" not in data
        assert data["has_client_secret"] is True

        # Verify ciphertext is stored, not plaintext
        from models.m365_setting import M365Setting

        row = db_session.query(M365Setting).filter(M365Setting.id == 1).first()
        assert row is not None
        assert row.client_secret_enc != ""
        assert row.client_secret_enc != "super-secret-value"
        # Round-trip via the service decrypts back to the original plaintext
        assert (
            m365_service.decrypt_secret(row.client_secret_enc) == "super-secret-value"
        )

    def test_update_config_non_admin_forbidden(self, client, viewer_token):
        resp = client.put(
            "/api/v1/m365/config",
            json={"tenant_id": "x"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestM365TestConnection:
    def test_test_connection_returns_503_when_config_missing(self, client, admin_token):
        # Default singleton has enabled=False → test_connection returns {ok:False, stage:"config"}
        resp = client.post(
            "/api/v1/m365/test-connection",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["ok"] is False
        assert body["detail"]["stage"] == "config"

    def test_test_connection_non_admin_forbidden(self, client, viewer_token):
        resp = client.post(
            "/api/v1/m365/test-connection",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestM365Lookup:
    def test_lookup_user_when_m365_disabled_returns_503(self, client, admin_token):
        # M365 is disabled by default in tests — _require_enabled raises M365ConfigError
        resp = client.get(
            "/api/v1/m365/users/lookup?email=test@example.com",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 503

    def test_lookup_user_non_admin_forbidden(self, client, viewer_token):
        resp = client.get(
            "/api/v1/m365/users/lookup?email=test@example.com",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestFernetRoundTrip:
    """Service-level encryption guarantees, independent of HTTP layer."""

    def test_encrypt_then_decrypt_matches(self, fernet_key):
        cipher = m365_service.encrypt_secret("plaintext-abc-123")
        assert cipher != "plaintext-abc-123"
        assert m365_service.decrypt_secret(cipher) == "plaintext-abc-123"

    def test_encrypt_empty_returns_empty(self, fernet_key):
        assert m365_service.encrypt_secret("") == ""
        assert m365_service.decrypt_secret("") == ""

    def test_decrypt_garbage_raises_config_error(self, fernet_key):
        with pytest.raises(m365_service.M365ConfigError):
            m365_service.decrypt_secret("not-a-valid-fernet-token")

    def test_encrypt_without_key_raises_config_error(self, monkeypatch):
        monkeypatch.setattr(m365_service.settings, "m365_fernet_key", "")
        with pytest.raises(m365_service.M365ConfigError):
            m365_service.encrypt_secret("anything")
