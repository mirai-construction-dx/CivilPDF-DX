"""Tests for the app distribution API (releases, release notes, build info, downloads).

These assert that responses reflect the real CivilPDF-Editor v1.12.6 release
(Tauri v2, self-signed Windows code signing), redistributed from this repository's
GitHub Release tag editor-v1.12.6.
Distribution scope is Windows only; macOS is reported as pending (後日対応).
"""

# Real Tauri asset filenames of v1.12.6 (as listed in the upstream updater
# latest.json). GitHub replaces spaces with dots; the MSI is built for ja-JP.
# Download URLs are `{base}/{filename}`.
_BASE = (
    "https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/"
    "editor-v1.12.6"
)
_REAL_FILENAMES = {
    "win-exe": "CivilPDF.Editor_1.12.6_x64-setup.exe",
    "win-msi": "CivilPDF.Editor_1.12.6_x64_ja-JP.msi",
}
# Assets that exist on the GitHub Release but are intentionally not distributed.
_NOT_DISTRIBUTED = ("mac-dmg", "linux-deb", "linux-appimage", "linux-rpm")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestReleases:
    def test_releases_structure(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["stable_version"] == "v1.12.6"
        assert isinstance(data["packages"], list)
        assert isinstance(data["channels"], list)
        # Only the stable channel exists.
        assert len(data["channels"]) == 1
        assert data["channels"][0]["id"] == "stable"
        assert data["channels"][0]["version"] == "v1.12.6"
        # user_count is not measured, so it is reported as 0 (no fabrication).
        assert data["channels"][0]["user_count"] == 0

    def test_releases_include_all_real_packages(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        ids = {p["id"] for p in resp.json()["packages"]}
        # Windows-only distribution: exactly the two real Windows installers.
        assert ids == {"win-exe", "win-msi"}
        assert {p["platform"] for p in resp.json()["packages"]} == {"windows"}

    def test_no_fabricated_packages(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        ids = {p["id"] for p in resp.json()["packages"]}
        # These were fabricated (Tauri does not produce them) and must be gone.
        assert {"win-zip", "mac-pkg", "ent-intune"}.isdisjoint(ids)

    def test_real_filenames_and_version(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        by_id = {p["id"]: p for p in resp.json()["packages"]}
        for pkg_id, filename in _REAL_FILENAMES.items():
            assert by_id[pkg_id]["filename"] == filename
            # version field reports the release version, not the filename fragment.
            assert by_id[pkg_id]["version"] == "1.12.6"

    def test_macos_reported_as_pending(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        pending = resp.json()["pending_platforms"]
        assert [p["platform"] for p in pending] == ["macos"]
        assert pending[0]["status"] == "pending"
        assert "後日対応" in pending[0]["note"]

    def test_windows_msi_metadata(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        pkg = next(p for p in resp.json()["packages"] if p["id"] == "win-msi")
        assert pkg["platform"] == "windows"
        assert pkg["format"] == "msi"
        assert pkg["filename"].endswith(".msi")

    def test_non_windows_packages_not_distributed(self, client, admin_token):
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        ids = {p["id"] for p in resp.json()["packages"]}
        assert ids.isdisjoint(_NOT_DISTRIBUTED)

    def test_packages_unavailable_without_base_url(
        self, client, admin_token, monkeypatch
    ):
        monkeypatch.delenv("APPS_RELEASE_BASE_URL", raising=False)
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        assert all(p["available"] is False for p in resp.json()["packages"])

    def test_packages_available_with_base_url(self, client, admin_token, monkeypatch):
        monkeypatch.setenv("APPS_RELEASE_BASE_URL", _BASE)
        resp = client.get("/api/v1/apps/releases", headers=_auth(admin_token))
        assert all(p["available"] is True for p in resp.json()["packages"])

    def test_releases_requires_auth(self, client):
        resp = client.get("/api/v1/apps/releases")
        assert resp.status_code == 401


class TestReleaseNotes:
    def test_all_notes(self, client, admin_token):
        resp = client.get("/api/v1/apps/release-notes", headers=_auth(admin_token))
        assert resp.status_code == 200
        notes = resp.json()["notes"]
        assert len(notes) == 1
        first = notes[0]
        assert first["version"] == "1.12.6"
        assert first["channel"] == "stable"
        assert all("type" in i and "text" in i for i in first["items"])

    def test_notes_describe_real_features(self, client, admin_token):
        resp = client.get("/api/v1/apps/release-notes", headers=_auth(admin_token))
        texts = " ".join(i["text"] for n in resp.json()["notes"] for i in n["items"])
        # Real features: PDF viewing (M1) and electronic seal (M2).
        assert "PDF 表示" in texts
        assert "電子印鑑" in texts
        # Carried-over text edit mode and v1.12 auto-update.
        assert "テキスト編集" in texts
        assert "自動更新" in texts
        # Honest disclosure: self-signed code signing still triggers SmartScreen.
        assert "自己署名" in texts
        assert "SmartScreen" in texts
        # Windows-only distribution is disclosed; no macOS Gatekeeper guidance.
        assert "Windows 版のみ" in texts
        assert "Gatekeeper" not in texts

    def test_notes_have_no_fabricated_content(self, client, admin_token):
        resp = client.get("/api/v1/apps/release-notes", headers=_auth(admin_token))
        blob = resp.text
        # Fabricated items from the old fake data must not reappear.
        for fake in ("CVE-2026-1234", "Teams", "2.4.1", "2.5.0", "OCR日本語縦書き"):
            assert fake not in blob

    def test_filter_by_channel(self, client, admin_token):
        resp = client.get(
            "/api/v1/apps/release-notes",
            params={"channel": "stable"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        notes = resp.json()["notes"]
        assert len(notes) == 1
        assert notes[0]["channel"] == "stable"

    def test_invalid_channel_rejected(self, client, admin_token):
        resp = client.get(
            "/api/v1/apps/release-notes",
            params={"channel": "beta"},
            headers=_auth(admin_token),
        )
        # beta is no longer a valid channel — only "stable" is accepted.
        assert resp.status_code == 422

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/apps/release-notes")
        assert resp.status_code == 401


class TestBuildInfo:
    def test_build_info_shape(self, client, admin_token):
        resp = client.get("/api/v1/apps/build-info", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "CivilPDF Editor Client"
        assert data["stable_version"] == "v1.12.6"
        assert data["channel"] == "stable"
        assert "Tauri" in data["runtime"]
        assert isinstance(data["supported_os"], list) and data["supported_os"]
        # Windows-only distribution (macOS pending, Linux not distributed).
        assert data["supported_os"] == ["Windows 10 / 11 (64bit)"]
        assert "min_supported_version" in data
        # build_number always present; commit/date may be None when env unset
        assert data["build_number"]

    def test_build_info_env_injection(self, client, admin_token, monkeypatch):
        # Env is read at request time, so monkeypatch alone takes effect.
        monkeypatch.setenv("APPS_BUILD_COMMIT", "abc1234")
        monkeypatch.setenv("APPS_BUILD_DATE", "2026-06-22")
        monkeypatch.setenv("APPS_BUILD_NUMBER", "1.12.6+build.42")
        resp = client.get("/api/v1/apps/build-info", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["git_commit"] == "abc1234"
        assert data["build_date"] == "2026-06-22"
        assert data["build_number"] == "1.12.6+build.42"

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/apps/build-info")
        assert resp.status_code == 401


class TestDownload:
    def test_download_not_configured_returns_null(
        self, client, admin_token, monkeypatch
    ):
        monkeypatch.delenv("APPS_RELEASE_BASE_URL", raising=False)
        resp = client.get("/api/v1/apps/download/win-exe", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] is None
        assert data["message"]

    def test_download_configured_returns_real_github_url(
        self, client, admin_token, monkeypatch
    ):
        monkeypatch.setenv("APPS_RELEASE_BASE_URL", _BASE)
        monkeypatch.setenv("APPS_SHA256_WIN_EXE", "deadbeef")
        resp = client.get("/api/v1/apps/download/win-exe", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == f"{_BASE}/{_REAL_FILENAMES['win-exe']}"
        assert data["sha256"] == "deadbeef"

    def test_download_url_for_every_package(self, client, admin_token, monkeypatch):
        monkeypatch.setenv("APPS_RELEASE_BASE_URL", _BASE)
        for pkg_id, filename in _REAL_FILENAMES.items():
            resp = client.get(
                f"/api/v1/apps/download/{pkg_id}", headers=_auth(admin_token)
            )
            assert resp.status_code == 200
            assert resp.json()["url"] == f"{_BASE}/{filename}"

    def test_download_sha256_none_when_env_unset(
        self, client, admin_token, monkeypatch
    ):
        monkeypatch.setenv("APPS_RELEASE_BASE_URL", _BASE)
        monkeypatch.delenv("APPS_SHA256_WIN_MSI", raising=False)
        resp = client.get("/api/v1/apps/download/win-msi", headers=_auth(admin_token))
        assert resp.status_code == 200
        # No fabricated checksum: None when the env var is not set.
        assert resp.json()["sha256"] is None

    def test_download_non_distributed_package_404(
        self, client, admin_token, monkeypatch
    ):
        # Even with the base URL set, macOS/Linux assets must not be handed out.
        monkeypatch.setenv("APPS_RELEASE_BASE_URL", _BASE)
        for pkg_id in _NOT_DISTRIBUTED:
            resp = client.get(
                f"/api/v1/apps/download/{pkg_id}", headers=_auth(admin_token)
            )
            assert resp.status_code == 404, pkg_id

    def test_download_unknown_package_404(self, client, admin_token):
        resp = client.get(
            "/api/v1/apps/download/does-not-exist", headers=_auth(admin_token)
        )
        assert resp.status_code == 404

    def test_download_requires_auth(self, client):
        resp = client.get("/api/v1/apps/download/win-exe")
        assert resp.status_code == 401
