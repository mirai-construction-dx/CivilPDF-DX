"""Tests for scripts/check-editor-assets.py (no network: httpx.MockTransport)."""

import hashlib
import importlib.util
from pathlib import Path

import httpx
import pytest

from api.apps import _build_packages

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-editor-assets.py"
_BASE = "https://example.test/releases/download/editor-v0"


def _load():
    """Import the script by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("check_editor_assets", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def script():
    return _load()


def test_all_packages_reachable(script, capsys):
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(200)

    assert script.run(_BASE, _client(handler)) == 0
    expected = {("HEAD", f"{_BASE}/{p.filename}") for p in _build_packages()}
    assert set(seen) == expected
    assert capsys.readouterr().out.count("[PASS]") == len(expected)


def test_missing_asset_fails(script, capsys):
    def handler(request):
        return httpx.Response(404 if request.url.path.endswith(".msi") else 200)

    assert script.run(_BASE, _client(handler)) == 1
    out = capsys.readouterr().out
    assert "[FAIL] win-msi" in out and "HTTP 404" in out


def test_network_error_is_reported_not_raised(script, capsys):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    assert script.run(_BASE, _client(handler)) == 1
    assert "request failed: ConnectError" in capsys.readouterr().out


def test_sha256_verified_when_configured(script, monkeypatch, capsys):
    payload = b"installer-bytes"
    good = hashlib.sha256(payload).hexdigest()
    monkeypatch.setenv("APPS_SHA256_WIN_EXE", good)
    monkeypatch.setenv("APPS_SHA256_WIN_MSI", "0" * 64)

    def handler(request):
        return httpx.Response(200, content=b"" if request.method == "HEAD" else payload)

    assert script.run(_BASE, _client(handler), verify_sha256=True) == 1
    out = capsys.readouterr().out
    assert "[PASS] win-exe" in out
    assert "[FAIL] win-msi" in out and "sha256 mismatch" in out


def test_get_error_during_sha256_is_reported_not_raised(script, monkeypatch, capsys):
    monkeypatch.setenv("APPS_SHA256_WIN_EXE", "0" * 64)

    def handler(request):
        if request.method == "GET":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200)

    assert script.run(_BASE, _client(handler), verify_sha256=True) == 1
    assert "[FAIL] win-exe" in capsys.readouterr().out


def test_get_non_200_is_not_a_checksum_mismatch(script, monkeypatch, capsys):
    monkeypatch.setenv("APPS_SHA256_WIN_EXE", "0" * 64)

    def handler(request):
        return httpx.Response(200 if request.method == "HEAD" else 403)

    assert script.run(_BASE, _client(handler), verify_sha256=True) == 1
    out = capsys.readouterr().out
    assert "GET HTTP 403" in out and "sha256 mismatch" not in out


def test_unconfigured_sha256_is_flagged_in_pass_line(script, monkeypatch, capsys):
    monkeypatch.delenv("APPS_SHA256_WIN_EXE", raising=False)
    monkeypatch.delenv("APPS_SHA256_WIN_MSI", raising=False)
    assert script.run(_BASE, _client(lambda r: httpx.Response(200)), True) == 0
    assert capsys.readouterr().out.count("(sha256 not configured)") == 2


def test_redirect_to_asset_cdn_is_followed(script):
    def handler(request):
        if request.url.host == "example.test":
            return httpx.Response(302, headers={"location": "https://cdn.test/a"})
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    assert script.run(_BASE, client) == 0


def test_main_strips_trailing_slash_and_checks(script, monkeypatch):
    calls = []

    def fake_run(base_url, client, verify_sha256=False, packages=None):
        calls.append(base_url)
        return 0

    monkeypatch.setattr(script, "run", fake_run)
    assert script.main(["--base-url", _BASE + "/"]) == 0
    assert calls == [_BASE]


def test_non_https_base_url_rejected(script):
    assert script.main(["--base-url", "http://example.test/x"]) == 1


def test_unset_base_url_skips(script, monkeypatch):
    monkeypatch.delenv("APPS_RELEASE_BASE_URL", raising=False)
    assert script.main([]) == 3


def test_explicit_filenames_override_checkout_list(script):
    seen = []

    def handler(request):
        seen.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200)

    pkgs = script.packages_from_filenames(["old_1.0.0.exe", "old_1.0.0.msi"])
    assert script.run(_BASE, _client(handler), packages=pkgs) == 0
    assert seen == ["old_1.0.0.exe", "old_1.0.0.msi"]
