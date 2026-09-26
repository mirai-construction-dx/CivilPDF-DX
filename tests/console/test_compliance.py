"""Phase 5.1 Compliance Foundation tests.

Covers:
- services/timestamp_service.py  (RFC 3161 / HMAC fallback)
- services/retention_service.py  (保存期間ポリシー)
- services/audit_chain_service.py (ハッシュチェーン)
- api/privacy.py                 (GDPR/CCPA endpoints)
- GET /audit-logs/verify         (chain verification endpoint)
"""

import base64
import hashlib
import json
import os

from models.document import Document, DocumentType
from models.retention_policy import DEFAULT_POLICIES, RetentionPolicy
from services import timestamp_service
from services.audit_chain_service import (
    GENESIS_HASH,
    create_chained_audit_log,
    verify_chain,
)
from services.retention_service import (
    apply_retention_policy,
    get_expired_documents,
    get_policy_for_document,
    seed_default_policies,
)


# ─── Timestamp Service ───────────────────────────────────────────────────────


class TestTimestampService:
    def test_generate_timestamp_local_fallback(self):
        """Without TSA_URL configured, local HMAC token is generated."""
        os.environ.pop("TSA_URL", None)
        # Reload module-level constant
        timestamp_service.TSA_URL = ""

        result = timestamp_service.generate_timestamp(b"hello pdf", "test.pdf")

        assert result["token_type"] == "local_hmac"
        assert result["file_hash"] == hashlib.sha256(b"hello pdf").hexdigest()
        assert result["tsa_url"] == ""
        assert result["token_b64"]
        assert result["verified_at"]

    def test_local_timestamp_verify_valid(self):
        timestamp_service.TSA_URL = ""
        result = timestamp_service.generate_timestamp(b"data", "f.pdf")
        assert timestamp_service.verify_local_timestamp(
            result["token_b64"], result["file_hash"]
        )

    def test_local_timestamp_verify_wrong_hash(self):
        timestamp_service.TSA_URL = ""
        result = timestamp_service.generate_timestamp(b"data", "f.pdf")
        assert not timestamp_service.verify_local_timestamp(
            result["token_b64"], "a" * 64
        )

    def test_verify_file_against_timestamp_match(self):
        timestamp_service.TSA_URL = ""
        content = b"pdf content here"
        result = timestamp_service.generate_timestamp(content, "doc.pdf")
        assert timestamp_service.verify_file_against_timestamp(
            content, result["file_hash"], result["token_b64"]
        )

    def test_verify_file_against_timestamp_mismatch(self):
        timestamp_service.TSA_URL = ""
        result = timestamp_service.generate_timestamp(b"original", "doc.pdf")
        assert not timestamp_service.verify_file_against_timestamp(
            b"tampered", result["file_hash"], result["token_b64"]
        )

    def test_token_is_base64_decodable(self):
        timestamp_service.TSA_URL = ""
        result = timestamp_service.generate_timestamp(b"x", "x.pdf")
        decoded = base64.b64decode(result["token_b64"])
        token_data = json.loads(decoded)
        assert token_data["type"] == "local_hmac"
        assert token_data["file_hash"] == result["file_hash"]


# ─── Retention Service ────────────────────────────────────────────────────────


class TestRetentionService:
    def test_seed_default_policies(self, db_session):
        seed_default_policies(db_session)
        count = db_session.query(RetentionPolicy).count()
        assert count == len(DEFAULT_POLICIES)

    def test_seed_idempotent(self, db_session):
        seed_default_policies(db_session)
        seed_default_policies(db_session)  # must not raise or duplicate
        count = db_session.query(RetentionPolicy).count()
        assert count == len(DEFAULT_POLICIES)

    def test_get_policy_for_drawing(self, db_session):
        seed_default_policies(db_session)
        policy = get_policy_for_document(db_session, DocumentType.DRAWING)
        assert policy is not None

    def test_apply_retention_sets_expiry(self, db_session, admin_user):
        seed_default_policies(db_session)

        doc = Document(
            title="test",
            document_type=DocumentType.DRAWING,
            filename="x.pdf",
            file_path="/tmp/x.pdf",
            file_size=100,
            mime_type="application/pdf",
            project_id="proj-1",
            owner_id=admin_user.id,
        )
        db_session.add(doc)
        db_session.flush()
        apply_retention_policy(db_session, doc)
        db_session.commit()
        db_session.refresh(doc)
        # Should have retention_expires_at set (or is_permanent policy)
        policy = get_policy_for_document(db_session, DocumentType.DRAWING)
        if policy and not policy.is_permanent:
            assert doc.retention_expires_at is not None

    def test_get_expired_documents_empty(self, db_session):
        docs = get_expired_documents(db_session)
        assert docs == []


# ─── Audit Chain Service ──────────────────────────────────────────────────────


