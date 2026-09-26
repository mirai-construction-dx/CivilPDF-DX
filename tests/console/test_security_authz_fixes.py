"""Security hardening tests — RBAC boundaries, token types, upload validation,
soft delete, workflow ordering, lockout and production settings validation."""

import io

import pytest



def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _create_project(client, token: str, name: str = "Security Project") -> str:
    resp = client.post(
        "/api/v1/projects/",
        json={"name": name, "code": f"SEC-{abs(hash(name)) % 100000}"},
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


class TestDocumentAccessBoundaries:
    def test_viewer_cannot_see_foreign_documents(
        self, client, admin_token, viewer_token
    ):
        project_id = _create_project(client, admin_token)
        _upload_doc(client, admin_token, project_id, "機密図面")

        resp = client.get(
            "/api/v1/documents/", headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert resp.status_code == 200
        assert all(d["title"] != "機密図面" for d in resp.json())

    def test_viewer_cannot_download_foreign_document(
        self, client, admin_token, viewer_token
    ):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        resp = client.get(
            f"/api/v1/documents/{doc_id}/download",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 404

    def test_engineer_member_can_see_project_documents(
        self, client, admin_token, engineer_token, engineer_user
    ):
        project_id = _create_project(client, admin_token)
        _upload_doc(client, admin_token, project_id, "共有図面")
        resp = client.post(
            f"/api/v1/projects/{project_id}/members/{engineer_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

        resp = client.get(
            "/api/v1/documents/", headers={"Authorization": f"Bearer {engineer_token}"}
        )
        assert any(d["title"] == "共有図面" for d in resp.json())

    def test_engineer_non_member_cannot_upload_to_foreign_project(
        self, client, admin_token, engineer_token
    ):
        project_id = _create_project(client, admin_token)
        resp = client.post(
            "/api/v1/documents/",
            data={"project_id": project_id, "title": "侵入"},
            files={
                "file": (
                    "x.pdf",
                    io.BytesIO(_make_pdf_bytes()),
                    "application/pdf",
                )
            },
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 404


class TestTokenTypeBoundary:
    def test_refresh_token_rejected_on_api(self, client, admin_token):
        # Get a real refresh token via the token endpoint.
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "admin@example.com", "password": "Admin1234!"},
        )
        refresh_token = resp.json()["refresh_token"]

        resp = client.get(
            "/api/v1/documents/",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert resp.status_code == 401


class TestUploadValidation:
    def test_non_pdf_magic_bytes_rejected(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        resp = client.post(
            "/api/v1/documents/",
            data={"project_id": project_id, "title": "偽装PDF"},
            files={
                "file": (
                    "fake.pdf",
                    io.BytesIO(b"PK\x03\x04 not a pdf"),
                    "application/pdf",
                )
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 415

    def test_filename_header_injection_sanitized(self, client, admin_token, db_session):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id, "図面")
        from models.document import Document

        doc = db_session.query(Document).filter(Document.id == doc_id).first()
        doc.filename = 'evil"\r\nX-Injected: 1.pdf'
        db_session.commit()

        resp = client.get(
            f"/api/v1/documents/{doc_id}/download",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert "\r\n" not in disposition
        assert "X-Injected: 1" not in disposition


class TestSoftDelete:
    def test_delete_is_logical_and_hidden_from_list(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id, "削除対象")

        resp = client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["deletion_requested_at"] is not None

        list_resp = client.get(
            "/api/v1/documents/", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert all(d["id"] != doc_id for d in list_resp.json())


class TestWorkflowOrder:
    def test_cannot_approve_later_step_first(
        self,
        client,
        admin_token,
        manager_token,
        engineer_user,
        manager_user,
        db_session,
    ):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        resp = client.post(
            "/api/v1/workflows/",
            json={
                "document_id": doc_id,
                "approver_ids": [engineer_user.id, manager_user.id],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        workflow = resp.json()
        step2_id = workflow["steps"][1]["id"]

        resp = client.post(
            f"/api/v1/workflows/{workflow['id']}/steps/{step2_id}/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 409


class TestLoginLockout:
    def test_account_locks_after_five_failures_and_admin_can_unlock(
        self, client, admin_token, admin_user
    ):
        email = admin_user.email
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/token",
                data={"username": email, "password": "WrongPass1!"},
            )
            assert resp.status_code == 401

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": "Admin1234!"},
        )
        assert resp.status_code == 403
        assert "locked" in resp.json()["detail"]

        resp = client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"unlock": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": "Admin1234!"},
        )
        assert resp.status_code == 200


class TestPasswordPolicy:
    def test_weak_password_rejected(self, client, admin_token):
        resp = client.post(
            "/api/v1/users/",
            json={
                "email": "weak@example.com",
                "username": "weakuser",
                "full_name": "Weak User",
                "password": "abcdefgh",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_strong_password_accepted(self, client, admin_token):
        resp = client.post(
            "/api/v1/users/",
            json={
                "email": "strong@example.com",
                "username": "stronguser",
                "full_name": "Strong User",
                "password": "StrongPass123!",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201


class TestAuditPersistence:
    def test_document_upload_persists_audit_log(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        _upload_doc(client, admin_token, project_id)

        resp = client.get(
            "/api/v1/audit-logs/?action=document.uploaded",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_user_create_persists_audit_log(self, client, admin_token):
        client.post(
            "/api/v1/users/",
            json={
                "email": "audit@example.com",
                "username": "audituser",
                "full_name": "Audit User",
                "password": "AuditPass123!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.get(
            "/api/v1/audit-logs/?action=user.created",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


class TestProductionSettingsValidation:
    def test_insecure_secret_key_fails_fast(self):
        from config import Settings, validate_production_settings

        cfg = Settings(
            _env_file=None,
            debug=False,
            secret_key="change-this-in-production",
            timestamp_hmac_key="unit-test-hmac-key-value",
        )
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            validate_production_settings(cfg)

    def test_insecure_hmac_key_fails_fast(self):
        from config import Settings, validate_production_settings

        cfg = Settings(
            _env_file=None,
            debug=False,
            secret_key="unit-test-secret-key-value",
            timestamp_hmac_key="change-me-in-production",
        )
        with pytest.raises(RuntimeError, match="TIMESTAMP_HMAC_KEY"):
            validate_production_settings(cfg)

    def test_valid_settings_pass(self):
        from config import Settings, validate_production_settings

        cfg = Settings(
            _env_file=None,
            debug=False,
            secret_key="unit-test-secret-key-value",
            timestamp_hmac_key="unit-test-hmac-key-value",
        )
        validate_production_settings(cfg)
