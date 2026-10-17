"""Adversarial regressions for integration signing and fail-closed behavior."""

import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from config import Settings, settings
from services import service_auth
from tests.console.test_integration_api import SECRET, SYSTEM, _headers

PATH = "/api/v1/integration/ping"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "integration_hmac_secrets", {SYSTEM: SECRET})
    monkeypatch.setattr(settings, "integration_nonce_redis_url", "redis://test-only")


@pytest.mark.parametrize(
    "header,value",
    [
        ("X-CivilPDF-Timestamp", "9" * 400),
        ("X-CivilPDF-Timestamp", "2026-01-01"),
        ("X-CivilPDF-Nonce", "n" * 10000),
        ("X-CivilPDF-Nonce", "bad"),
        ("X-CivilPDF-Signature", "z" * 64),
        ("X-CivilPDF-Signature", "0" * 10000),
    ],
)
def test_malformed_headers_are_401(client, configured, header, value):
    headers = _headers("GET", PATH)
    headers[header] = value
    assert client.get(PATH, headers=headers).status_code == 401


def test_missing_redis_is_disabled(client, configured, monkeypatch):
    monkeypatch.setattr(settings, "integration_nonce_redis_url", "")
    assert client.get(PATH, headers=_headers("GET", PATH)).status_code == 503


def test_redis_outage_is_fail_closed(client, configured, monkeypatch):
    async def unavailable(*args):
        raise RedisConnectionError("unavailable")

    monkeypatch.setattr(service_auth, "_consume_nonce", unavailable)
    assert client.get(PATH, headers=_headers("GET", PATH)).status_code == 503


def test_malformed_redis_url_is_fail_closed(client, configured, monkeypatch):
    monkeypatch.setattr(settings, "integration_nonce_redis_url", "not-a-url")
    assert client.get(PATH, headers=_headers("GET", PATH)).status_code == 503


def test_invalid_config_error_hides_secret_values():
    dummy = "must-not-appear-in-error-output"
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None, integration_hmac_secrets={SYSTEM: dummy})
    assert dummy not in str(error.value)


def test_shared_quota_rejects_calls(client, configured, monkeypatch):
    async def full(*args):
        return -1

    monkeypatch.setattr(service_auth, "_consume_nonce", full)
    assert client.get(PATH, headers=_headers("GET", PATH)).status_code == 429


def test_get_body_rejected_before_auth_store(client, configured):
    response = client.request(
        "GET", PATH, headers=_headers("GET", PATH), content=b"x" * 10000
    )
    assert response.status_code == 413


def test_query_tampering_rejected(client, configured):
    assert (
        client.get(PATH + "?project=other", headers=_headers("GET", PATH)).status_code
        == 400
    )


def test_identity_is_signed(client, configured, monkeypatch):
    # Even if an operator bypasses config validation and reuses a secret,
    # changing only the system header cannot impersonate another caller.
    monkeypatch.setattr(
        settings, "integration_hmac_secrets", {SYSTEM: SECRET, "other-peer": SECRET}
    )
    headers = _headers("GET", PATH)
    headers["X-CivilPDF-System"] = "other-peer"
    assert client.get(PATH, headers=headers).status_code == 401


def test_future_signature_nonce_retained_to_signed_expiry(
    client, configured, monkeypatch
):
    now = int(time.time())
    monkeypatch.setattr(service_auth.time, "time", lambda: now)
    stored = []

    async def consume(peer, nonce, current, expires, window):
        stored.append(expires)
        return 1

    monkeypatch.setattr(service_auth, "_consume_nonce", consume)
    assert (
        client.get(PATH, headers=_headers("GET", PATH, timestamp=now + 299)).status_code
        == 200
    )
    assert stored == [now + 600]


@pytest.mark.parametrize(
    "values", [{SYSTEM: "short"}, {SYSTEM: SECRET, "other": SECRET}]
)
def test_invalid_peer_configuration_is_rejected(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, integration_hmac_secrets=values)


@pytest.mark.parametrize("window", [0, -1, 301])
def test_invalid_skew_is_rejected(window):
    with pytest.raises(ValueError):
        Settings(_env_file=None, integration_clock_skew_seconds=window)
