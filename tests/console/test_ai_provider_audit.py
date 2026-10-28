"""Audit records for direct AI Provider calls (ADR-0007).

Every request that actually reaches the provider — document classify /
extract / summary, search query expansion and the admin connection test — is
written to the hash-chained audit log with provider, model, operation, actor,
target document (if any), characters sent and result. The prompt, document
text, search words, AI response, exception message and key are never stored.

Calls refused before sending (environment gate, kill switch off, no key) send
nothing and are not recorded as provider calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.audit_log import AuditLog
from services import ai_audit
from services import ai_settings as ai_settings_service

DOC_TEXT = "秘匿テキスト平面図ABC 東京都港区芝公園 施工: 株式会社テスト建設"
DOC_TITLE = "監査テスト図面.pdf"
SEARCH_WORDS = "非公開検索語XYZ"
SECRET_KEY = "sk-ant-secret-value-never-logged"
UPSTREAM_ERROR = "upstream said something sensitive"

DOCUMENT_OPS = {
    # path: (http method, success action, max chars of document text sent)
    "classify": ("post", "ai.document_classified", 3000),
    "extract": ("post", "ai.document_extracted", 4000),
    "summary": ("get", "ai.document_summarized", 5000),
}


# ── Fixtures / helpers ────────────────────────────────────────────────────────


@pytest.fixture
def headers(client, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def ai_on(db_session, monkeypatch):
    ai_settings_service.update_ai_setting(db_session, enabled=True)
    monkeypatch.setattr(ai_settings_service.settings, "anthropic_api_key", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)


@pytest.fixture
def doc_id(db_session, admin_user):
    from models.document import Document, DocumentStatus, DocumentType
    from models.user import Project

    project = Project(name="AUD", code="AUD-001")
    db_session.add(project)
    db_session.flush()
    doc = Document(
        title=DOC_TITLE,
        filename="audit.pdf",
        file_size=10,
        document_type=DocumentType.DRAWING,
        status=DocumentStatus.DRAFT,
        project_id=project.id,
        owner_id=admin_user.id,
        ocr_text=DOC_TEXT,
        tags=[],
        extra_data={},
    )
    db_session.add(doc)
    db_session.commit()
    return doc.id


def _logs(db_session, prefix="ai.") -> list[AuditLog]:
    db_session.expire_all()
    return [
        x
        for x in db_session.query(AuditLog)
        .filter(AuditLog.sequence_number.isnot(None))
        .order_by(AuditLog.sequence_number.asc())
        .all()
        if x.action.startswith(prefix) and x.action != "ai.config.updated"
    ]


def _message(text: str):
    message = MagicMock()
    message.content = [MagicMock(text=text)]
    return message


def _assert_no_content(entry: AuditLog) -> None:
    raw = entry.detail or ""
    for forbidden in (
        DOC_TEXT,
        "平面図ABC",
        DOC_TITLE,
        SEARCH_WORDS,
        SECRET_KEY,
        UPSTREAM_ERROR,
    ):
        assert forbidden not in raw, forbidden
    for key in ("prompt", "content", "messages", "system", "response", "api_key"):
        assert key not in json.loads(raw), key


def _expected_chars(system: str, user_content: str) -> int:
    return len(system) + len(user_content)


# ── Unit: the helper itself ──────────────────────────────────────────────────


def test_sent_chars_counts_system_and_all_message_content():
    messages = [
        {"role": "user", "content": "abc"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "de"}, {"type": "image"}],
        },
    ]
    assert ai_audit.sent_chars("xyz", messages) == 3 + 3 + 2
    assert ai_audit.sent_chars(None, []) == 0


def test_detail_contains_metadata_only():
    detail = json.loads(
        ai_audit.provider_call_detail(
            operation="classify",
            model="m",
            chars=12,
            result="error",
            error=RuntimeError(UPSTREAM_ERROR),
        )
    )
    assert detail == {
        "provider": "anthropic",
        "model": "m",
        "operation": "classify",
        "sent_chars": 12,
        "result": "error",
        "error_type": "RuntimeError",
    }


# ── Document operations ──────────────────────────────────────────────────────


@pytest.mark.parametrize("path", sorted(DOCUMENT_OPS))
def test_document_call_success_is_audited_with_provider(
    client, headers, doc_id, db_session, admin_user, ai_on, path
):
    method, action, limit = DOCUMENT_OPS[path]
    reply = (
        '{"drawing_type": "平面図", "project_type": "建築", "confidence": 0.9}'
        if path == "classify"
        else '{"construction_name": null}'
        if path == "extract"
        else "要約"
    )
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = _message(reply)
        resp = getattr(client, method)(
            f"/api/v1/ai/documents/{doc_id}/{path}", headers=headers
        )
    assert resp.status_code == 200, resp.text
    kwargs = sdk.return_value.messages.create.call_args.kwargs

    logs = _logs(db_session)
    assert [x.action for x in logs] == [action]
    entry = logs[0]
    assert entry.user_id == admin_user.id
    assert entry.resource_type == "document" and entry.resource_id == doc_id
    detail = json.loads(entry.detail)
    assert detail["provider"] == "anthropic"
    assert detail["model"] == kwargs["model"]
    assert detail["operation"] == path
    assert detail["result"] == "success"
    assert detail["sent_chars"] == _expected_chars(
        kwargs["system"], kwargs["messages"][0]["content"]
    )
    assert detail["sent_chars"] > len(DOC_TEXT[:limit])
    _assert_no_content(entry)


@pytest.mark.parametrize("path", sorted(DOCUMENT_OPS))
def test_document_call_failure_is_audited_with_provider(
    db_session, doc_id, admin_user, admin_token, ai_on, path
):
    method, _, _ = DOCUMENT_OPS[path]
    tc = TestClient(app, raise_server_exceptions=False)
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.side_effect = RuntimeError(UPSTREAM_ERROR)
        resp = getattr(tc, method)(
            f"/api/v1/ai/documents/{doc_id}/{path}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 502
    kwargs = sdk.return_value.messages.create.call_args.kwargs

    logs = _logs(db_session)
    assert [x.action for x in logs] == [f"ai.document_{path}_failed"]
    detail = json.loads(logs[0].detail)
    assert logs[0].user_id == admin_user.id and logs[0].resource_id == doc_id
    assert detail["provider"] == "anthropic"
    assert detail["result"] == "error" and detail["error_type"] == "RuntimeError"
    assert detail["sent"] is True  # existing field kept
    assert detail["sent_chars"] == _expected_chars(
        kwargs["system"], kwargs["messages"][0]["content"]
    )
    _assert_no_content(logs[0])


@pytest.mark.parametrize("path", sorted(DOCUMENT_OPS))
def test_refused_document_calls_are_not_recorded_as_provider_calls(
    client, headers, doc_id, db_session, monkeypatch, path
):
    """Kill switch off (default) and environment refusal send nothing."""
    method, _, _ = DOCUMENT_OPS[path]
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    with patch("anthropic.Anthropic") as sdk:
        off = getattr(client, method)(
            f"/api/v1/ai/documents/{doc_id}/{path}", headers=headers
        )
        ai_settings_service.update_ai_setting(db_session, enabled=True)
        monkeypatch.setattr(ai_settings_service.settings, "environment", "production")
        blocked = getattr(client, method)(
            f"/api/v1/ai/documents/{doc_id}/{path}", headers=headers
        )
    assert off.status_code == 503 and blocked.status_code == 503
    sdk.assert_not_called()
    assert _logs(db_session) == []


# ── Search query expansion ───────────────────────────────────────────────────


@pytest.mark.parametrize("endpoint", ["documents", "documents/suggest"])
def test_query_expansion_success_is_audited(
    client, headers, db_session, admin_user, ai_on, endpoint
):
    params = {"q": SEARCH_WORDS}
    if endpoint == "documents":
        params["mode"] = "semantic"
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = _message('["橋梁", "橋"]')
        resp = client.get(f"/api/v1/search/{endpoint}", params=params, headers=headers)
    assert resp.status_code == 200
    kwargs = sdk.return_value.messages.create.call_args.kwargs

    logs = _logs(db_session)
    assert [x.action for x in logs] == ["ai.query_expanded"]
    entry = logs[0]
    assert entry.user_id == admin_user.id
    assert entry.resource_type == "search" and entry.resource_id is None
    detail = json.loads(entry.detail)
    assert detail["provider"] == "anthropic"
    assert detail["model"] == kwargs["model"] == "claude-haiku-4-5-20251001"
    assert detail["operation"] == "query_expansion"
    assert detail["result"] == "success"
    assert detail["sent_chars"] == _expected_chars(
        kwargs["system"], kwargs["messages"][0]["content"]
    )
    _assert_no_content(entry)


def test_query_expansion_failure_is_audited_and_search_still_works(
    client, headers, db_session, ai_on
):
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.side_effect = RuntimeError(UPSTREAM_ERROR)
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": SEARCH_WORDS, "mode": "semantic"},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["expanded_terms"] == [SEARCH_WORDS]
    logs = _logs(db_session)
    assert [x.action for x in logs] == ["ai.query_expanded"]
    detail = json.loads(logs[0].detail)
    assert detail["result"] == "error" and detail["error_type"] == "RuntimeError"
    _assert_no_content(logs[0])


def test_unparseable_expansion_reply_is_still_a_sent_request(
    client, headers, db_session, ai_on
):
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = _message("not json")
        resp = client.get(
            "/api/v1/search/documents/suggest",
            params={"q": SEARCH_WORDS},
            headers=headers,
        )
    assert resp.json() == [SEARCH_WORDS]
    logs = _logs(db_session)
    assert [x.action for x in logs] == ["ai.query_expanded"]
    assert json.loads(logs[0].detail)["error_type"] == "JSONDecodeError"


def test_refused_query_expansion_is_not_recorded(
    client, headers, db_session, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    with patch("anthropic.Anthropic") as sdk:
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": SEARCH_WORDS, "mode": "semantic"},
            headers=headers,
        )
    assert resp.status_code == 200
    sdk.assert_not_called()
    assert _logs(db_session) == []


def test_keyword_search_is_not_recorded(client, headers, db_session, ai_on):
    with patch("anthropic.Anthropic") as sdk:
        client.get("/api/v1/search/documents", params={"q": "橋"}, headers=headers)
    sdk.assert_not_called()
    assert _logs(db_session) == []


# ── Connection test ──────────────────────────────────────────────────────────


def test_connection_test_success_is_audited(
    client, headers, db_session, admin_user, ai_on
):
    with patch("api.ai_settings.anthropic.Anthropic") as sdk:
        resp = client.post("/api/v1/ai-config/test", headers=headers)
    assert resp.json()["ok"] is True
    kwargs = sdk.return_value.messages.create.call_args.kwargs

    logs = _logs(db_session)
    assert [x.action for x in logs] == ["ai.connection_tested"]
    entry = logs[0]
    assert entry.user_id == admin_user.id
    assert entry.resource_type == "ai_settings"
    detail = json.loads(entry.detail)
    assert detail["provider"] == "anthropic"
    assert detail["model"] == kwargs["model"]
    assert detail["operation"] == "connection_test"
    assert detail["result"] == "success"
    assert detail["sent_chars"] == len("ping")
    _assert_no_content(entry)


def test_connection_test_failure_is_audited_without_the_message(
    client, headers, db_session, ai_on
):
    with patch("api.ai_settings.anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.side_effect = RuntimeError(UPSTREAM_ERROR)
        resp = client.post("/api/v1/ai-config/test", headers=headers)
    assert resp.json()["ok"] is False
    logs = _logs(db_session)
    assert [x.action for x in logs] == ["ai.connection_tested"]
    detail = json.loads(logs[0].detail)
    assert detail["result"] == "error" and detail["error_type"] == "RuntimeError"
    _assert_no_content(logs[0])


def test_connection_test_without_key_or_in_production_is_not_recorded(
    client, headers, db_session, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_settings_service.settings, "anthropic_api_key", "")
    with patch("api.ai_settings.anthropic.Anthropic") as sdk:
        no_key = client.post("/api/v1/ai-config/test", headers=headers)
        monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
        monkeypatch.setattr(ai_settings_service.settings, "environment", "staging")
        blocked = client.post("/api/v1/ai-config/test", headers=headers)
    assert no_key.json()["ok"] is False
    assert blocked.status_code == 503
    sdk.assert_not_called()
    assert _logs(db_session) == []


def test_provider_audit_rows_keep_the_hash_chain_valid(
    client, headers, doc_id, db_session, ai_on
):
    from services.audit_chain_service import verify_chain

    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = _message("要約")
        client.get(f"/api/v1/ai/documents/{doc_id}/summary", headers=headers)
        sdk.return_value.messages.create.return_value = _message('["a"]')
        client.get(
            "/api/v1/search/documents/suggest", params={"q": "x"}, headers=headers
        )
    assert len(_logs(db_session)) == 2
    result = verify_chain(db_session)
    assert result["chain_valid"] is True and result["complete"] is True, result
