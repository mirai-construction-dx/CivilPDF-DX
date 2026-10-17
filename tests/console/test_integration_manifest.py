"""Tests for scripts/verify-integration-manifest.py (ADR-0006).

The validator is a standalone stdlib script so it can run from the ops-checks CI
job without the backend dependencies. These tests exercise it through its CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-integration-manifest.py"
MANIFEST = ROOT / "infra" / "integration" / "system.json"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_repository_manifest_is_valid() -> None:
    result = run("--root", str(ROOT))
    assert result.returncode == 0, result.stderr
    assert "INTEGRATION MANIFEST: OK" in result.stdout


def test_version_drift_is_rejected(tmp_path: Path) -> None:
    mutated = tmp_path / "system.json"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["version"] = "0.0.0-drift"
    mutated.write_text(json.dumps(data), encoding="utf-8")

    result = run("--root", str(ROOT), "--manifest", str(mutated))
    assert result.returncode == 1
    assert "VERSION" in result.stderr


def test_unknown_interface_status_is_rejected(tmp_path: Path) -> None:
    mutated = tmp_path / "system.json"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["provides"][0]["status"] = "done"
    mutated.write_text(json.dumps(data), encoding="utf-8")

    result = run("--root", str(ROOT), "--manifest", str(mutated))
    assert result.returncode == 1
    assert "status" in result.stderr


def test_missing_contract_file_is_rejected(tmp_path: Path) -> None:
    mutated = tmp_path / "system.json"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["provides"][0]["contract"] = "docs/api/does-not-exist.md"
    mutated.write_text(json.dumps(data), encoding="utf-8")

    result = run("--root", str(ROOT), "--manifest", str(mutated))
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_production_identifier_leak_is_rejected(tmp_path: Path) -> None:
    """A staging manifest must not point at production identifiers."""
    manifest = tmp_path / "system.json"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    staging_ids = json.loads((ROOT / "infra/staging/identifiers.json").read_text(encoding="utf-8"))
    leaked = json.loads(json.dumps(staging_ids))
    leaked["tunnelName"] = leaked["production"]["tunnelName"]
    (tmp_path / "infra" / "staging").mkdir(parents=True)
    (tmp_path / "infra" / "staging" / "identifiers.json").write_text(
        json.dumps(leaked), encoding="utf-8"
    )
    (tmp_path / "VERSION").write_text((ROOT / "VERSION").read_text(encoding="utf-8"), encoding="utf-8")
    data["stagingIdentifiers"] = "infra/staging/identifiers.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = run("--root", str(tmp_path), "--manifest", str(manifest))
    assert result.returncode == 1
    assert "tunnelName" in result.stderr


def test_check_siblings_skips_missing_repositories(tmp_path: Path) -> None:
    """A locally missing sibling repository is a SKIP, never a failure."""
    manifest = tmp_path / "system.json"
    shutil.copy(MANIFEST, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["siblingChecks"] = [{"repo": "no-such-repo", "file": "systems.yaml"}]
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = run("--root", str(ROOT), "--manifest", str(manifest), "--check-siblings")
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
