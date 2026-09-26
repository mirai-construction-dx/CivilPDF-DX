"""App distribution API — release channel, release notes, build info and installer downloads.

Source of truth: the public GitHub Release of CivilPDF-Editor (Tauri v2 desktop app).

    https://github.com/Kensan196948G/CivilPDF-Editor/releases/tag/v1.2.4

Distribution scope: Windows only. macOS is deferred (pending, reported via
`pending_platforms`); Linux assets exist on the Release but are not distributed.

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

# Current published stable release. Matches the GitHub Release tag v1.2.4.
_VERSION = "1.2.4"
# Public release date of v1.2.4 (GitHub Release publication date).
_RELEASE_DATE = "2026-06-22"

Channel = Literal["stable"]
NoteType = Literal["FEAT", "FIX", "SEC", "IMP", "NOTE"]


# Env is read at request time (not import time) so deployment configuration and
# tests take effect without a module reload.
def _base_url() -> str:
    """Base URL of the GitHub Releases asset path (empty when unconfigured).

    Set in deployment to:
        https://github.com/Kensan196948G/CivilPDF-Editor/releases/download/v1.2.4
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

    Filenames MUST match the real assets attached to the GitHub Release
    (GitHub replaces spaces in asset names with dots). Asset filenames embed the
    release version because package.json / tauri.conf.json are bumped before the
    CI build, so filenames are derived from _VERSION here to prevent drift.
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
            "約 1.9 MB",
        ),
        _pkg(
            "win-msi",
            "windows",
            "msi",
            "インストーラー (.msi)",
            f"CivilPDF.Editor_{_VERSION}_x64_en-US.msi",
            "約 2.4 MB",
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
            "安定版。テキスト編集モード（v1.2.4 新機能）・注釈（Phase A）・"
            "検索/しおり/透かし/メタデータ（Phase B）・"
            "画像→PDF/比較/フォーム（Phase C）を搭載。"
            "Windows 版のみ提供（macOS は後日対応）。"
            "未署名ビルドのため Windows SmartScreen の警告が表示される場合があります。"
        ),
        user_count=0,
    ),
]


