"""Environment gate for direct AI Provider calls (ADR-0007).

Every direct Anthropic call — document classify / extract / summary, search
query expansion and the admin connection test — goes through one gate,
``services.ai_settings.direct_call_allowed``. It allows a call only when the
explicit flag ``AI_DIRECT_CALL_ALLOWED`` is true *and* ``ENVIRONMENT`` is a
non-production value (development / test / local). Production, staging and any
unknown or empty environment are refused even with the flag, the kill switch
and an API key all present.

The matrix below crosses environment x API key x flag and asserts that no
outbound SDK call is made whenever the gate refuses. The suite-wide defaults
(``ENVIRONMENT=test``, flag on) come from conftest.py; each test overrides them.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from services import ai_settings as ai_settings_service

REFUSED_ENVIRONMENTS = [
    "production",
    "staging",
    "Production",
    " staging ",
    "prod",
    "",
    "unknown",
]
ALLOWED_ENVIRONMENTS = ["development", "test", "local"]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def headers(client, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def doc_id(db_session, admin_user):
    from models.document import Document, DocumentStatus, DocumentType
    from models.user import Project

    project = Project(name="ENV", code="ENV-001")
    db_session.add(project)
    db_session.flush()
    doc = Document(
        title="env.pdf",
        filename="env.pdf",
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


def _configure(monkeypatch, db_session, *, environment, flag, key):
    """Kill switch ON, then set environment / flag / key for one case."""
    ai_settings_service.update_ai_setting(db_session, enabled=True)
    monkeypatch.setattr(ai_settings_service.settings, "environment", environment)
    monkeypatch.setattr(ai_settings_service.settings, "ai_direct_call_allowed", flag)
    monkeypatch.setattr(ai_settings_service.settings, "anthropic_api_key", "")
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _ok_message(
    text='{"drawing_type": "平面図", "project_type": "建築", "confidence": 0.9}',
):
    message = MagicMock()
    message.content = [MagicMock(text=text)]
    return message


def _call_all(client, headers, doc_id):
    """Hit every endpoint that can make a direct call; return the responses."""
    return {
        "classify": client.post(
            f"/api/v1/ai/documents/{doc_id}/classify", headers=headers
        ),
        "extract": client.post(
            f"/api/v1/ai/documents/{doc_id}/extract", headers=headers
        ),
        "summary": client.get(
            f"/api/v1/ai/documents/{doc_id}/summary", headers=headers
        ),
        "search": client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "semantic"},
            headers=headers,
        ),
        "suggest": client.get(
            "/api/v1/search/documents/suggest", params={"q": "橋梁"}, headers=headers
        ),
        "config_test": client.post("/api/v1/ai-config/test", headers=headers),
    }


# ── The gate function itself ─────────────────────────────────────────────────


@pytest.mark.parametrize("environment", REFUSED_ENVIRONMENTS)
@pytest.mark.parametrize("flag", [True, False])
def test_gate_refuses_production_like_environments(environment, flag):
    cfg = SimpleNamespace(environment=environment, ai_direct_call_allowed=flag)
    assert ai_settings_service.direct_call_allowed(cfg) is False


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
def test_gate_requires_the_explicit_flag(environment):
    off = SimpleNamespace(environment=environment, ai_direct_call_allowed=False)
    on = SimpleNamespace(environment=environment, ai_direct_call_allowed=True)
    assert ai_settings_service.direct_call_allowed(off) is False
    assert ai_settings_service.direct_call_allowed(on) is True


@pytest.mark.parametrize("value", ["true", "1", "yes", None, 1])
def test_gate_accepts_only_a_real_boolean_true(value):
    """A truthy non-bool (e.g. a raw string that bypassed parsing) is refused."""
    cfg = SimpleNamespace(environment="development", ai_direct_call_allowed=value)
    assert ai_settings_service.direct_call_allowed(cfg) is False


def test_gate_fails_closed_on_unreadable_configuration():
    class Broken:
        @property
        def ai_direct_call_allowed(self):
            raise RuntimeError("boom")

    assert ai_settings_service.direct_call_allowed(Broken()) is False
    assert ai_settings_service.direct_call_allowed(SimpleNamespace()) is False


def test_flag_defaults_to_false(monkeypatch):
    monkeypatch.delenv("AI_DIRECT_CALL_ALLOWED", raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.ai_direct_call_allowed is False
    assert ai_settings_service.direct_call_allowed(cfg) is False


# ── End to end: environment x key x flag → no outbound call ──────────────────


@pytest.mark.parametrize("environment", ["production", "staging", "unknown"])
@pytest.mark.parametrize("key", [True, False])
@pytest.mark.parametrize("flag", [True, False])
def test_no_outbound_call_in_production_like_environments(
    client, headers, doc_id, db_session, monkeypatch, environment, key, flag
):
    _configure(monkeypatch, db_session, environment=environment, flag=flag, key=key)
    with (
        patch("anthropic.Anthropic") as sdk,
        patch("api.ai_settings.anthropic.Anthropic") as config_sdk,
    ):
        resp = _call_all(client, headers, doc_id)

    sdk.assert_not_called()
    config_sdk.assert_not_called()
    for name in ("classify", "extract", "summary", "config_test"):
        assert resp[name].status_code == 503, name
        assert "ADR-0007" in resp[name].json()["detail"], name
    assert resp["search"].status_code == 200
    assert resp["search"].json()["expanded_terms"] == ["橋梁"]
    assert resp["suggest"].json() == ["橋梁"]


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
@pytest.mark.parametrize("key", [True, False])
def test_no_outbound_call_without_the_flag(
    client, headers, doc_id, db_session, monkeypatch, environment, key
):
    _configure(monkeypatch, db_session, environment=environment, flag=False, key=key)
    with (
        patch("anthropic.Anthropic") as sdk,
        patch("api.ai_settings.anthropic.Anthropic") as config_sdk,
    ):
        resp = _call_all(client, headers, doc_id)

    sdk.assert_not_called()
    config_sdk.assert_not_called()
    for name in ("classify", "extract", "summary", "config_test"):
        assert resp[name].status_code == 503, name
    assert resp["search"].json()["expanded_terms"] == ["橋梁"]


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
def test_no_outbound_call_without_a_key_even_when_allowed(
    client, headers, doc_id, db_session, monkeypatch, environment
):
    _configure(monkeypatch, db_session, environment=environment, flag=True, key=False)
    with (
        patch("anthropic.Anthropic") as sdk,
        patch("api.ai_settings.anthropic.Anthropic") as config_sdk,
    ):
        resp = _call_all(client, headers, doc_id)

    sdk.assert_not_called()
    config_sdk.assert_not_called()
    assert resp["classify"].status_code == 503
    assert "ANTHROPIC_API_KEY" in resp["classify"].json()["detail"]
    assert resp["config_test"].json()["ok"] is False


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
def test_calls_go_out_only_when_flag_key_and_environment_allow(
    client, headers, doc_id, db_session, monkeypatch, environment
):
    _configure(monkeypatch, db_session, environment=environment, flag=True, key=True)
    with patch("anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = _ok_message()
        resp = client.post(f"/api/v1/ai/documents/{doc_id}/classify", headers=headers)
    assert resp.status_code == 200
    sdk.assert_called_once_with(api_key="sk-test-not-used")


def test_kill_switch_still_applies_when_the_environment_allows(
    client, headers, doc_id, db_session, monkeypatch
):
    """The environment gate is added in front of the kill switch, not instead of it."""
    _configure(monkeypatch, db_session, environment="development", flag=True, key=True)
    ai_settings_service.update_ai_setting(db_session, enabled=False)
    with patch("anthropic.Anthropic") as sdk:
        resp = client.post(f"/api/v1/ai/documents/{doc_id}/classify", headers=headers)
    assert resp.status_code == 503
    assert "無効化" in resp.json()["detail"]
    sdk.assert_not_called()


def test_environment_gate_is_checked_before_document_text_is_read(
    client, headers, doc_id, db_session, monkeypatch
):
    _configure(monkeypatch, db_session, environment="production", flag=True, key=True)
    with (
        patch("api.ai._get_document_text") as read_text,
        patch("anthropic.Anthropic") as sdk,
    ):
        resp = client.post(f"/api/v1/ai/documents/{doc_id}/classify", headers=headers)
    assert resp.status_code == 503
    read_text.assert_not_called()
    sdk.assert_not_called()


def test_connection_test_refused_in_production_before_reading_the_key(
    client, headers, db_session, monkeypatch
):
    _configure(monkeypatch, db_session, environment="production", flag=True, key=True)
    with (
        patch.object(ai_settings_service, "get_api_key") as get_key,
        patch("api.ai_settings.anthropic.Anthropic") as sdk,
    ):
        resp = client.post("/api/v1/ai-config/test", headers=headers)
    assert resp.status_code == 503
    get_key.assert_not_called()
    sdk.assert_not_called()


# ── Deployment definitions must not opt production / staging in ──────────────


def test_production_and_staging_definitions_do_not_set_the_flag():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    candidates = [
        "docker-compose.prod.yml",
        "docker-compose.staging.yml",
        "deploy/civilpdf-backend.service",
        "deploy/civilpdf-stg.service",
        "deploy/civilpdf.env.example",
        ".env.prod.example",
        ".env.stg.example",
    ]
    checked = 0
    for name in candidates:
        path = root / name
        if not path.exists():
            continue
        checked += 1
        assert "AI_DIRECT_CALL_ALLOWED" not in path.read_text(encoding="utf-8"), name
    assert checked > 0
