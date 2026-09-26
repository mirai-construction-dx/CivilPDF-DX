"""Tests for scripts/editor-asset-watch.sh (stubbed checker, alert and docker)."""

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "editor-asset-watch.sh"

# The watch script runs only on the Linux production host (systemd monitor timer).
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux-host ops script (bash + POSIX paths)"
)

_ALERT_FAIL = "[CivilPDF-DX] PDF Editor 配布リンク異常"
_ALERT_RECOVER = "[CivilPDF-DX] PDF Editor 配布リンク復旧"
_ALERT_ERROR = "[CivilPDF-DX] PDF Editor 配布リンク検査の実行失敗"


def _write_exec(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "state"
    alerts = tmp_path / "alerts.log"
    checker_args = tmp_path / "checker_args"
    rc_file = tmp_path / "checker_rc"
    rc_file.write_text("0")
    alert_rc = tmp_path / "alert_rc"
    alert_rc.write_text("0")
    # Fake "python": records its arguments and exits with the configured rc.
    fake_python = _write_exec(
        tmp_path / "fake-python",
        f'echo "$@" > "{checker_args}"; echo "[FAIL] x — HTTP 404"\n'
        f'exit "$(cat "{rc_file}")"\n',
    )
    fake_alert = _write_exec(
        tmp_path / "fake-alert",
        f'echo "$1" >> "{alerts}"; exit "$(cat "{alert_rc}")"\n',
    )
    base = {
        **os.environ,
        "CIVILPDF_MONITOR_STATE": str(state),
        "CIVILPDF_PYTHON": str(fake_python),
        "CIVILPDF_ALERT_NOTIFY": str(fake_alert),
        # Never read the real production container during tests.
        "CIVILPDF_BACKEND_CONTAINER": "civilpdf-test-no-such-container",
        "APPS_RELEASE_BASE_URL": "https://example.test/releases/download/editor-v0",
    }
    return {
        "env": base,
        "tmp": tmp_path,
        "alerts": alerts,
        "rc_file": rc_file,
        "alert_rc": alert_rc,
        "checker_args": checker_args,
        "state": state,
    }


def _run(e, *args):
    return subprocess.run(
        ["bash", str(_SCRIPT), *args], env=e["env"], capture_output=True, timeout=30
    )


def _alerts(e) -> list[str]:
    return e["alerts"].read_text().splitlines() if e["alerts"].exists() else []


def _next_check_in_minutes(e) -> float:
    ts = int((e["state"] / "editor_assets_next_check_ts").read_text())
    return (ts - time.time()) / 60


def test_healthy_links_send_no_alert(env):
    assert _run(env, "--force").returncode == 0
    assert _alerts(env) == []
    assert _next_check_in_minutes(env) > 60 * 23  # next real check in ~1 day


def test_failure_alerts_once_then_recovery_alerts_once(env):
    env["rc_file"].write_text("1")
    assert _run(env, "--force").returncode == 0  # never fails the monitor
    assert _run(env, "--force").returncode == 0
    assert _alerts(env) == [_ALERT_FAIL]

    env["rc_file"].write_text("0")
    _run(env, "--force")
    _run(env, "--force")
    assert _alerts(env) == [_ALERT_FAIL, _ALERT_RECOVER]


def test_interval_guard_skips_repeated_checks(env):
    env["rc_file"].write_text("1")
    _run(env)  # first run checks and alerts
    (env["state"] / "editor_assets_failing").unlink()
    _run(env)  # within the interval: no check, so no second alert
    assert len(_alerts(env)) == 1


def test_unconfigured_base_url_retries_soon_instead_of_next_day(env):
    env["env"].pop("APPS_RELEASE_BASE_URL")
    env["rc_file"].write_text("1")
    assert _run(env).returncode == 0
    assert _alerts(env) == []
    assert "skipped" in (env["state"] / "monitor.log").read_text()
    assert 50 < _next_check_in_minutes(env) <= 60


def test_failed_alert_delivery_is_retried(env):
    env["rc_file"].write_text("1")
    env["alert_rc"].write_text("1")  # e.g. SMTP failure
    _run(env, "--force")
    assert not (env["state"] / "editor_assets_failing").exists()
    env["alert_rc"].write_text("0")
    _run(env, "--force")
    assert _alerts(env) == [_ALERT_FAIL, _ALERT_FAIL]
    assert (env["state"] / "editor_assets_failing").exists()


def test_checker_crash_is_reported_as_execution_failure(env):
    env["rc_file"].write_text("2")  # argparse / import error, not a 404
    _run(env, "--force")
    assert _alerts(env) == [_ALERT_ERROR]


def test_corrupt_state_file_does_not_stop_the_watch(env):
    env["state"].mkdir(parents=True)
    (env["state"] / "editor_assets_next_check_ts").write_text("abc")
    env["rc_file"].write_text("1")
    _run(env)
    assert _alerts(env) == [_ALERT_FAIL]


def test_uses_base_url_and_filenames_from_running_container(env):
    bindir = env["tmp"] / "bin"
    bindir.mkdir()
    _write_exec(
        bindir / "docker",
        'case "$1" in\n'
        "  inspect) echo PATH=/usr/bin; "
        "echo APPS_RELEASE_BASE_URL=https://prod.test/editor-v9 ;;\n"
        "  exec) echo 'CivilPDF.Editor_9.0.0_x64-setup.exe,CivilPDF.Editor_9.0.0.msi' ;;\n"
        "esac\n",
    )
    env["env"]["PATH"] = f"{bindir}{os.pathsep}{env['env']['PATH']}"
    env["env"]["APPS_RELEASE_BASE_URL"] = "https://ignored.test/x"
    _run(env, "--force")
    args = env["checker_args"].read_text()
    assert "--base-url https://prod.test/editor-v9" in args
    assert (
        "--filenames CivilPDF.Editor_9.0.0_x64-setup.exe,CivilPDF.Editor_9.0.0.msi"
        in args
    )
