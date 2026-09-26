"""App distribution API — release channel, release notes, build info and installer downloads.

Source of truth for the distributed installers: the public GitHub Release of this
repository (CivilPDF-DX) under the Editor-specific tag `editor-v<version>`, kept
separate from the console's own `v0.x` release tags.

    https://github.com/mirai-construction-dx/CivilPDF-DX/releases/tag/editor-v1.12.6

The Editor itself (Tauri v2 desktop app) is built in the CivilPDF-Editor repository;
version, asset names and notes here mirror its v1.12.6 release.

Distribution scope: Windows only. macOS is deferred (pending, reported via
`pending_platforms`); Linux builds exist upstream but are not distributed.

This module intentionally avoids fabricated metadata. Values that are not measured
(e.g. active user counts) are reported honestly (0 / None) rather than guessed.
"""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth.dependencies import get_current_user
from models.user import User

router = APIRouter(prefix="/apps", tags=["App Distribution"])

# Current distributed stable release (CivilPDF-Editor v1.12.6).
_VERSION = "1.12.6"
# Upstream release date of v1.12.6 (updater latest.json pub_date).
_RELEASE_DATE = "2026-08-12"

Channel = Literal["stable"]
NoteType = Literal["FEAT", "FIX", "SEC", "IMP", "NOTE"]


# Env is read at request time (not import time) so deployment configuration and
# tests take effect without a module reload.
def _base_url() -> str:
    """Base URL of the GitHub Releases asset path (empty when unconfigured).

    Set in deployment to:
        https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
    """
    return os.getenv("APPS_RELEASE_BASE_URL", "").rstrip("/")


class ReleasePackage(BaseModel):
    id: str
    platform: str
    format: str
    label: str
    filename: str
    version: str
    size_label: str
    sha256: str | None
    download_path: str
    available: bool


class ChannelInfo(BaseModel):
    id: str
    label: str
    version: str
    release_date: str
    description: str
    user_count: int


class PendingPlatform(BaseModel):
    platform: str
    label: str
    status: Literal["pending"]
    note: str


class AppsReleasesResponse(BaseModel):
    stable_version: str
    packages: list[ReleasePackage]
    channels: list[ChannelInfo]
    pending_platforms: list[PendingPlatform] = []


class DownloadUrlResponse(BaseModel):
    url: str | None
    sha256: str | None = None
    message: str | None = None


class ReleaseNoteItem(BaseModel):
    type: NoteType
    text: str


class ReleaseNote(BaseModel):
    version: str
    channel: Channel
    release_date: str
    summary: str
    items: list[ReleaseNoteItem]
    highlights: str | None = None


class ReleaseNotesResponse(BaseModel):
    notes: list[ReleaseNote]


class BuildInfo(BaseModel):
    product: str
    stable_version: str
    build_number: str
    git_commit: str | None
    build_date: str | None
    channel: str
    runtime: str
    supported_os: list[str]
    min_supported_version: str


def _resolve_sha256(pkg_id: str) -> str | None:
    """Resolve a package checksum from APPS_SHA256_<PKG_ID> (e.g. APPS_SHA256_WIN_EXE).

    Returns None when unset so the frontend can omit the integrity badge. We do not
    hardcode checksums here because they are produced by the release pipeline.
    """
    key = "APPS_SHA256_" + pkg_id.upper().replace("-", "_")
    value = os.getenv(key)
    return value or None


def _pkg(
    pkg_id: str, platform: str, fmt: str, label: str, filename: str, size: str
) -> ReleasePackage:
    return ReleasePackage(
        id=pkg_id,
        platform=platform,
        format=fmt,
        label=label,
        filename=filename,
        version=_VERSION,
        size_label=size,
        sha256=_resolve_sha256(pkg_id),
        download_path=f"/api/v1/apps/download/{pkg_id}",
        available=bool(_base_url()),
    )


