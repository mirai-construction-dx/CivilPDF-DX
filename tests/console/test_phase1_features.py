"""Phase 1 feature tests — password reset, trash/restore, pagination,
notifications, permission report, OIDC SSO and download audit."""

import io


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _create_project(client, token: str, name: str = "Phase1 Project") -> str:
    resp = client.post(
        "/api/v1/projects/",
        json={"name": name, "code": f"P1-{abs(hash(name)) % 100000}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload_doc(client, token: str, project_id: str, title: str = "図面") -> str:
    resp = client.post(
        "/api/v1/documents/",
        data={"project_id": project_id, "title": title},
        files={
            "file": (f"{title}.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestPasswordReset:
    def test_request_does_not_reveal_account_existence(self, client):
        resp = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 202
        assert "reset_token" not in resp.json()

    def test_full_reset_flow(self, client, admin_user, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "debug", True)
        resp = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": admin_user.email},
        )
        assert resp.status_code == 202
        token = resp.json()["reset_token"]

        resp = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "new_password": "NewPass123!"},
        )
        assert resp.status_code == 204

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": admin_user.email, "password": "NewPass123!"},
        )
        assert resp.status_code == 200

    def test_confirm_with_invalid_token(self, client):
        resp = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "not-a-token", "new_password": "NewPass123!"},
        )
        assert resp.status_code == 400

    def test_admin_reset(self, client, admin_token, engineer_user):
        resp = client.post(
            f"/api/v1/users/{engineer_user.id}/password-reset",
            json={"new_password": "AdminReset123!"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": engineer_user.email, "password": "AdminReset123!"},
        )
        assert resp.status_code == 200


class TestTrashAndRestore:
    def test_trash_list_and_restore(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id, "復元対象")

        resp = client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

        resp = client.get(
            "/api/v1/documents/trash",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert any(d["id"] == doc_id for d in resp.json())

        resp = client.post(
            f"/api/v1/documents/{doc_id}/restore",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deletion_requested_at"] is None

        resp = client.get(
            "/api/v1/documents/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert any(d["id"] == doc_id for d in resp.json())


class TestPagination:
    def test_include_meta_returns_pagination(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        for i in range(3):
            _upload_doc(client, admin_token, project_id, f"文書{i}")
        resp = client.get(
            "/api/v1/documents/?include_meta=true&page=1&per_page=2",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["pages"] == 2


class TestNotifications:
    def test_workflow_creation_notifies_first_approver(
        self, client, admin_token, engineer_token, engineer_user
    ):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        # A-3: the approver must be able to view the document.
        client.post(
            f"/api/v1/projects/{project_id}/members/{engineer_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        created = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [engineer_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 201
        resp = client.get(
            "/api/v1/notifications/",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        assert any(
            n["notification_type"] == "workflow.assigned" for n in resp.json()["items"]
        )

        unread = client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert unread.json()["unread"] >= 1

        nid = next(
            n["id"]
            for n in resp.json()["items"]
            if n["notification_type"] == "workflow.assigned"
        )
        resp = client.post(
            f"/api/v1/notifications/{nid}/read",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True


class TestPermissionReport:
    def test_admin_can_export_json_and_csv(self, client, admin_token):
        resp = client.get(
            "/api/v1/users/permissions-report",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        resp = client.get(
            "/api/v1/users/permissions-report?format=csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    def test_non_admin_forbidden(self, client, viewer_token):
        resp = client.get(
            "/api/v1/users/permissions-report",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestOIDCSSO:
    def test_login_returns_503_when_not_configured(self, client):
        resp = client.get("/api/v1/auth/oidc/login")
        assert resp.status_code == 503

    def test_login_and_callback_flow(self, client, monkeypatch):
        from config import settings
        from services import oidc as oidc_service

        monkeypatch.setattr(settings, "oidc_client_id", "test-client")
        monkeypatch.setattr(settings, "oidc_client_secret", "test-secret")
        monkeypatch.setattr(
            settings,
            "oidc_discovery_url",
            "https://idp.example/.well-known/openid-configuration",
        )
        monkeypatch.setattr(
            settings,
            "oidc_redirect_uri",
            "https://app.example/api/v1/auth/oidc/callback",
        )
        monkeypatch.setattr(
            oidc_service,
            "_discover",
            lambda: {
                "issuer": "https://idp.example",
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "jwks_uri": "https://idp.example/jwks",
            },
        )

        login_resp = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
        assert login_resp.status_code == 307
        assert "state=" in login_resp.headers["location"]
        state_cookie = login_resp.cookies.get("civilpdf_oidc_state")
        assert state_cookie
        from urllib.parse import parse_qs, urlparse

        state_value = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][
            0
        ]

        monkeypatch.setattr(
            oidc_service,
            "exchange_code",
            lambda code, verifier: {"id_token": "signed.id.token"},
        )
        monkeypatch.setattr(
            oidc_service,
            "validate_id_token",
            lambda id_token, nonce: {
                "sub": "oidc-user-1",
                "email": "oidc@example.com",
                "name": "OIDC User",
                "preferred_username": "oidcuser",
            },
        )

        resp = client.get(
            f"/api/v1/auth/oidc/callback?code=abc&state={state_value}",
            cookies={"civilpdf_oidc_state": state_cookie},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

        # Provisioned user can authenticate with the issued token.
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "oidc@example.com"


class TestDownloadAudit:
    def test_download_records_audit_log(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        resp = client.get(
            f"/api/v1/documents/{doc_id}/download",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        audit = client.get(
            "/api/v1/audit-logs/?action=document.downloaded",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert audit.json()["total"] >= 1
