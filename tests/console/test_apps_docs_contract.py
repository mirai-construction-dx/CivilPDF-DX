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
    # Every x.y.z in the doc must be the current release, so a version bump
    # that forgets the doc (or the Electron-era 2.4.1) fails here.
    assert set(re.findall(r"\b\d+\.\d+\.\d+\b", text)) == {_VERSION}


def test_doc_points_to_editor_release_tag_of_this_repo():
    text = _doc_text()
    base = (
        "https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/"
        f"editor-v{_VERSION}"
    )
    assert base in text
    # The old private-repo location 404s and must not be advertised again.
    assert "Kensan196948G/CivilPDF-Editor" not in text


def test_doc_declares_pending_platforms_from_api():
    text = _doc_text()
    table_rows = [ln for ln in text.splitlines() if ln.startswith("|")]
    for p in _PENDING_PLATFORMS:
        # The OS table must mark each pending platform on a single table row.
        assert any(p.label in r and "後日対応" in r for r in table_rows), p.label
    # Distributed platforms must not be marked pending in the table.
    assert not any("Windows" in r and "後日対応" in r for r in table_rows)
