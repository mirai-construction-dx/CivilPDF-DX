"""Tests for AI document analysis API (Phase 7)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ai_enabled(db_session):
    """These tests exercise AI behaviour, so the admin kill switch is on.

    The switch itself (default off, fail closed) is covered in
    test_ai_kill_switch.py.
    """
    from services import ai_settings as ai_settings_service

    ai_settings_service.update_ai_setting(db_session, enabled=True)


@pytest.fixture
def auth_headers(client: TestClient, admin_user):
    """Return Authorization headers for the admin user."""
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin@example.com", "password": "Admin1234!"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_doc_id(client: TestClient, auth_headers: dict, db_session):
    """Create a sample document and return its ID. Sets ocr_text for AI tests."""
    from models.document import Document, DocumentType, DocumentStatus
    from models.user import User, Project

    admin = db_session.query(User).filter(User.email == "admin@example.com").first()

    # Create a project first
    project = Project(name="AIテストプロジェクト", code="AI-TEST-001")
    db_session.add(project)
    db_session.flush()

    doc = Document(
        title="テスト平面図.pdf",
        filename="test_plan.pdf",
        file_size=1024,
        document_type=DocumentType.DRAWING,
        status=DocumentStatus.DRAFT,
        project_id=project.id,
        owner_id=admin.id,
        ocr_text="平面図 1:100 建物配置図 東京都港区芝公園 工事名: ○○ビル新築工事 施工: 株式会社テスト建設",
        tags=[],
        extra_data={},
    )
    db_session.add(doc)
    db_session.commit()
    return doc.id


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestClassifyDocument:
    def test_classify_success(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str
    ):
        """POST /ai/documents/{id}/classify returns classification when API succeeds."""
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "drawing_type": "平面図",
                        "project_type": "建築",
                        "confidence": 0.92,
                        "reasoning": "平面レイアウトが含まれているため",
                    }
                )
            )
        ]

        with patch("api.ai._get_anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            resp = client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/classify",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["drawing_type"] == "平面図"
        assert data["project_type"] == "建築"
        assert data["confidence"] == pytest.approx(0.92)
        assert "図面:平面図" in data["tags"]
        assert "種別:建築" in data["tags"]
        assert "ai分類済" in data["tags"]
        assert data["document_id"] == sample_doc_id
        assert data["model"] == "claude-haiku-4-5-20251001"

    def test_classify_tags_persisted(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str, db_session
    ):
        """Classification tags are saved to the Document record."""
        from models.document import Document

        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "drawing_type": "構造図",
                        "project_type": "土木",
                        "confidence": 0.85,
                        "reasoning": "鉄筋配置図が含まれる",
                    }
                )
            )
        ]

        with patch("api.ai._get_anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/classify",
                headers=auth_headers,
            )

        doc = db_session.query(Document).filter(Document.id == sample_doc_id).first()
        assert doc is not None
        assert "図面:構造図" in doc.tags
        assert "種別:土木" in doc.tags
        assert doc.extra_data["ai_classification"]["drawing_type"] == "構造図"

    def test_classify_not_found(self, client: TestClient, auth_headers: dict):
        """POST /ai/documents/{id}/classify returns 404 for unknown document."""
        with patch("api.ai._get_anthropic_client"):
            resp = client.post(
                "/api/v1/ai/documents/nonexistent-id/classify",
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_classify_idor_blocked(
        self, client: TestClient, db_session, sample_doc_id: str
    ):
        """Viewer user cannot classify a document owned by admin (IDOR prevention)."""
        from auth.jwt import get_password_hash
        from models.user import User, UserRole, UserStatus

        # Create a separate viewer user who does NOT own the document
        viewer = User(
            email="viewer_idor@example.com",
            username="viewer_idor",
            full_name="IDOR Viewer",
            hashed_password=get_password_hash("Viewer1234!"),
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE,
        )
        db_session.add(viewer)
        db_session.commit()

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "viewer_idor@example.com", "password": "Viewer1234!"},
        )
        assert resp.status_code == 200
        viewer_token = resp.json()["access_token"]

        with patch("api.ai._get_anthropic_client"):
            resp = client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/classify",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 404

    def test_classify_no_api_key(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str, monkeypatch
    ):
        """Returns 503 when no API key is available (env var removed, DB key forced empty)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("api.ai.ai_settings_service.get_api_key", return_value=""):
            resp = client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/classify",
                headers=auth_headers,
            )
        assert resp.status_code == 503

    def test_classify_malformed_json_response(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str
    ):
        """Falls back gracefully when Claude returns non-JSON text."""
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(text="申し訳ありませんが分類できませんでした")
        ]

        with patch("api.ai._get_anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            resp = client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/classify",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["drawing_type"] is None
        assert data["project_type"] is None
        assert data["confidence"] == pytest.approx(0.0)

    def test_classify_requires_auth(self, client: TestClient, sample_doc_id: str):
        """Unauthenticated request returns 401."""
        resp = client.post(f"/api/v1/ai/documents/{sample_doc_id}/classify")
        assert resp.status_code == 401


class TestExtractDocument:
    def test_extract_success(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str
    ):
        """POST /ai/documents/{id}/extract returns structured data."""
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "construction_name": "○○橋梁補修工事",
                        "contractor": "株式会社土木テスト",
                        "site_location": "東京都港区",
                        "amount": "1500万円",
                        "start_date": "2026-04-01",
                        "end_date": "2026-09-30",
                        "responsible_person": "田中太郎",
                        "checklist_items": ["設計図確認", "材料検査", "施工計画書承認"],
                    }
                )
            )
        ]

        with patch("api.ai._get_anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            resp = client.post(
                f"/api/v1/ai/documents/{sample_doc_id}/extract",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == sample_doc_id
        assert data["data"]["construction_name"] == "○○橋梁補修工事"
        assert data["data"]["amount"] == "1500万円"
        assert len(data["data"]["checklist_items"]) == 3

    def test_extract_not_found(self, client: TestClient, auth_headers: dict):
        """Returns 404 for unknown document."""
        with patch("api.ai._get_anthropic_client"):
            resp = client.post(
                "/api/v1/ai/documents/nonexistent/extract",
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_extract_requires_auth(self, client: TestClient, sample_doc_id: str):
        """Unauthenticated request returns 401."""
        resp = client.post(f"/api/v1/ai/documents/{sample_doc_id}/extract")
        assert resp.status_code == 401


class TestDocumentSummary:
    def test_summary_success(
        self, client: TestClient, auth_headers: dict, sample_doc_id: str
    ):
        """GET /ai/documents/{id}/summary returns a summary."""
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(
                text="本文書は東京都港区における橋梁補修工事の設計図面です。補修範囲はA棟橋脚部分で、工期は2026年4月から9月の6ヶ月間です。施工は株式会社土木テストが担当します。"
            )
        ]

        with patch("api.ai._get_anthropic_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            resp = client.get(
                f"/api/v1/ai/documents/{sample_doc_id}/summary",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == sample_doc_id
        assert len(data["summary"]) > 10
        assert data["model"] == "claude-haiku-4-5-20251001"

    def test_summary_not_found(self, client: TestClient, auth_headers: dict):
        """Returns 404 for unknown document."""
        with patch("api.ai._get_anthropic_client"):
            resp = client.get(
                "/api/v1/ai/documents/nonexistent/summary",
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_summary_requires_auth(self, client: TestClient, sample_doc_id: str):
        """Unauthenticated request returns 401."""
        resp = client.get(f"/api/v1/ai/documents/{sample_doc_id}/summary")
        assert resp.status_code == 401