class TestAuditChainService:
    def test_genesis_hash_format(self):
        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64

    def test_create_first_chained_log(self, db_session, admin_user):
        log = create_chained_audit_log(
            db_session,
            user_id=admin_user.id,
            action="test.action",
            resource_type="test",
            resource_id="r1",
            detail="details",
            ip_address="127.0.0.1",
        )
        assert log.id
        assert log.sequence_number == 1
        assert log.prev_hash == GENESIS_HASH
        assert log.record_hash
        assert len(log.record_hash) == 64  # SHA-256 hex

    def test_chain_links_correctly(self, db_session, admin_user):
        log1 = create_chained_audit_log(
            db_session,
            user_id=admin_user.id,
            action="first",
            resource_type="x",
            resource_id="1",
            detail="",
            ip_address=None,
        )
        log2 = create_chained_audit_log(
            db_session,
            user_id=admin_user.id,
            action="second",
            resource_type="x",
            resource_id="2",
            detail="",
            ip_address=None,
        )
        assert log2.prev_hash == log1.record_hash
        assert log2.sequence_number == log1.sequence_number + 1

    def test_verify_chain_empty(self, db_session):
        result = verify_chain(db_session, limit=100)
        assert result["chain_valid"] is True
        assert result["records_checked"] == 0
        assert result["first_broken_sequence"] is None

    def test_verify_chain_valid(self, db_session, admin_user):
        for i in range(5):
            create_chained_audit_log(
                db_session,
                user_id=admin_user.id,
                action=f"action.{i}",
                resource_type="test",
                resource_id=str(i),
                detail="",
                ip_address=None,
            )
        result = verify_chain(db_session, limit=100)
        assert result["chain_valid"] is True
        assert result["records_checked"] == 5
        assert result["first_broken_sequence"] is None

    def test_verify_chain_detects_tampering(self, db_session, admin_user):
        from models.audit_log import AuditLog

        log = create_chained_audit_log(
            db_session,
            user_id=admin_user.id,
            action="legit",
            resource_type="x",
            resource_id="1",
            detail="",
            ip_address=None,
        )
        # Tamper with the action field
        db_session.query(AuditLog).filter(AuditLog.id == log.id).update(
            {"action": "tampered_action"}
        )
        db_session.commit()
        result = verify_chain(db_session, limit=100)
        assert result["chain_valid"] is False
        assert result["first_broken_sequence"] == log.sequence_number


# ─── Privacy API ─────────────────────────────────────────────────────────────


class TestPrivacyAPI:
    def test_deletion_request_admin_only(self, client, viewer_token, admin_user):
        resp = client.delete(
            f"/api/v1/privacy/users/{admin_user.id}/data",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_deletion_request_user_not_found(self, client, admin_token):
        resp = client.delete(
            "/api/v1/privacy/users/nonexistent-id/data",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_deletion_request_marks_documents(
        self, client, admin_token, db_session, admin_user
    ):
        doc = Document(
            title="sensitive",
            document_type=DocumentType.CONTRACT,
            filename="s.pdf",
            file_path="/tmp/s.pdf",
            file_size=10,
            mime_type="application/pdf",
            project_id="proj-1",
            owner_id=admin_user.id,
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.delete(
            f"/api/v1/privacy/users/{admin_user.id}/data",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents_marked"] == 1
        assert data["user_id"] == admin_user.id
        assert "audit_log_id" in data

        db_session.refresh(doc)
        assert doc.deletion_requested_at is not None

    def test_data_export_self(self, client, viewer_token, viewer_user):
        resp = client.get(
            f"/api/v1/privacy/users/{viewer_user.id}/export",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == viewer_user.id
        assert data["email"] == viewer_user.email
        assert "documents" in data
        assert "consent_records" in data

    def test_data_export_other_user_forbidden(self, client, viewer_token, admin_user):
        resp = client.get(
            f"/api/v1/privacy/users/{admin_user.id}/export",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_data_export_admin_can_access_any(self, client, admin_token, viewer_user):
        resp = client.get(
            f"/api/v1/privacy/users/{viewer_user.id}/export",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    def test_record_consent(self, client, admin_token):
        resp = client.post(
            "/api/v1/privacy/consent",
            json={
                "consent_type": "analytics",
                "version": "1.0",
                "granted": True,
                "source": "web",
                "disclosed_purpose": "サービス改善のための分析",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["granted"] is True
        assert data["consent_type"] == "analytics"
        assert "id" in data

    def test_record_consent_revocation(self, client, admin_token):
        # Grant first
        client.post(
            "/api/v1/privacy/consent",
            json={"consent_type": "marketing", "version": "1.0", "granted": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Then revoke — must be a NEW record, not an update
        resp = client.post(
            "/api/v1/privacy/consent",
            json={"consent_type": "marketing", "version": "1.0", "granted": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["granted"] is False

    def test_get_consent_status(self, client, admin_token, admin_user):
        client.post(
            "/api/v1/privacy/consent",
            json={"consent_type": "analytics", "version": "1.0", "granted": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.get(
            f"/api/v1/privacy/consent/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) >= 1
        assert records[0]["consent_type"] == "analytics"

    def test_get_consent_forbidden_for_other_user(
        self, client, viewer_token, admin_user
    ):
        resp = client.get(
            f"/api/v1/privacy/consent/{admin_user.id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


# ─── Audit Log Chain Verify Endpoint ─────────────────────────────────────────


class TestAuditChainEndpoint:
    def test_verify_chain_after_login(self, client, admin_token):
        resp = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain_valid"] is True
        # Login audit entries must form a valid chain (records_checked >= 1).
        assert data["records_checked"] >= 1
        assert data["first_broken_sequence"] is None

    def test_verify_requires_admin(self, client, viewer_token):
        resp = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_verify_requires_auth(self, client):
        resp = client.get("/api/v1/audit-logs/verify")
        assert resp.status_code == 401
