# 📦 アプリ配信ページ 運用手順（PDF Editor Client）

管理コンソールの「アプリ」ページ（`/apps`）は、デスクトップ **PDF Editor Client**
（建設・土木業向け・電子印鑑/OCR/大判図面対応）を社内・協力会社へ配布する窓口です。

> ⚠️ PDF Editor 本体（デスクトップアプリ）の開発・ビルドは本リポジトリ外です。
> Editor のソースとビルドは CivilPDF-Editor リポジトリ（非公開）
> （**Tauri v2**、Issue #62 で配置先・技術選定を確定）。本リポジトリに `desktop/` 等の本体コードは置きません。
> 本ページはバイナリの**配布窓口**です。インストーラーは**本リポジトリ（public・正本）[mirai-construction-dx/CivilPDF-DX](https://github.com/mirai-construction-dx/CivilPDF-DX) の GitHub Releases**、
> Editor 専用タグ `editor-v<版>`（例 `editor-v1.12.6`）に添付して配布します。コンソール自身の `v0.x` タグとは名前で区別します。

## 🎯 0. 配布対象 OS（2026-09-26 決定）

| OS         | 状態                            | 備考                                                                 |
| ---------- | ------------------------------- | -------------------------------------------------------------------- |
| 🪟 Windows | ✅ **提供中**                   | Windows 10 / 11 (64bit)。`.exe`（NSIS）/ `.msi` の 2 形式            |
| 🍎 macOS   | ⏸️ **後日対応（ペンディング）** | API `pending_platforms` で返し、配信ページに「後日対応」カードを表示 |
| 🐧 Linux   | 🚫 提供対象外                   | Release にアセットはあるが配布しない。要望があれば再検討             |

> 🔒 配布対象外のパッケージ ID（`mac-dmg` / `linux-*`）は `/api/v1/apps/download/{id}` で **404** を返します。
> macOS 対応を再開する場合は、`apps.py` の `_build_packages()` へ戻し `_PENDING_PLATFORMS` から外します（API 契約変更として PR で扱う）。

---

## 📌 1. 提供エンドポイント（要認証）

| メソッド | パス                                  | 用途                                                       |
| -------- | ------------------------------------- | ---------------------------------------------------------- |
| GET      | `/api/v1/apps/releases`               | パッケージ一覧 + チャンネル情報 + `pending_platforms`      |
| GET      | `/api/v1/apps/release-notes?channel=` | リリースノート（任意でチャンネル絞り込み）                 |
| GET      | `/api/v1/apps/build-info`             | 配布中ビルドのメタデータ（`supported_os` は Windows のみ） |
| GET      | `/api/v1/apps/download/{package_id}`  | ダウンロード URL（未設定時は `url=null`）                  |

`package_id`: `win-exe` / `win-msi`

> 🧪 上記一覧は `tests/console/test_apps_docs_contract.py` が API 実装（`src/console/backend/api/apps.py`）と照合します。
> パッケージを追加・削除したら本書も同時に更新してください。

| package_id | 形式                           | 配布ファイル名（v1.12.6）              |
| ---------- | ------------------------------ | -------------------------------------- |
| `win-exe`  | Windows インストーラー（NSIS） | `CivilPDF.Editor_1.12.6_x64-setup.exe` |
| `win-msi`  | Windows インストーラー（MSI）  | `CivilPDF.Editor_1.12.6_x64_ja-JP.msi` |

`pending_platforms` の例（追加フィールド・後方互換）:

```json
[
  {
    "platform": "macos",
    "label": "macOS",
    "status": "pending",
    "note": "後日対応（ペンディング）。現在は Windows 版のみ提供しています"
  }
]
```

> 🔢 ファイル名は Tauri のビルド成果物を GitHub Release に添付した実名です（GitHub はアセット名の空白を `.` に置換）。
> バージョン部分は `apps.py` の `_VERSION` から導出され、ダウンロード URL は `{APPS_RELEASE_BASE_URL}/{filename}` です。

> 🚫 `.zip`（ポータブル）/ `.intunewin` は Tauri が生成しないため配布対象外です。
> Intune 配布が必要な場合は `.msi` を Win32 アプリとしてラップしてください（§4）。

---

## 📌 2. 環境変数（`.env.prod` / `deploy/civilpdf.env`）

| 変数                         | 必須       | 説明                                                              |
| ---------------------------- | ---------- | ----------------------------------------------------------------- |
| `APPS_RELEASE_BASE_URL`      | 配布時必須 | GitHub Releases のアセットパス。未設定なら「近日公開予定」表示    |
| `APPS_BUILD_NUMBER`          | 任意       | ビルド番号（既定 `<version>+local`、例 `1.12.6+build.42`）        |
| `APPS_BUILD_COMMIT`          | 任意       | ビルド元コミット（CivilPDF-Editor 側）                            |
| `APPS_BUILD_DATE`            | 任意       | ビルド日（ISO 8601）                                              |
| `APPS_MIN_SUPPORTED_VERSION` | 任意       | 強制最低バージョン（既定は配布中バージョン = `1.12.6`）           |
| `APPS_SHA256_<PKG_ID>`       | 任意       | 配布物の SHA-256（`APPS_SHA256_WIN_EXE` / `APPS_SHA256_WIN_MSI`） |

`APPS_RELEASE_BASE_URL` の設定例:

```text
https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
```

> 🔢 `APPS_SHA256_<PKG_ID>` の `<PKG_ID>` は package_id をハイフン→アンダースコアにし大文字化（`win-msi` → `WIN_MSI`）。
> 未設定のパッケージは整合性バッジを表示しません（チェックサムをコードにハードコードしない方針）。

---

## 📌 3. リリース手順

1. CivilPDF-Editor（非公開）で `v*` タグを push し、Windows インストーラー（`.exe` / `.msi`）が生成されるのを待つ。
2. チェックサムを生成（Linux 上 / Windows PowerShell いずれか）:
   ```bash
   sha256sum CivilPDF.Editor_1.12.6_x64-setup.exe CivilPDF.Editor_1.12.6_x64_ja-JP.msi
   ```
   ```powershell
   Get-FileHash .\CivilPDF.Editor_1.12.6_x64_ja-JP.msi -Algorithm SHA256
   ```
3. 本リポジトリの Releases に Editor 専用タグで公開する（コンソールの「Latest」を奪わないよう `--latest=false`）:
   ```bash
   gh release create editor-v1.12.6 -R mirai-construction-dx/CivilPDF-DX \
     --title "PDF Editor v1.12.6（Windows）" --latest=false --notes-file notes.md \
     CivilPDF.Editor_1.12.6_x64-setup.exe CivilPDF.Editor_1.12.6_x64_ja-JP.msi
   ```
4. 本リポジトリで `src/console/backend/api/apps.py` の `_VERSION` / `_RELEASE_DATE`・チャンネル説明・リリースノートを更新し、
   `tests/console/test_apps.py` の期待値（バージョン・ファイル名）と本書 §1 の表を合わせて更新する（PR 経由）。
5. `APPS_RELEASE_BASE_URL`（新タグのパス）と `APPS_SHA256_WIN_EXE` / `APPS_SHA256_WIN_MSI`・`APPS_BUILD_*` を環境へ設定。
6. 配布リンクが生きていることを確認（全パッケージ `[PASS]` で exit 0。SHA-256 設定時は `--verify-sha256` で実体も照合）:
   ```bash
   python scripts/check-editor-assets.py --base-url https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
   ```
7. コンソールを再起動し、`/apps` で Windows パッケージが「準備中」→ ダウンロード可能に変わり、macOS が「後日対応」表示であることを確認。

---

## 📌 4. Windows 展開（社内 IT 向け）

| 項目              | 内容                                                                                                                                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🧩 前提ランタイム | WebView2（Windows 11 は標準搭載。Windows 10 は未導入端末のみ Evergreen を事前配布）                                                                                                                                                                                                                                             |
| 🤫 サイレント導入 | `msiexec /i CivilPDF.Editor_1.12.6_x64_ja-JP.msi /qn /norestart`                                                                                                                                                                                                                                                                |
| 🗑️ サイレント削除 | `msiexec /x {ProductCode} /qn /norestart`                                                                                                                                                                                                                                                                                       |
| 🔁 対話型導入     | `CivilPDF.Editor_1.12.6_x64-setup.exe`（個人 PC 向け）                                                                                                                                                                                                                                                                          |
| 🔍 検出条件       | Uninstall レジストリの DisplayName（`CivilPDF Editor`）/ DisplayVersion（`1.12.6`）                                                                                                                                                                                                                                             |
| 🏢 Intune         | `.msi` を Win32 アプリ（IntuneWinAppUtil でラップ）または LOB アプリとして登録                                                                                                                                                                                                                                                  |
| 🔏 署名           | Authenticode 署名済み（**自己署名**）。証明書を GPO/Intune で **信頼された発行元（Trusted Publishers）** ストアへ配布すると「発行元不明」警告を軽減できる（ルートへの全社配布は鍵漏えい時の影響が大きいので避け、署名鍵は厳重に保護する）。ダウンロードファイルの SmartScreen 評判判定は残る場合があり、恒久対策は OV/EV 証明書 |

> 🔐 配布前に §3 の SHA-256 と `APPS_SHA256_*` の一致を確認してから展開してください。

---

## 📌 5. macOS（後日対応・ペンディング）

- ⏸️ macOS 版（`.dmg` / MDM 向け `.pkg`）の配布は**ペンディング**です。配信ページには「後日対応」カードのみ表示します。
- 🔁 再開時の確認事項: Apple Developer ID 署名・notarization、`.dmg` のみか `.pkg` も要るか、対応 macOS バージョン。
- 🍎 iTunes パッケージ（`.itmsp`）は App Store 提出専用形式のため本配信ページでは扱いません。

---

## 📌 6. チャンネル運用

| チャンネル | 対象                   | 備考                                        |
| ---------- | ---------------------- | ------------------------------------------- |
| Stable     | 全ユーザー（本番推奨） | 現在提供している唯一のチャンネル（v1.12.6） |

> 🧭 Beta / Insider チャンネルは未提供です（API の `Channel` 型も `stable` のみ）。追加する場合は API 契約変更として扱います。

---

## 📌 7. 既知の制約

- 🔏 配布ビルドは**自己署名**のコード署名のため、Windows SmartScreen の警告が表示される場合があります。
- 📊 チャンネルの `user_count` は実測していないため `0` を返します（推測値を表示しない方針）。
- 📊 「展開対象」「展開率/バージョン統一率」などの KPI は **MDM 未連携のデモ表示**（UI に「デモ」明示）。
  実数値表示には Intune 連携の実装が必要（別 Issue 候補）。
- ⚙️ 配信ページの「配布設定」トグル（自動アップデート等）は UI 上の表示のみで、サーバーへ保存されません（別 Issue 候補）。
- 🔗 ダウンロードは `APPS_RELEASE_BASE_URL` 設定後に有効化（未設定時は「近日公開予定」）。
  設定済みでもアセット未公開・非公開化ではリンクが 404 になるため、`scripts/check-editor-assets.py` で確認する。
