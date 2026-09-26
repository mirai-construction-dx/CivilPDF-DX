"""Contract test: docs/deployment/app-distribution.md must match the apps API.

The operations doc drifted once (it kept advertising Electron-era win-zip /
mac-pkg / ent-intune packages and a fictional v2.4.1 after the API moved to the
real Tauri v2 release). These tests fail CI when the doc and api/apps.py diverge.
"""

import re
from pathlib import Path

from api.apps import _PENDING_PLATFORMS, _VERSION, _build_packages

_DOC = (
    Path(__file__).resolve().parents[2] / "docs" / "deployment" / "app-distribution.md"
)


def _doc_text() -> str:
    return _DOC.read_text(encoding="utf-8")


def _documented_package_ids() -> set[str]:
    line = next(
        (ln for ln in _doc_text().splitlines() if ln.startswith("`package_id`:")),
        None,
    )
    assert line is not None, "package_id list line is missing from the doc"
    return set(re.findall(r"`([a-z][a-z0-9-]*)`", line.split(":", 1)[1]))


def test_documented_package_ids_match_api():
    assert _documented_package_ids() == {p.id for p in _build_packages()}


def test_documented_filenames_match_api():
    text = _doc_text()
    for pkg in _build_packages():
        assert f"`{pkg.filename}`" in text, f"{pkg.id}: {pkg.filename} not in doc"


def test_doc_references_current_version_only():
    text = _doc_text()
    assert f"v{_VERSION}" in text
    # Fictional Electron-era version must not reappear.
    assert "2.4.1" not in text


def test_doc_declares_pending_platforms_from_api():
    text = _doc_text()
    lines = text.splitlines()
    for p in _PENDING_PLATFORMS:
        # The OS table must mark each pending platform on a single row.
        assert any(p.label in ln and "後日対応" in ln for ln in lines), p.label
