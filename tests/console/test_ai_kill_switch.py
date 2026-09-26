"""The admin AI kill switch (ai_settings.enabled) must gate every AI call.

Regression: the flag was stored but never checked, so a configured API key
alone kept AI calls going out even after an admin turned AI off.
"""

from unittest.mock import MagicMock, patch

import pytest

from services import ai_settings as ai_settings_service


@pytest.fixture
def headers(client, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def doc_id(db_session, admin_user):
    from models.document import Document, DocumentStatus, DocumentType
    from models.user import Project

    project = Project(name="KS", code="KS-001")
    db_session.add(project)
    db_session.flush()
    doc = Document(
        title="ks.pdf",
        filename="ks.pdf",
        file_size=10,
        document_type=DocumentType.DRAWING,
        status=DocumentStatus.DRAFT,
        project_id=project.id,
        owner_id=admin_user.id,
        ocr_text="平面図",
        tags=[],
        extra_data={},
    )
    db_session.add(doc)
    db_session.commit()
    return doc.id


def _set_enabled(db_session, enabled: bool) -> None:
    row = ai_settings_service.get_ai_setting_row(db_session)
    row.enabled = enabled
    db_session.commit()


def test_disabled_by_default_blocks_ai_even_with_env_key(
    client, headers, doc_id, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    with patch("anthropic.Anthropic") as sdk:
        resp = client.post(f"/api/v1/ai/documents/{doc_id}/classify", headers=headers)
    assert resp.status_code == 503
    assert "無効化" in resp.json()["detail"]
    sdk.assert_not_called()


@pytest.mark.parametrize("path", ["classify", "extract", "summary"])
def test_every_ai_endpoint_honours_the_switch(
    client, headers, doc_id, db_session, monkeypatch, path
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    _set_enabled(db_session, False)
    method = client.get if path == "summary" else client.post
    with patch("anthropic.Anthropic") as sdk:
        resp = method(f"/api/v1/ai/documents/{doc_id}/{path}", headers=headers)
    assert resp.status_code == 503
    sdk.assert_not_called()


def test_enabled_without_key_reports_missing_key(
    client, headers, doc_id, db_session, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _set_enabled(db_session, True)
    with patch.object(ai_settings_service.settings, "anthropic_api_key", ""):
        resp = client.post(f"/api/v1/ai/documents/{doc_id}/classify", headers=headers)
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_semantic_search_does_not_call_ai_when_disabled(
    client, headers, db_session, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    _set_enabled(db_session, False)
    with patch("anthropic.Anthropic") as sdk:
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=headers,
        )
        suggest = client.get(
            "/api/v1/search/documents/suggest", params={"q": "橋梁"}, headers=headers
        )
    assert resp.status_code == 200 and resp.json()["expanded_terms"] == ["橋梁"]
    assert suggest.json() == ["橋梁"]
    sdk.assert_not_called()


def test_semantic_search_uses_configured_key_when_enabled(
    client, headers, db_session, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ai_settings_service.update_ai_setting(
        db_session, enabled=True, model_name="claude-expensive-model"
    )
    message = MagicMock()
    message.content = [MagicMock(text='["橋梁", "橋"]')]
    with (
        patch.object(ai_settings_service, "get_api_key", return_value="sk-db-key"),
        patch("anthropic.Anthropic") as sdk,
    ):
        sdk.return_value.messages.create.return_value = message
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=headers,
        )
    assert resp.json()["expanded_terms"] == ["橋梁", "橋"]
    sdk.assert_called_once_with(api_key="sk-db-key")
    # Query expansion stays on the cheap model regardless of the admin setting.
    assert sdk.return_value.messages.create.call_args.kwargs["model"] == (
        "claude-haiku-4-5-20251001"
    )


def test_enabled_without_key_keeps_search_on_the_original_query(
    client, headers, db_session, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _set_enabled(db_session, True)
    with (
        patch.object(ai_settings_service.settings, "anthropic_api_key", ""),
        patch("anthropic.Anthropic") as sdk,
    ):
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=headers,
        )
    assert resp.json()["expanded_terms"] == ["橋梁"]
    sdk.assert_not_called()


def test_unreadable_settings_fail_closed_without_breaking_the_request(
    client, headers, db_session, monkeypatch
):
    """A DB error while reading the switch must not leave the session aborted.

    Regression guard: without a rollback the following search queries on the
    same session failed and the endpoint returned 500.
    """
    from sqlalchemy import text

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    db_session.execute(text("DROP TABLE ai_settings"))
    db_session.commit()
    with patch("anthropic.Anthropic") as sdk:
        resp = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["expanded_terms"] == ["橋梁"]
    sdk.assert_not_called()


def test_request_paths_do_not_create_the_settings_row(client, headers, db_session):
    from models.ai_setting import AiSetting

    client.get(
        "/api/v1/search/documents",
        params={"q": "橋梁", "mode": "semantic"},
        headers=headers,
    )
    assert db_session.query(AiSetting).count() == 0


def test_read_error_rolls_back_the_session_and_fails_closed():
    """On PostgreSQL a failed statement aborts the transaction; the lookup must
    roll back so the caller's next query (e.g. the search itself) still runs.
    SQLite does not abort, so this is asserted directly on the session.
    """
    from sqlalchemy.exc import OperationalError

    db = MagicMock()
    db.query.side_effect = OperationalError("SELECT", {}, Exception("aborted"))
    assert ai_settings_service.is_ai_enabled(db) is False
    db.rollback.assert_called_once()
    assert ai_settings_service.get_model_name(db, "fallback") == "fallback"
