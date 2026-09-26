"""Tests for scripts/pre-deploy-check.sh (temporary git repo + stubbed tools)."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pre-deploy-check.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux-host ops script (bash + POSIX paths)"
)

_SECRET = "super-secret-value-must-not-leak"


def _write_exec(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


# Isolate from the developer's git config (signing, hooks) and GIT_* env.
_GIT_ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env=_GIT_ENV
    )


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "user.email", "t@example.test")
    _git(work, "config", "user.name", "t")
    (work / "state.json").write_text("{}\n")
    (work / "VERSION").write_text("1.0.0\n")
    (work / "app.txt").write_text("v1\n")
    (work / "scripts").mkdir()
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")
    env_file = work / ".env"
    env_file.write_text(
        f"SECRET_KEY={_SECRET}\nAPP_VERSION=1.0.0\nAPPS_RELEASE_BASE_URL=\n"
    )
    env_file.chmod(0o600)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    images = tmp_path / "images"
    images.write_text("civilpdf-dx-backend:pre-1\ncivilpdf-dx-frontend:pre-1\n")
    _write_exec(bindir / "docker", f'[ "$1 $2" = "image ls" ] && cat "{images}"\n')
    hc_rc = tmp_path / "hc_rc"
    hc_rc.write_text("0")
    healthcheck = _write_exec(tmp_path / "hc", f'exit "$(cat "{hc_rc}")"\n')
    py_rc = tmp_path / "py_rc"
    py_rc.write_text("0")
    py_args = tmp_path / "py_args"
    fake_python = _write_exec(
        tmp_path / "py", f'env | grep APPS_ > "{py_args}"; exit "$(cat "{py_rc}")"\n'
    )
    env = {
        **_GIT_ENV,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "CIVILPDF_PROJECT_DIR": str(work),
        "CIVILPDF_HEALTHCHECK": str(healthcheck),
        "CIVILPDF_PYTHON": str(fake_python),
    }
    return {
        "bindir": bindir,
        "work": work,
        "env": env,
        "images": images,
        "hc_rc": hc_rc,
        "py_rc": py_rc,
        "py_args": py_args,
    }


def _run(r):
    return subprocess.run(
        ["bash", str(_SCRIPT)], env=r["env"], capture_output=True, text=True, timeout=60
    )


def test_all_checks_pass(repo):
    res = _run(repo)
    assert res.returncode == 0, res.stdout
    assert "0 fail, 0 warn" in res.stdout


def test_state_json_change_is_tolerated_but_other_changes_fail(repo):
    (repo["work"] / "state.json").write_text('{"hook": 1}\n')
    assert _run(repo).returncode == 0
    (repo["work"] / "app.txt").write_text("edited\n")
    res = _run(repo)
    assert res.returncode == 1
    assert "tracked changes besides state.json: app.txt" in res.stdout


def test_feature_branch_checkout_fails(repo):
    _git(repo["work"], "switch", "-q", "-c", "feature")
    res = _run(repo)
    assert res.returncode == 1
    assert "not main" in res.stdout


def test_head_behind_origin_fails(repo):
    (repo["work"] / "app.txt").write_text("v2\n")
    _git(repo["work"], "commit", "-q", "-am", "v2")
    _git(repo["work"], "push", "-q", "origin", "main")
    _git(repo["work"], "reset", "-q", "--hard", "HEAD~1")
    res = _run(repo)
    assert res.returncode == 1
    assert "!= origin/main" in res.stdout


def test_world_readable_env_fails(repo):
    (repo["work"] / ".env").chmod(0o644)
    res = _run(repo)
    assert res.returncode == 1
    assert "chmod 600 .env" in res.stdout


def test_failed_healthcheck_fails(repo):
    repo["hc_rc"].write_text("1")
    assert _run(repo).returncode == 1


def test_missing_rollback_tags_only_warn(repo):
    repo["images"].write_text("civilpdf-dx-backend:latest\n")
    res = _run(repo)
    assert res.returncode == 0
    assert "[WARN] no rollback tag for: backend frontend" in res.stdout


def test_installer_check_uses_apps_values_and_never_prints_secrets(repo):
    (repo["work"] / ".env").write_text(
        f"SECRET_KEY={_SECRET}\n"
        "APPS_RELEASE_BASE_URL=https://example.test/editor-v1\n"
        "APPS_SHA256_WIN_EXE=aaa\nAPPS_SHA256_WIN_MSI=bbb\n"
    )
    repo["py_rc"].write_text("1")
    res = _run(repo)
    assert res.returncode == 1
    assert "installer link/checksum check failed" in res.stdout
    passed = repo["py_args"].read_text()
    assert "APPS_SHA256_WIN_EXE=aaa" in passed and "APPS_SHA256_WIN_MSI=bbb" in passed
    assert _SECRET not in res.stdout + res.stderr
    assert _SECRET not in passed


def test_unreachable_origin_fails_instead_of_passing(repo):
    _git(repo["work"], "remote", "set-url", "origin", str(repo["work"] / "nope.git"))
    res = _run(repo)
    assert res.returncode == 1
    assert "could not read origin/main" in res.stdout


def test_path_with_space_is_reported_intact(repo):
    spaced = repo["work"] / "my file.txt"
    spaced.write_text("a\n")
    _git(repo["work"], "add", "my file.txt")
    _git(repo["work"], "commit", "-q", "-m", "spaced")
    _git(repo["work"], "push", "-q", "origin", "main")
    spaced.write_text("b\n")
    res = _run(repo)
    assert "tracked changes besides state.json: my file.txt" in res.stdout


def test_unusable_docker_is_reported_as_unchecked(repo):
    # e.g. user not in the docker group: `docker image ls` exits non-zero.
    _write_exec(repo["bindir"] / "docker", 'echo "permission denied" >&2; exit 1\n')
    res = _run(repo)
    assert res.returncode == 0
    assert "cannot list docker images" in res.stdout
    assert "no rollback tag for" not in res.stdout


@pytest.mark.parametrize(
    "line",
    [
        'APPS_RELEASE_BASE_URL="https://example.test/editor-v1"',
        "APPS_RELEASE_BASE_URL='https://example.test/editor-v1'\r",
        "export APPS_RELEASE_BASE_URL = https://example.test/editor-v1  ",
    ],
)
def test_env_value_is_normalized_like_compose(repo, line):
    (repo["work"] / ".env").write_text(f'{line}\nAPPS_SHA256_WIN_EXE="aaa"\n')
    (repo["work"] / ".env").chmod(0o600)
    res = _run(repo)
    assert "(https://example.test/editor-v1)" in res.stdout
    assert "APPS_SHA256_WIN_EXE=aaa\n" in repo["py_args"].read_text()


def test_checker_crash_is_distinguished_from_link_failure(repo):
    (repo["work"] / ".env").write_text("APPS_RELEASE_BASE_URL=https://example.test/x\n")
    (repo["work"] / ".env").chmod(0o600)
    repo["py_rc"].write_text("2")
    res = _run(repo)
    assert res.returncode == 1
    assert "check-editor-assets.py itself failed (rc=2" in res.stdout


def test_app_version_mismatch_fails(repo):
    (repo["work"] / ".env").write_text("APP_VERSION=0.9.0\n")
    (repo["work"] / ".env").chmod(0o600)
    res = _run(repo)
    assert res.returncode == 1
    assert "APP_VERSION in .env is '0.9.0' but VERSION is 1.0.0" in res.stdout