_RELEASE_NOTES: list[ReleaseNote] = [
    ReleaseNote(
        version=_VERSION,
        channel="stable",
        release_date=_RELEASE_DATE,
        summary="v1.2.4 安定版 — テキスト編集の左右の位置ずれを修正（v1.2.0 の全機能を継続搭載）",
        items=[
            ReleaseNoteItem(
                type="FIX",
                text="テキスト編集の置換テキストが画面で左にずれる不具合を修正（左右の位置を元の文字に一致）",
            ),
            ReleaseNoteItem(
                type="FIX",
                text="テキスト編集の置換テキストが元のベースラインに正確に配置されるよう修正（上下のずれを解消）",
            ),
            ReleaseNoteItem(
                type="FIX",
                text="テキスト編集の確定後に画面へ即時反映されるよう修正（確定した編集が画面に表示されなかった不具合）",
            ),
            ReleaseNoteItem(
                type="FIX",
                text="テキスト編集モードの日本語対応（NotoSansJP 同梱で日本語が PDF に焼き込まれるように）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="テキスト編集モード（PDF 上のテキストを直接編集・PDF 焼き込み）",
            ),
            ReleaseNoteItem(type="FEAT", text="PDF 表示（M1: ページ閲覧・ズーム）"),
            ReleaseNoteItem(
                type="FEAT",
                text="電子印鑑（M2: 印影作成・配置・PDF 埋め込み）",
            ),
            ReleaseNoteItem(type="FEAT", text="OCR テキスト抽出（M3: Tesseract.js）"),
            ReleaseNoteItem(type="FEAT", text="大判図面対応（M4: A0/A1 タイル表示）"),
            ReleaseNoteItem(
                type="FEAT",
                text="注釈（Phase A: ハイライト・下線・取消線・付箋・手書き・消去 + 6色カラーピッカー）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="テキスト検索（Phase B: 全ページ横断・前後ナビ・コンテキスト表示）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="しおり/目次ナビゲーション（Phase B: PDF アウトライン階層表示）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="透かし追加（Phase B: CJK 対応テキスト透かし）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="メタデータ編集（Phase B: タイトル・著者・件名・キーワード）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="画像から PDF 作成（Phase C: PNG/JPEG → PDF A4/A3 対応）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="PDF 比較（Phase C: LCS アルゴリズムによるテキスト差分表示）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="フォームフィールド確認（Phase C: AcroForm Widget 読み取り）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="ネイティブメニュー（File/Edit/View・キーボードショートカット対応）",
            ),
            ReleaseNoteItem(
                type="FEAT",
                text="レビューワークフロー（承認・却下スタンプ・非破壊保存）",
            ),
            ReleaseNoteItem(
                type="NOTE",
                text="未署名ビルド。Windows SmartScreen の警告が表示される場合があります",
            ),
            ReleaseNoteItem(
                type="NOTE",
                text="配布は Windows 版のみ（macOS は後日対応・ペンディング）",
            ),
        ],
        highlights=(
            "v1.2.4 — リリースノート\n\n"
            f"リリース日: {_RELEASE_DATE}\nチャンネル: Stable（安定版）\n\n"
            "修正（v1.2.4）:\n"
            "- テキスト編集の左右ずれ: 置換テキストが画面で左にずれる不具合を修正"
            "（左右の位置を元の文字に一致）\n"
            "- テキスト編集の上下ずれ: 元のベースラインに正確に配置するよう修正（v1.2.3）\n"
            "- テキスト編集の画面反映: 確定した編集が画面に即時表示されるよう修正（v1.2.2）\n"
            "- テキスト編集の日本語対応: NotoSansJP 同梱で日本語が PDF に焼き込まれるよう修正（v1.2.1）\n\n"
            "v1.2.0 の新機能:\n"
            "- テキスト編集モード: PDF 上のテキストを直接編集し、PDF へ焼き込み\n\n"
            "継続機能（v1.1.0 から）:\n"
            "- 注釈（Phase A）: ハイライト・下線・取消線・付箋・手書き・消去 + 6色カラーピッカー\n"
            "- テキスト検索（Phase B）: 全ページ横断検索・前後ナビゲーション・コンテキスト表示\n"
            "- しおり/目次（Phase B）: PDF アウトライン階層表示・クリックでページ移動\n"
            "- 透かし（Phase B）: CJK 対応テキスト透かし\n"
            "- メタデータ編集（Phase B）: タイトル・著者・件名・キーワード・作成アプリ\n"
            "- 画像から PDF 作成（Phase C）: PNG/JPEG → PDF（A4/A3/自動）\n"
            "- PDF 比較（Phase C）: LCS アルゴリズムによるテキスト差分表示\n"
            "- フォームフィールド確認（Phase C）: AcroForm Widget フィールド読み取り\n"
            "- ネイティブメニュー: File/Edit/View メニュー・キーボードショートカット\n\n"
            "継続機能（v1.0.0 から）:\n"
            "- PDF 表示（M1）: ページ閲覧・ズーム\n"
            "- 電子印鑑（M2）: 印影作成・配置・PDF 埋め込み\n"
            "- OCR（M3）: テキスト抽出（Tesseract.js）\n"
            "- 大判図面（M4）: A0/A1 タイル表示\n"
            "- レビューワークフロー: 承認・却下スタンプ・非破壊保存\n\n"
            "技術スタック: Tauri v2（システムの WebView を利用）\n"
            "対応 OS: Windows 10 / 11 (64bit)。macOS は後日対応（ペンディング）。\n"
            "注意: 未署名ビルドのため、Windows SmartScreen の警告が表示される場合があります。"
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