def _build_packages() -> list[ReleasePackage]:
    """Build the package list fresh so env-driven checksums/availability stay current.

    Filenames MUST match the real Tauri build assets (GitHub replaces spaces in
    asset names with dots; the MSI is built with WiX language ja-JP). Asset
    filenames embed the release version, so they are derived from _VERSION here
    to prevent drift.
    The download URL is then `{APPS_RELEASE_BASE_URL}/{filename}`.

    Only Windows packages are distributed; macOS is listed in _PENDING_PLATFORMS.
    """
    return [
        _pkg(
            "win-exe",
            "windows",
            "exe",
            "インストーラー (.exe / NSIS)",
            f"CivilPDF.Editor_{_VERSION}_x64-setup.exe",
            "約 39.3 MB",
        ),
        _pkg(
            "win-msi",
            "windows",
            "msi",
            "インストーラー (.msi)",
            f"CivilPDF.Editor_{_VERSION}_x64_ja-JP.msi",
            "約 40.1 MB",
        ),
    ]


# Platforms announced but not yet distributed. Reported so the UI can say
# "後日対応" instead of silently omitting them.
_PENDING_PLATFORMS: list[PendingPlatform] = [
    PendingPlatform(
        platform="macos",
        label="macOS",
        status="pending",
        note="後日対応（ペンディング）。現在は Windows 版のみ提供しています",
    ),
]


_CHANNELS: list[ChannelInfo] = [
    ChannelInfo(
        id="stable",
        label="Stable",
        version=f"v{_VERSION}",
        release_date=_RELEASE_DATE,
        description=(
            "安定版。PDF 表示・電子印鑑・OCR・大判図面・注釈・レビュー台帳に加え、"
            "自動更新（署名付き）・複数 PDF 一括処理・印影ライブラリ・自動保存を搭載。"
            "Windows 版のみ提供（macOS は後日対応）。"
            "自己署名のコード署名のため Windows SmartScreen の警告が表示される場合があります。"
        ),
        user_count=0,
    ),
]


_RELEASE_NOTES: list[ReleaseNote] = [
    ReleaseNote(
        version=_VERSION,
        channel="stable",
        release_date=_RELEASE_DATE,
        summary=(
            f"v{_VERSION} 安定版 — Windows コード署名の検証を自己署名に対応"
            "（v1.3〜v1.12 の機能を継続搭載）"
        ),
        items=[
            ReleaseNoteItem(
                type="FIX",
                text="Windows 署名検証を自己署名証明書に対応（署名の存在・改ざんなし・署名者の一致で判定）",
            ),
            ReleaseNoteItem(
                type="SEC",
                text="Windows インストーラーに Authenticode コード署名を付与（現行は自己署名）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="自動更新（署名付き更新パッケージ・診断ダイアログから「更新を確認」）",
            ),
            ReleaseNoteItem(
                type="SEC",
                text="暗号化処理の任意パス読み取り防止・DX オフラインキューの上限設定",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="診断ログ（オプトイン・端末内保存・外部送信なし）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="複数 PDF 一括処理（回転・透かし・ヘッダー/フッター・パスワード保護）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="印影ライブラリ・自動保存とクラッシュ復元・検索→置換",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="レビュー台帳の CSV 出力・比較結果の PDF レポート・DX 同期のオフラインキュー",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="継続: PDF 表示・電子印鑑・OCR・大判図面・注釈・テキスト編集・検索/しおり/透かし・比較・フォーム",
            ),
            ReleaseNoteItem(
                type="NOTE",
                text="自己署名のため Windows SmartScreen の警告が表示される場合があります（社内信頼ストア配布で解消）",
            ),
            ReleaseNoteItem(
                type="NOTE",
                text="配布は Windows 版のみ（macOS は後日対応・ペンディング）",
            ),
        ],
        highlights=(
            f"v{_VERSION} — リリースノート\n\n"
            f"リリース日: {_RELEASE_DATE}\nチャンネル: Stable（安定版）\n\n"
            f"修正（v{_VERSION}）:\n"
            "- Windows 署名検証を自己署名証明書に対応（v1.12.4〜v1.12.6 で署名パイプラインを実地検証）\n\n"
            "v1.12 の主な追加:\n"
            "- 自動更新: 署名付き更新パッケージ。診断ダイアログから「更新を確認」「ダウンロードして適用」\n"
            "- コード署名: Windows インストーラーに Authenticode 署名（現行は自己署名）\n\n"
            "v1.3〜v1.11 の主な追加:\n"
            "- 複数 PDF 一括処理・印影ライブラリ・自動保存とクラッシュ復元・検索→置換\n"
            "- レビュー台帳 CSV 出力・比較結果 PDF レポート・DX 同期オフラインキュー\n"
            "- 診断ログ（オプトイン・外部送信なし）・セキュリティ堅牢化\n\n"
            "継続機能（v1.0〜v1.2）:\n"
            "- PDF 表示・電子印鑑・OCR・大判図面・注釈・テキスト編集・検索/しおり/透かし・比較・フォーム\n\n"
            "技術スタック: Tauri v2（システムの WebView2 を利用）\n"
            "対応 OS: Windows 10 / 11 (64bit)。macOS は後日対応（ペンディング）。\n"
            "注意: 自己署名のため、Windows SmartScreen の警告が表示される場合があります。"
        ),
    ),
]


