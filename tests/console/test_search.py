"""Tests for document search API (Phase 7 P2)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_fts_table(db_session):
    """Drop FTS5 virtual table before each test so auto-rebuild always fires fresh."""
    try:
        db_session.execute(text("DROP TABLE IF EXISTS documents_fts"))
        db_session.commit()
    except Exception:
        pass
    yield


@pytest.fixture
def auth_headers(client: TestClient, admin_user):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin@example.com", "password": "Admin1234!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def sample_docs(db_session, admin_user):
    """Create several documents with OCR text for search testing."""
    from models.document import Document, DocumentStatus, DocumentType
    from models.user import Project

    project = Project(name="検索テスト", code="SRCH-001")
    db_session.add(project)
    db_session.flush()

    docs = [
        Document(
            title="○○橋梁補修工事 平面図",
            filename="bridge_plan.pdf",
            file_size=2048,
            document_type=DocumentType.DRAWING,
            status=DocumentStatus.DRAFT,
            project_id=project.id,
            owner_id=admin_user.id,
            ocr_text="橋梁 補修 平面図 RC構造 スパン12m 東京都港区 1:100",
            tags=["図面:平面図", "種別:橋梁"],
            extra_data={},
        ),
        Document(
            title="△△ビル新築工事 構造図",
            filename="building_structure.pdf",
            file_size=3072,
            document_type=DocumentType.DRAWING,
            status=DocumentStatus.APPROVED,
            project_id=project.id,
            owner_id=admin_user.id,
            ocr_text="鉄筋コンクリート 構造図 配筋 柱 梁 基礎 建築確認 S造",
            tags=["図面:構造図", "種別:建築"],
            extra_data={},
        ),
        Document(
            title="道路舗装工事 安全書類",
            filename="road_safety.pdf",
            file_size=1024,
            document_type=DocumentType.SAFETY,
            status=DocumentStatus.PENDING_REVIEW,
            project_id=project.id,
            owner_id=admin_user.id,
            ocr_text="道路 舗装 アスファルト 安全管理 施工計画 重機",
            tags=["種別:道路"],
            extra_data={},
        ),
    ]
    for doc in docs:
        db_session.add(doc)
    db_session.commit()
    return docs


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestKeywordSearch:
    def test_search_returns_results(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """GET /search/documents?q=橋梁&mode=keyword returns matching docs."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "keyword"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "橋梁"
        assert data["mode"] == "keyword"
        assert data["total"] >= 1
        titles = [h["title"] for h in data["hits"]]
        assert any("橋梁" in t for t in titles)

    def test_search_no_results(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """Returns empty hits for a query with no matches."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "存在しないキーワードXYZ999", "mode": "keyword"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["hits"] == []

    def test_search_multiple_results(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """Search for common term returns multiple results."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "構造", "mode": "keyword"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # "構造図" appears in multiple docs
        assert data["total"] >= 1

    def test_search_requires_auth(self, client: TestClient):
        """Unauthenticated request returns 401."""
        resp = client.get("/api/v1/search/documents", params={"q": "test"})
        assert resp.status_code == 401

    def test_search_query_too_short(self, client: TestClient, auth_headers: dict):
        """Empty query returns 422."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "", "mode": "keyword"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_search_invalid_mode(self, client: TestClient, auth_headers: dict):
        """Invalid mode returns 422."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "invalid"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_search_limit_respected(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """limit parameter caps number of results."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "工事", "mode": "keyword", "limit": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["hits"]) <= 1

    def test_search_hit_has_snippet(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """Each hit includes a snippet field."""
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "keyword"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["hits"]:
            assert "snippet" in data["hits"][0]
            assert isinstance(data["hits"][0]["snippet"], str)


class TestSemanticSearch:
    def test_semantic_search_with_expanded_terms(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """Semantic mode calls _expand_query_with_claude and uses expanded terms."""
        expanded = ["橋梁", "bridge", "RC構造", "補修", "スパン"]

        with patch("api.search._expand_query_with_claude", return_value=expanded):
            resp = client.get(
                "/api/v1/search/documents",
                params={"q": "橋", "mode": "semantic"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "semantic"
        assert data["expanded_terms"] == expanded

    def test_semantic_search_falls_back_to_keyword_without_api_key(
        self, client: TestClient, auth_headers: dict, sample_docs, monkeypatch
    ):
        """Without ANTHROPIC_API_KEY, semantic search falls back gracefully."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Falls back to original query
        assert data["expanded_terms"] == ["橋梁"]

    def test_suggest_without_api_key(
        self, client: TestClient, auth_headers: dict, monkeypatch
    ):
        """Suggest endpoint returns original query when no API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp = client.get(
            "/api/v1/search/documents/suggest",
            params={"q": "橋梁"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == ["橋梁"]


class TestReindex:
    def test_reindex_admin_only(
        self, client: TestClient, auth_headers: dict, sample_docs
    ):
        """Admin can trigger reindex."""
        resp = client.post(
            "/api/v1/search/documents/reindex",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "indexed" in data
        assert isinstance(data["indexed"], int)

    def test_reindex_forbidden_for_viewer(
        self, client: TestClient, db_session, sample_docs
    ):
        """Viewer cannot trigger reindex."""
        from auth.jwt import get_password_hash
        from models.user import User, UserRole, UserStatus

        viewer = User(
            email="viewer_reindex@example.com",
            username="viewer_reindex",
            full_name="Viewer Reindex",
            hashed_password=get_password_hash("Viewer1234!"),
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE,
        )
        db_session.add(viewer)
        db_session.commit()

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "viewer_reindex@example.com", "password": "Viewer1234!"},
        )
        viewer_token = resp.json()["access_token"]

        resp = client.post(
            "/api/v1/search/documents/reindex",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestSearchQueryCost:
    """Search must not issue one query per hit (N+1 on a hot read path).

    Regression: the hit filter called ``document_visible`` per row, which loaded
    the document one id at a time — up to ``limit`` (<=100) extra SELECTs.
    """

    def _search_select_count(self, client, headers, db_session, query):
        from sqlalchemy import event

        bind = db_session.get_bind()
        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(bind, "before_cursor_execute", _record)
        try:
            resp = client.get(
                "/api/v1/search/documents", params={"q": query}, headers=headers
            )
            assert resp.status_code == 200, resp.text
        finally:
            event.remove(bind, "before_cursor_execute", _record)
        return len([s for s in statements if s.lstrip().upper().startswith("SELECT")])

    def test_query_count_does_not_grow_with_hit_count(
        self, client, auth_headers, db_session
    ):
        from models.document import Document, DocumentStatus, DocumentType
        from models.user import Project, User

        owner = db_session.query(User).filter(User.email == "admin@example.com").one()

        def seed(count, code):
            project = Project(name=f"検索N+1 {code}", code=code)
            db_session.add(project)
            db_session.flush()
            for i in range(count):
                db_session.add(
                    Document(
                        title=f"N1検索対象 {code}-{i}",
                        filename=f"n1_{code}_{i}.pdf",
                        file_size=10,
                        document_type=DocumentType.REPORT,
                        status=DocumentStatus.DRAFT,
                        project_id=project.id,
                        owner_id=owner.id,
                        ocr_text="共通キーワード N1SEARCH 検索対象",
                        tags=[],
                        extra_data={},
                    )
                )
            db_session.commit()

        seed(2, "N1-A")
        small = self._search_select_count(client, auth_headers, db_session, "N1SEARCH")

        seed(10, "N1-B")
        big = self._search_select_count(client, auth_headers, db_session, "N1SEARCH")

        assert big <= small + 2, (
            "search SELECT count grew with the number of hits, so the visibility "
            f"filter is still per-hit: 2 hits -> {small} SELECTs, "
            f"12 hits -> {big} SELECTs"
        )
