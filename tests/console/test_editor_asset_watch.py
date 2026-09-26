"""Tests for scripts/editor-asset-watch.sh (stubbed checker and alert command)."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "editor-asset-watch.sh"


def _write_exec(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "state"
    alerts = tmp_path / "alerts.log"
    rc_file = tmp_path / "checker_rc"
    rc_file.write_text("0")
    # Fake "python": ignores the script path and exits with the configured rc.
    fake_python = _write_exec(
        tmp_path / "fake-python",
        f'echo "[FAIL] win-msi — HTTP 404"; exit "$(cat {rc_file})"\n',
    )
    fake_alert = _write_exec(tmp_path / "fake-alert", f'echo "$1" >> {alerts}\n')
    base = {
        **os.environ,
        "CIVILPDF_MONITOR_STATE": str(state),
        "CIVILPDF_PYTHON": str(fake_python),
        "CIVILPDF_ALERT_NOTIFY": str(fake_alert),
        # Never read the real production container during tests.
        "CIVILPDF_BACKEND_CONTAINER": "civilpdf-test-no-such-container",
        "APPS_RELEASE_BASE_URL": "https://example.test/releases/download/editor-v0",
    }
    return {"env": base, "alerts": alerts, "rc_file": rc_file, "state": state}


def _run(e, *args):
    return subprocess.run(
        ["bash", str(_SCRIPT), *args], env=e["env"], capture_output=True, timeout=30
    )


def _alerts(e) -> list[str]:
    return e["alerts"].read_text().splitlines() if e["alerts"].exists() else []


def test_healthy_links_send_no_alert(env):
    assert _run(env, "--force").returncode == 0
    assert _alerts(env) == []


def test_failure_alerts_once_then_recovery_alerts_once(env):
    env["rc_file"].write_text("1")
    assert _run(env, "--force").returncode == 0  # never fails the monitor
    assert _run(env, "--force").returncode == 0
    assert _alerts(env) == ["[CivilPDF-DX] PDF Editor 配布リンク異常"]

    env["rc_file"].write_text("0")
    _run(env, "--force")
    _run(env, "--force")
    assert _alerts(env) == [
        "[CivilPDF-DX] PDF Editor 配布リンク異常",
        "[CivilPDF-DX] PDF Editor 配布リンク復旧",
    ]


def test_interval_guard_skips_repeated_checks(env):
    env["rc_file"].write_text("1")
    _run(env)  # first run checks and alerts
    (env["state"] / "editor_assets_failing").unlink()
    _run(env)  # within the interval: no check, so no second alert
    assert len(_alerts(env)) == 1


def test_unconfigured_base_url_is_skipped(env):
    env["env"].pop("APPS_RELEASE_BASE_URL")
    env["rc_file"].write_text("1")
    assert _run(env, "--force").returncode == 0
    assert _alerts(env) == []
    assert "skipped" in (env["state"] / "monitor.log").read_text()