@router.get("/releases", response_model=AppsReleasesResponse)
def get_releases(_: User = Depends(get_current_user)) -> AppsReleasesResponse:
    """Return release metadata for all platforms and distribution channels."""
    return AppsReleasesResponse(
        stable_version=f"v{_VERSION}",
        packages=_build_packages(),
        channels=_CHANNELS,
        pending_platforms=_PENDING_PLATFORMS,
    )


@router.get("/release-notes", response_model=ReleaseNotesResponse)
def get_release_notes(
    channel: Optional[Channel] = None, _: User = Depends(get_current_user)
) -> ReleaseNotesResponse:
    """Return release notes, optionally filtered by distribution channel."""
    notes = _RELEASE_NOTES
    if channel is not None:
        notes = [n for n in notes if n.channel == channel]
    return ReleaseNotesResponse(notes=notes)


@router.get("/build-info", response_model=BuildInfo)
def get_build_info(_: User = Depends(get_current_user)) -> BuildInfo:
    """Return build metadata for the currently distributed build.

    Values come from the build pipeline (APPS_BUILD_* env vars); safe defaults
    are returned when unset so the endpoint never leaks secrets or fails.
    """
    return BuildInfo(
        product="CivilPDF Editor Client",
        stable_version=f"v{_VERSION}",
        build_number=os.getenv("APPS_BUILD_NUMBER", f"{_VERSION}+local"),
        git_commit=os.getenv("APPS_BUILD_COMMIT") or None,
        build_date=os.getenv("APPS_BUILD_DATE") or None,
        channel="stable",
        runtime="Tauri v2（システムの WebView を利用）",
        supported_os=["Windows 10 / 11 (64bit)"],
        min_supported_version=os.getenv("APPS_MIN_SUPPORTED_VERSION", _VERSION),
    )


@router.get("/download/{package_id}", response_model=DownloadUrlResponse)
def get_download_url(
    package_id: str, _: User = Depends(get_current_user)
) -> DownloadUrlResponse:
    """Return the download URL for a specific installer package.

    Returns url=null with a message when APPS_RELEASE_BASE_URL is not configured,
    so the frontend can show a 'coming soon' state gracefully. When configured,
    the URL is `{base}/{filename}` where filename matches the real GitHub asset.
    """
    pkg = next((p for p in _build_packages() if p.id == package_id), None)
    if pkg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    base = _base_url()
    if not base:
        return DownloadUrlResponse(
            url=None, sha256=pkg.sha256, message="ダウンロードリンクは近日公開予定です"
        )
    return DownloadUrlResponse(url=f"{base}/{pkg.filename}", sha256=pkg.sha256)
