# Changelog

すべての注目すべき変更点はこのファイルに記録されます。

[Semantic Versioning](https://semver.org/) に従います。

---

## [Unreleased]

### 2026-09-26 (15) — 反映前チェックスクリプト・MVP バックアップの除外・既知の制約の棚卸し

- 🚀 `scripts/pre-deploy-check.sh` 追加（読み取りのみ）— checkout が main かつ origin/main と一致、追跡ファイルの変更なし（state.json は許容）、`.env` が group/others に権限なし（600 推奨）、ヘルス/バックアップ鮮度、ロールバック用イメージタグ、配布リンクと SHA-256 を確認。`.env` は APPS_* だけを読み、secret は出力しない。テスト 8 件
- 🔒 `.gitignore` に `.mvp-data.bak-*/` を追加（MVP の SQLite とアップロードのバックアップを誤ってコミットしないように）
- 📄 runbook: デプロイ手順（main 更新後・再ビルド直前）に反映前チェックを追加、既知の制約を更新（#62/#94 close・ecdsa 解消・macOS は #147）。反映チェックリストにも組み込み
- 🔒 pip-audit / npm audit ともに 0 件を確認

### 2026-09-26 (14) — 運用・品質の底上げ（配布リンク日次監視・テスト DB 分離・作り話の数値撤去・依存脆弱性ゼロ）

- 🔍 `scripts/editor-asset-watch.sh` 追加・`monitor-civilpdf.sh` から日次実行 — PDF Editor 配布リンクが届かなければメール通知（復旧時も 1 回）。ヘルス監視の結果には影響しない
- 🧪 pytest のテスト DB をプロセスごとの一時ファイルに分離（並行実行で互いのテーブルを drop していた問題の再発防止）
- 🖥️ LandingView の実測でない数値（1,284 / 248 / 97.3% / 6）を機能の事実表示へ置換。AppsView の全カードで Space 押下時に preventDefault
- 🧹 tests/ の未使用 import 16 件を解消（CI の ruff 対象への `tests/` `scripts/` 追加は workflow 権限が必要なため別途適用）
- 🔒 vitest 4.1.9 → 4.1.11（GHSA-82fw-gwwq-j7x9 / CWE-22、dev 依存のみ）で `npm audit` 0 件
- ⚙️ 配信ページの「配布設定」トグル（Editor に効かない UI だけのスイッチ）を撤去し、読み取り専用の「配布ポリシー」表示へ（案 A・ユーザー決定）
- 📄 設計メモ `docs/architecture/apps-distribution-settings.md`（案 A 採用を記録）、runbook §4.3、ブランチ棚卸しレポート

### 2026-09-26 (13) — PDF Editor 配布元を本リポジトリ Releases（editor-v1.12.6）へ移行・表示版を v1.12.6 へ更新

- 🚨 旧配布元 `Kensan196948G/CivilPDF-Editor/releases/download/v1.2.4` が 404（リポジトリ非公開化）で、配信ページのダウンロードが壊れていた
- 🌐 配布元を public の本リポジトリ Releases・Editor 専用タグ `editor-v<版>` へ変更（コンソールの `v0.x` と区別、`--latest=false` で公開）
- 🔢 表示版を実配布版 v1.12.6（2026-08-12）へ更新。MSI 実名は `_x64_ja-JP.msi`、サイズは実測（約 39.3 / 40.1 MB）
- 📝 リリースノート・チャンネル説明を v1.3〜v1.12.6 の実変更（自動更新・自己署名コード署名・一括処理 等）へ更新。「未署名」→「自己署名」へ是正
- 🔍 `scripts/check-editor-assets.py` 追加 — 配布アセットの到達性（HEAD）と任意で SHA-256 を検証。テストは MockTransport（外部通信なし）
- 🖥️ AppsView: 実測でない「248 ライセンス」表示を削除、「v1.1.0 未満」固定文言と展開対象デモの固定版表示を API 連動へ。mock を v1.12.6 へ同期
- API スキーマ・DB・認証の変更なし（版・ファイル名・文言のみ）

### 2026-09-26 (12) — PDF Editor 配布を Windows のみへ限定・macOS を後日対応（ペンディング）化

- 🪟 `/api/v1/apps/releases` のパッケージを `win-exe` / `win-msi` の 2 種に限定。`mac-dmg` / `linux-*` のダウンロードは 404
- ⏸️ `pending_platforms` フィールドを追加（後方互換の追加のみ）— macOS を「後日対応（ペンディング）」として返却
- 🔧 `build-info.supported_os` を `Windows 10 / 11 (64bit)` のみに。リリースノート・チャンネル説明から Gatekeeper 記載を削除し Windows 限定配布を明記
- 🖥️ 配信ページ（AppsView）: Windows 2 形式 + macOS「後日対応」カード（クリックで説明モーダル）。mockAdapter も同期
- 📄 `docs/deployment/app-distribution.md` に配布対象 OS 表・Windows 社内展開手順（サイレント導入/削除・Intune・SHA-256 確認）・macOS 再開時の確認事項を追加
- 🧪 backend 26・契約 4・frontend AppsView 8 件（macOS pending 表示・旧バックエンド互換を含む）
- API 追加のみ・DB/認証/本番設定の変更なし

### 2026-09-26 (11) — アプリ配信文書を実 API（CivilPDF-Editor v1.2.4 / Tauri v2）へ同期（Issue #62 連携）

- 📄 `docs/deployment/app-distribution.md`・README・`.env.prod.example` に残っていた Electron 計画時の記載
  （`win-zip` / `mac-pkg` / `ent-intune`・架空の v2.4.1・Beta/Insider チャンネル）を削除し、
  実 API（Windows exe/msi の 2 種・macOS は後日対応・Linux は対象外）と Stable のみの運用へ是正（(12) の Windows 限定と同時適用）
- 🧩 PDF Editor 本体の正本は別リポジトリ CivilPDF-Editor であることを明記（本リポジトリに desktop/ を作らない）
- 🧪 `tests/console/test_apps_docs_contract.py` 追加 — 文書の package_id・ファイル名・バージョンを `api/apps.py` と照合し、再ドリフトを CI で検知
- API・DB・認証・本番設定の変更なし

### 2026-09-18 (10) — 本番実体（compose スタック）への運用系完全移行・監視/バックアップの実障害修正

#### 🚨 本番実体は compose スタックだった（旧 systemd 構成の残留と Neon の残存を発見・修正）
- 実測: 公開URL（200）の実体は `civilpdf-dx` docker compose スタック（frontend nginx :18970）。
  一方 `deploy/` の systemd ユニット（uvicorn 8180 / vite preview 5182 / user cloudflared）は
  **Neon の失効した DATABASE_URL（2026-08-29 失効）を参照した旧世代のまま残存**していた
- 旧 `civilpdf-backup.service` は**毎日 02:30 に Neon へ pg_dump して 21日間失敗し続けていた**
  （本番DB＝compose の db コンテナは一度もバックアップされていなかった）
- 旧 `civilpdf-monitor.service` は 5 分毎に frontend 5182 を見て失敗し続けていた（DEGRADED）
- 対応: `deploy/civilpdf-backend.service` 等に **RETIRED 注記**を付し `install-systemd.sh` を
  compose 運用（backup/monitor/drill/retention のユーザーユニット）へ全面改訂。
  退役手順を Runbook §2.1 に記録

#### バックアップ（compose モード実装・実測 PASS）
- `scripts/backup-production.sh` に **CIVILPDF_DEPLOY_MODE（auto/compose/database-url/sqlite）**を追加。
  compose モードは db コンテナ内 pg_dump（認証情報不要・版数は必然一致）＋ backend コンテナ内
  uploads の tar 化。auto は稼働中スタックを検出して切替
- **本番DBの初めての有効バックアップを取得**（42,882バイト・17テーブル・コンテナ内+ホスト両
  pg_restore で検証）。8/28 の旧ダンプは 21世代前の無効データ
- 修正前は毎回 60 秒で SIGTERM され **prune が中断して「半分削除されたバックアップ」を残していた**
  （8/26 世代の dump のみが消えた状態を実測）→ ユニットに `TimeoutStartSec=10min`、
  半分削除世代は削除して実測

#### 復元訓練（DRILL PASS・2026-09-18 実測）
- `scripts/restore-drill.sh` を compose バックアップ（uploads.tar.gz）形式へ対応。
  訓練用DB（civildx_drill・peer 認証）へ復元 → alembic upgrade head（k1l2m3n4o5p6 → o5p6q7r8s9t0）
  → backend 起動 → ログイン → /auth/me → /projects まで **全段階 PASS**
- 修正: `alembic` が PATH に無い環境で rc=127 で黙死していたのを `python3 -m alembic` に統一

#### 監視（healthcheck を実本番構成へ）
- `scripts/healthcheck-civilpdf.sh`: 既定を compose 構成（:18970）へ。DB readiness は
  **backend コンテナ内で /health/ready を直接検証**（nginx 経由の旧手順は SPA fallback 200 で
  偽陽性になるため）。compose 稼働検出は自動
- 実測で「旧 backend コンテナ（8/29 ビルド）に /health/ready が無い」ことを検出
  （= 新イメージのデプロイが必要なことを監視が正しく指摘）

#### 🐛 frontend コンテナの healthcheck が永久 unhealthy（58,073 回連続失敗）
- `Dockerfile.prod` の HEALTHCHECK が `localhost`（→ ::1）を叩くが nginx は IPv4 のみ LISTEN
  のため 2 週間全失敗。**127.0.0.1 を明示**するよう修正

#### 🐛 retention-job.py が依存欠落環境で誤った exit code（1）を返す
- `--grace-days 0` は exit 2 と文書化されているが、検証がバックエンド import（pydantic_settings 等）
  の後だったため、依存が無い環境では ImportError の traceback で exit 1 になっていた。
  **検証を import より前に移動**し、依存の有無と無関係に exit 2 を返すように修正（両環境で実測）

#### 🐛 CSV エクスポートの 413 定数が starlette 0.4x に存在しない
- `csv_export.py` が `status.HTTP_413_CONTENT_TOO_LARGE`（starlette ≥0.47 の定数）を直接参照し、
  pip 解決環境（fastapi 0.115/starlette 0.38）で AttributeError になっていた
  （2 テスト失敗の原因）。requirements の範囲内で動作するよう `documents.py` と同じ
  `HTTP_413_REQUEST_ENTITY_TOO_LARGE` へ統一

#### 文書の実態同期
- `docs/operations/runbook.md`: §1 構成一覧・§2 デプロイ手順・§3 復旧手順・§4 監視・
  保持ポリシー手順を compose 実体へ全面更新
- `docs/deployment/local-postgresql.md`: 現行本番（compose の db コンテナ）と
  ホスト直 PostgreSQL（civildx_prod）の関係を明確化し、compose モードの
  バックアップ/復元/訓練手順を追加
- `docs/tech-stack.md` / `docs/architecture/system-architecture.md` /
  `docker-production-deployment.md`: DB 表記を実態へ統一
- `.gitignore`: ローカル実行成果物（agent ツール設定・バックアップ類）を除外。
  `.claude/commands/` の新規 2 コマンド（design-sync-check / safe-auto-merge）は
  プロジェクト標準コマンドとして追跡

#### 検証（2026-09-18 実測）
- backend: **482 passed / 4 skipped**（486 collected・starlette 修正後。旧環境の 3 失敗を解消）
- frontend: lint 0 / build OK / **vitest 277 passed** / **Playwright E2E 25 passed**
- ruff 0.8.6（CI と同版数）: src/console/backend 全チェック PASS・format OK
- ops: backup 実走 PASS（6.1秒）・restore-drill 実走 PASS・healthcheck は旧イメージの
  readiness 欠落を正しく検出（= デプロイ待ちの正当な DEGRADED）
- verify-version-sync: OK

### 2026-09-18 (9) — Neon 設定の削除と、pg_dump/pg_restore 版数不一致の修正

#### Neon 依存の削除（ローカル PostgreSQL へ一本化）
- `scripts/migrate-sqlite-to-neon.py` → **`scripts/migrate-sqlite-to-postgresql.py`**
  （実装は元々 DATABASE_URL で任意の PostgreSQL を対象にできる汎用スクリプト。名前のみ Neon 依存だった）
- `docs/deployment/neon-postgresql-migration.md` → **`docs/deployment/local-postgresql.md`**
  （構築・バックアップからの移設・バックアップ・復元・ロールバック・残課題を、実施記録付きで全面改訂。
  旧 Neon 構成は「付録（廃止）」として履歴を保持）
- 参照と記述を更新: `docs/tech-stack.md`（構成図2箇所・技術表・ADR-001・リンク集）、
  `docs/architecture/system-architecture.md`、`docs/operations/runbook.md`（構成表・バックアップ・容量・残課題）、
  `docs/deployment/docker-production-deployment.md`、`docs/deployment/secret-management.md`、
  `docs/deployment/mvp-preview-environment.md`、`docs/evaluation/…assessment.md`（§10.4 を追加）

> `docs/architecture/CloudflareNeonGitHub自動化仕様.md` は**ワークスペース共通の中央ポリシー**
> （ホストの MCP 設定を含む）であり、本リポジトリのDB構成とは別の関心事のため対象外とした。

#### 🚨 バックアップが復元できない形式で作られていた（修正）
- `backup-production.sh` / `restore-drill.sh` は「**インストール済みの最新** pg_dump / pg_restore」を
  選んでいた。このホストは PATH が混在（`psql` 18 / `pg_dump` 17 / `pg_restore` 16、サーバーは 16）で、
  **pg_dump 18 が書いたダンプを既定の `pg_restore` 16 が読めず**、文書化された復元手順が失敗した:
  `pg_restore: エラー: ファイルヘッダ内のバージョン(1.16)はサポートされていません`
  （2026-08-28 の唯一の有効なバックアップが実際にこの状態だった）
- 修正: `scripts/pg-tools.sh` を追加し、**サーバーのメジャーバージョンに一致するクライアント**を
  自動選択（一致しない場合は警告）。`backup-production.sh` はさらに
  **既定の `pg_restore` でも読めること**を検証してから公開する
- 実測（修正後）: `/usr/lib/postgresql/16/bin/pg_dump` が選択され、46,543バイトのダンプを
  **既定の `pg_restore` 16 で読み出せる**ことを確認（同じコマンドで 08-28 のダンプは読めない＝修正前の障害を再現）
- `bash -n` / `shellcheck -S warning` clean

### 2026-09-18 (8) — 本番DBを Neon からローカル PostgreSQL へ移行（データ移設・テスト隔離）

ユーザー判断により **Neon を廃止し、ローカル PostgreSQL を本番DBとする**方針へ移行した。
本項はデータ移設と、その過程で発見したテスト隔離欠陥の修正を記録する。

#### データ移設（Neon → ローカル PostgreSQL）
- **復旧可能な最新の本番データを特定**: Neon の認証情報は失効しており直接読み出せないため、
  唯一の有効なバックアップ `~/civildx-backups/20260828T083204Z/civilpdf.dump`
  （2026-08-28、17テーブルの実データを含む）を使用した。08-29 以降のバックアップは
  すべて 0 バイトで使用不可
- **移設先**: 新規データベース `civildx_prod` を作成し、そこへ復元 →
  `alembic upgrade head`（`k1l2m3n4o5p6` → `o5p6q7r8s9t0`）
- 復元時のエラーは **PG17+ の `SET transaction_timeout` 1件のみ**（PG16 では無視される良性）
- 検証: schema parity OK（17テーブル）、`users` 1件（管理者 `admin`/ADMIN/ACTIVE）と
  `audit_logs` 1件が保持、`audit_logs` の UNIQUE インデックスと `ocr_jobs` も作成済み
- **重要**: 08-28 時点で `documents` は 0 件だった。`uploads/` にある PDF 1,307件（バックアップ内）
  / 2,007件（現行）は、いずれも DB 行から参照されていない**テスト成果物**である
- 認証情報は **Unix ソケットの peer 認証**（`host=/var/run/postgresql`）を使うため、
  パスワードを `env` に保存しない構成にできる

#### 🚨 テストが本番のアップロード領域を汚染していた（修正）
- `conftest.py` が `UPLOAD_DIR` を隔離していなかったため、`config.upload_dir` の既定値
  `~/civildx/uploads`（＝本番のアップロード保存先）へテストが実ファイルを書き込んでいた。
  当該ディレクトリは DB から参照されない PDF が約 2,000 件に達し、
  **1 日のテスト実行で 700 件増加**していた
- 修正: `tests/console/conftest.py` と `tests/integration/conftest.py` で
  `UPLOAD_DIR` をセッション毎の一時ディレクトリに設定し、終了時に削除
- 検証: 修正前に 47 テストで増加していたのが、修正後は **25 テスト実行で増加 0 件**、
  一時ディレクトリの残留も 0
- 再発防止: `tests/console/test_environment_isolation.py` を追加し、
  ①既定の本番パスと異なること ②書き込み可能であること ③`DATABASE_URL` が
  リモート（neon.tech 等）を指していないこと を常時検証

### 2026-09-18 (7) — スマホでの操作要素サイズを実測し是正（WCAG 2.5.8）

前項で「横スクロールが出ないこと」は確認したが、それは**スマホ可読性の十分条件ではない**。
操作要素の大きさを実測したところ、基準を下回る要素が実在した。

#### 🟡 実測で判明した違反（WCAG 2.5.8 AA は 24x24 CSS px 以上）
`e2e/responsive.spec.ts` に実測ゲートを追加して計測した結果、初期表示で **11 要素が 24x24 未満**:
- `.ep-icon-btn`（ヘッダの通知・設定ボタン）が **22x22**
- `.ep-nav-btn`（本文ナビ）の高さが約 24px（サブピクセル丸めで 24 未満）

#### 修正
- `.ep-icon-btn` を 22x22 → **28x28**、`.ep-nav-btn` に `min-height: 28px` を付与
- `enterprise.css` に**初のモバイル向けメディアクエリ**（`max-width: 640px`）を追加し、
  現場のスマホ利用を想定して `.ep-icon-btn` を **36x36**、`.ep-nav-item` / `.ep-nav-btn` を
  **min-height 32px** に拡大（トップバーが縦に膨らみすぎない範囲で）
- 是正後の実測: 24x24 未満の操作要素 **0 件**、主要ナビ・アイコンボタンは **32px 以上**

#### 常設ゲート（実測・2段階）
- 全ビュー × 2ビューポートで「24x24 未満の操作要素が無いこと」を検証（AA 相当の下限）
- スマホ幅で「主要ナビとアイコンボタンが 32px 以上であること」を検証
  （空振り検出のため対象要素が 0 件なら失敗させる）
- 違反時は**要素名・クラス・ラベル・実寸を出力**するため、原因の特定に再計測が不要

> 「横スクロールなし」と「タップ領域」は別の基準であり、**前者が通っても後者は保証されない**
> （実際に通っていた）。測定して初めて分かる差だった。

#### 検証
- frontend: **277 passed**、`npm run lint` / `npm run build` exit 0
- Playwright E2E: **25 passed**（新規3件: タップ領域2 + スマホ32px 1）
- テストファイルの解析ミス（`test.describe(` の閉じ括弧欠落）を TypeScript の構文診断で特定して修正

#### 残課題（未検証）
- 文字サイズの可読性、表の可読性（列の窮屈さ）、入力フォームのモバイル操作性は未検証

### 2026-09-18 (6) — 認可の全ルート機械的検査を常設化・検索のN+1解消

前項で発見した `/ocr/*` の認可欠落を受け、**同じクラスの欠陥を人手のレビューに依存せず検出する**
仕組みを追加した。あわせて全ルーターの認可を棚卸しし、検索のN+1を解消した。

#### 🛡 認可の全ルート検査を常設化（再発防止）
- `tests/console/test_route_authorization.py` を追加。FastAPI のルート表と依存関係ツリーを
  内省し、**`/api/**` の全ルートが「明示的な許可リスト」または `get_current_user` のいずれかを
  満たすこと**を機械的に検証する（実HTTPのプローブは行わない）
- 許可リストは「存在しないエントリ」も検出し、**公開面を広げる行為を可視化**する
  （公開ルートは `/api/v1/auth/*` のみに限定されることも検証）
- 検出力の担保: 「認可を忘れたルートを検出できること」「許可リストを尊重すること」の
  ネガティブテストを同梱
- **この検査を書いた直後に `POST /api/v1/auth/m365/login` が未認可として検出された**。
  同エンドポイントは M365 ログインブリッジであり設計上公開（`M365_ALLOWED_NETWORKS` による
  default-deny・レート制限・全件監査）のため、理由コメント付きで許可リストへ明示的に追加した

#### 🔍 全ルーターの認可棚卸し（結果: OCR 以外に欠落なし）
`api/*.py` の全エンドポイントについて、認証・ロール・リソース可視性の適用状況を確認した。
- `notifications`: `current_user.id` でスコープ済み / `m365`・`ai_settings`・`users`: `require_admin`
- `users.get_user`: 本人 or admin / `privacy`: 本人 or admin（削除・エクスポート・同意）
- `ai`: `_check_document_access` → `document_visible` / `search`: 可視性フィルタあり
- `apps`: すべて `get_current_user`
- **欠落していたのは `/ocr/*` のみ**（前項で修正済み）

#### ⚡ 検索のN+1解消
- `search.py::_is_accessible` が**ヒット1件ごとに文書を1回SELECT**していた
  （`limit` は最大100のため、検索1回で最大100本の追加クエリ）
- 修正: 正準の RBAC フィルタ（`visible_documents_query`）を使い、**ヒット全件の可視性を1クエリで解決**
- 索引に残った文書（文書行が既に無い孤児ヒット）は除外されるようになった
  （旧実装は「行が無い＝可視」としていた）
- 検証: クエリ数が件数に比例しないことを回帰テストで固定。**ミューテーションテストで
  旧実装に戻すと 2件→9 SELECT / 12件→19 SELECT と比例して FAIL する**ことを確認

#### 検証
- backend 全体で再実行（`test_search.py` 14件・`test_route_authorization.py` 7件を含む）
- ruff check / format clean

### 2026-09-18 (5) — OCR API の認可欠落の修正・ジョブ永続化・「OCRでないもの」をOCRと表示しない

コード・設定の棚卸しで、`/api/v1/ocr/*` が **OCR を実装していない**こと、加えて
**認可チェックが一切無い**ことを確認し、修正した。

#### 🚨 認可欠落（クロステナントの文書テキスト漏洩）
- `api/ocr.py` の3エンドポイントは `assert_document_visible` を**一度も呼んでいなかった**
  （他の文書系エンドポイント11箇所はすべて呼んでいる）。このため **どの認証ユーザーでも
  任意の `document_id` を指定して他組織の文書テキストを抽出できた**。
  ジョブ取得系も所有者・可視性の検証が無かった
- 修正: `POST /ocr/process` に文書可視性チェックを追加。ジョブ取得系は
  ジョブ→文書を辿って可視性を検証（漏れた job id も無効化）
- 回帰テスト: viewer が非メンバーの文書を 404、他ユーザーのジョブを 404

#### 🚨 マルチワーカーで動作しないジョブストア
- OCR ジョブが `api/ocr.py` の**プロセス内 dict** に保持されていた。
  `docker-compose.prod.yml` は `uvicorn ... --workers ${UVICORN_WORKERS:-4}`（`.env` は 2）で
  起動するため、`GET /ocr/jobs/{job_id}` は**別ワーカーに当たると 404**、
  再起動で結果は消えていた
- 修正: `ocr_jobs` テーブル（model + migration `o5p6q7r8s9t0`）へ永続化。
  `status` は PostgreSQL enum ではなく String にした（enum ラベルのドリフトは
  本セッションで既に P0 を起こしているため）
- migration は `has_table` ガード付き（create_all 期のDBでも二重作成しない。
  このガードを入れ忘れて既存の移行テスト2件が落ち、修正済み）

#### 🟡 「OCR ではないもの」を OCR として提示しない
- 実装は pypdf による**テキストレイヤ抽出**で、OCR エンジンは依存に無い。
  画像のみのPDFでは `(no extractable text — may be image-only PDF)` という
  **結果に見える文字列**を返していた
- 修正: `engine` をレスポンスに追加（現在は `pypdf-text-layer`）。テキストレイヤが無い場合は
  `status="unsupported"` + 理由を返し、`pages` は空にする（プレースホルダを返さない）。
  壊れたPDFは `status="failed"` として区別
- `language` / `enable_vertical` は受け取って**そのまま返す**ようにし、
  現行エンジンが使用しないことを API ドキュメントに明記
- WebUI: 「Tesseract (jpn) で全ページをOCR処理」という**虚偽の説明**を修正し、
  処理オプションがサーバーへ送信されない未実装機能であることを画面に明記。
  Viewer の未選択時に**架空の文書メタ情報**（`県道○○号_詳細図_Rev04.dwg` / 218 MB /
  AutoCAD 2024 / `OCR 処理: 完了 (日本語)`）を実データのように表示していた問題も修正

#### 検証
- backend: `test_ocr.py` **17 passed**（新規・書き直し）、`test_migrations.py` 含め全体で再実行
- migration: fresh SQLite / 既存 local PostgreSQL の双方で `o5p6q7r8s9t0` へ upgrade し
  schema parity OK（17 テーブル）
- frontend: **277 passed**（新規2件: 処理オプション未実装の明示、架空メタ情報の不在）、
  lint / build exit 0、Playwright E2E 22 passed

### 2026-09-18 (4) — WebUI の偽データ表示の修正とレスポンシブ検証ゲートの追加

#### 🚨 承認待ちバッジが偽データ（ハードコード `7`）だった
- 全画面共通のナビゲーションで「ワークフロー」に常時 **`7`** を表示していた
  （`EnterpriseLayout.tsx` の `<span className="ep-nav-badge">7</span>`）。
  実データは `GET /api/v1/stats/` の `pending_approvals` として既に取得可能で、
  ダッシュボード・設定画面は本物の値を使っていた。**ナビだけが固定の偽値を表示**していた
- 修正: 既存の30秒ポーリングに `getStats()` を相乗りさせ（モバイル回線で二重タイマーを作らない）、
  実データを表示。0 件のときはバッジを出さない

#### 🟡 アクセシビリティ（アクセシブル名の破損）
- バッジの数字がボタンのアクセシブル名に連結され、スクリーンリーダーには
  **「ワークフロー7」** と読み上げられていた。バッジに `aria-hidden` を付け、
  ボタンに `aria-label="ワークフロー（承認待ち 7 件）"` を付けて件数を語として伝えるよう修正

#### 🟡 レスポンシブ検証ゲート（実測）
- 評価書は「レスポンシブ対応が tsx 51ファイル中1件のみ」としていたが、これは
  Tailwind ユーティリティの使用数からの**推測**であり、実描画の測定ではなかった
- 実測する E2E を追加（`e2e/responsive.spec.ts`）: mobile 390x844 / tablet 768x1024 で
  初期表示・図書管理・プロジェクト・ワークフロー・監査・ユーザー管理を開き、
  `document.documentElement.scrollWidth <= innerWidth` を検証（はみ出し要素名も出力）。
  あわせて主要コンテンツが実際に可視・操作可能であることを検証
- **実測結果: 横スクロールは発生しない（22/22 PASS）**。ただし
  「横スクロールが出ない」はスマホ可読性の十分条件ではないため、
  タップ領域・文字サイズ・表の可読性は未検証の残課題として残す
  （→ タップ領域は (7) で実測・是正済み。文字サイズと表の可読性は引き続き未検証）
- 監査を誤らせていた**死んだ CSS を削除**: `src/App.css` はどこからも import されておらず
  （`main.tsx` は `index.css`、`EnterpriseLayout` は `enterprise.css` のみ）、
  リポジトリ内で唯一の `@media` 規則がこの未使用ファイルにだけ存在していた

#### 検証
- frontend **275 passed**（新規1件: バッジが実データを表示し、アクセシブル名が正しいこと）
- Playwright E2E **22 passed**（新規16件: 6ビュー × 2ビューポートの横スクロール検証、
  主要コンテンツ可視性、バッジの実データ表示）
- `npm run lint` / `npm run build` exit 0

### 2026-09-18 (3) — 電子納品パッケージのデータ整合性修正（ごみ箱混入・マニフェスト矛盾・無音の破損）

主要業務フロー（国交省 CALS/EC 電子納品）の実HTTP/実PostgreSQL検証で、納品パッケージが
**自らのマニフェストと矛盾し、利用者が削除した文書を納品していた**ことを実測で確認し修正した。

#### 🚨 ごみ箱（削除申請済み）文書が納品パッケージに混入
- 納品対象の抽出が `project_id` のみで絞られており、**利用者が削除した文書（ごみ箱／GDPR Art.17
  で消去待ち・消去済み）まで 国交省への納品物に含まれていた**。INDEX.XML のファイル数にも計上
- 実測: 2件中1件を削除後も `document_count=2`、ZIP に `DRAW_0002.PDF` が入り
  INDEX.XML は `ファイル数="2"` を宣言
- 修正: `deliverable_documents()` を新設し `deletion_requested_at IS NULL` の文書のみを対象化。
  併せて `created_at, id` の明示的順序で DRAW_0001… の採番を**再現可能**にした

#### 🚨 納品パッケージが自らのマニフェストと矛盾（0 バイト PDF の無音混入）
- ファイルが失われた文書（`file_path` は残存）は **0 バイトの PDF** として ZIP に入る一方、
  INDEX.XML は DB の `file_size`（例 2048）を宣言し続けていた。受領側の検証で必ず不一致となり、
  かつ API は **HTTP 200 成功**を返していた
- 修正:
  - `find_unreadable_documents()` で読み取れない文書を検出し、readiness に
    `unreadable_documents`（理由付き）を追加。`ready` は「そのまま梱包可能か」を意味するよう変更
  - **既定は fail-closed（409）**。読み取れない文書名と理由を明示し、復元を促す
  - 明示指定 `allow_partial=true` で「読み取れる分のみ」のパッケージを生成。この場合
    読み取れない文書は **ZIP と INDEX.XML の両方から除外**され、パッケージは常に内部整合。
    省略件数は `X-CivilPDF-Omitted-Documents` ヘッダ・readiness・監査チェーンで通知
  - INDEX.XML のファイルサイズは **実際に梱包したバイト数**を宣言（DB の値ではなく）
- 実測（Local PostgreSQL + 実HTTP）: readiness `ready=false` → 既定 **409**（文書名付き）→
  `allow_partial=true` で 200・**0 バイト PDF なし**・`X-CivilPDF-Omitted-Documents: 1`・
  INDEX.XML のファイル名/サイズが実体と完全一致

#### 🟡 その他の整合性
- INDEX.XML の `ソフトウェアバージョン` が **`v0.7.0` にハードコード**されていた（実際は 0.9.0）。
  `settings.app_version` を参照するよう修正
- 納品パッケージ生成は監査チェーンに記録されていなかった → `electronic_delivery.generated`
  として、梱包件数・省略件数・省略 ID・パッケージサイズを記録
- WebUI: 読み取れない文書と理由を表示し、409 の理由（どの文書が原因か）をエラー表示に反映。
  axios が `responseType: 'blob'` のためエラー本文も Blob で届く点を `deliveryErrorMessage()` で処理

#### 検証
- 実HTTP/実PostgreSQL の納品フロー検証 **12/12 PASS**（上記の実測を含む）
- backend 電子納品テスト **26 passed**（新規 9 件: fail-closed・部分納品・ごみ箱除外・
  マニフェスト整合・バージョン・監査記録・採番の再現性）
- frontend **274 passed**（新規 2 件: 読み取れない文書の表示・409 理由の表示）

### 2026-09-18 (2) — 本番無音障害の検知修正・PostgreSQL ENUM欠落の修正・可用性ハードニング

初動分析で **本番環境が 21 日間の無音障害状態** にあったことを実測で確認し、その検知・防止と、
同時に発見した PostgreSQL 専用の P0 欠陥を修正した。詳細は
`docs/operations/incident-2026-08-29-database-credential.md` 参照。

#### 🚨 本番障害（検知・防止を実装）
- **無音障害の実測**: Neon PostgreSQL の認証情報が 2026-08-29 頃から無効化され、
  DB を参照する本番リクエストがすべて **HTTP 500** を返していた。同時に毎日の
  バックアップが **0 バイトのダンプ** を生成し続けていた（21 日連続失敗）。
  一方 `/health` は DB を見ないため 200 を返し続け、監視は 21 日間「正常」を報告していた
  （旧 `healthcheck-civilpdf.sh` は `HEALTHCHECK: OK`）。
- **readiness 分離**: `GET /health/ready` を追加。`SELECT 1` を実行し DB 不通なら **503** を返す。
  `/health` は liveness 専用として後方互換を維持。本番 `DATABASE_URL` に対する実測で
  `/health` 200・`/health/ready` **503** を確認
- **監視の強化**: `scripts/healthcheck-civilpdf.sh` が `/health/ready` と
  **バックアップ鮮度**（有効バックアップの経過時間、既定 36 時間）を検査対象に追加。
  0 バイトのダンプは「有効なバックアップ」として扱わない。実測で旧版 `OK` → 新版 `DEGRADED`（exit 1）
- **バックアップのアトミック化**: 隠しディレクトリ `.incomplete-<stamp>` に作成し、
  検証後にのみ公開名へリネーム。失敗時は削除するため、
  **失敗した run が「バックアップがある」ように見えることがなくなった**
- **ダンプ検証**: 0 バイト検出に加え `pg_restore --list` で復元可能性を検証してから公開。
  prune は検証済み成功時のみ実行し、`.incomplete-*` も回収
- **起動の耐障害化**: DB 不通でもプロセスは起動し `/health/ready` で 503 を返す
  （クラッシュループ化を回避し、原因を可視化）
- **接続タイムアウト**: PostgreSQL 接続に `DB_CONNECT_TIMEOUT_SECONDS`（既定 5 秒）を導入し、
  DB 不通時に probe / リクエストがハングしないようにした

#### 🚨 PostgreSQL ENUM 欠落（本番専用の P0）
- `documents.status` の **`EDITOR_DRAFT` / `EDITOR_REVIEWED` / `FINALIZED` が PostgreSQL の
  enum に存在しなかった**。SQLAlchemy の `Enum(PyEnum)` は member **name**（大文字）を永続化するが、
  migration `f2b3c4d5e6f7` は **value**（小文字）を追加していたため、
  Editor 連携フロー（sidecar 取込 → `EDITOR_DRAFT`/`EDITOR_REVIEWED`、flatten-check → `FINALIZED`）が
  PostgreSQL/Neon 本番で `invalid input value for enum documentstatus` により失敗していた。
  SQLite は Enum を VARCHAR として保存するため CI は緑のままで、全テストが見逃していた
- migration **`n4o5p6q7r8s9`** で不足していた大文字ラベルを追加（既存データは name 保存のため有効なまま）
- **回帰防止**: `tests/console/test_enum_parity.py` を追加し、CI の
  「Backend Migrations (fresh DB)」ジョブが実 PostgreSQL 上で
  **全 Enum 列の member 名が PG ラベルに存在するか** を検証するようにした
  （SQLite では自動 skip）。事前修正版のラベル集合を再現して FAIL することを確認する
  ネガティブテストを含む
- 実測: 修正前は `INSERT ... 'EDITOR_DRAFT'` が `DataError`、修正後は INSERT/UPDATE ともに成功

#### ⚠️ 可用性・性能（CSV エクスポート）
- `csv_stream_response` は全行を 1 つの `StringIO` に構築してから `StreamingResponse` に渡しており、
  **実質ストリーミングではなかった**。`chunk_rows`（既定 500）単位で yield する真のストリーミングに変更
- `documents/export.csv` は `doc.project` / `doc.owner` を 1 行ずつ遅延ロードしていた（**N+1**）。
  既存の JOIN を再利用する `contains_eager` に変更し、`Query.yield_per` で逐次取得
- 両エクスポートに **上限 `MAX_EXPORT_ROWS`（100,000 件）** を導入。超過時は
  **413 で明示的に失敗**（監査ログは 7 年保持で無制限に成長するため）。
  黙って切り捨てないのは、法令対応のエクスポートが「完全に見えて欠落している」状態が
  明示的なエラーより危険なため
- 実測（Local SQLite, 同一条件）: 修正前は 2 文書→10 SELECT、10 文書→**26 SELECT**（行数比例）。
  修正後は件数に関わらず一定。ミューテーションテストで N+1 回帰テストが実際に FAIL することを確認

#### ⚠️ コンプライアンス（保持ポリシー / GDPR 削除の自動実行）
- 保持期限のアーカイブと GDPR 物理削除は**実装・単体テスト済みだったが、スケジューラに接続されておらず
  本番で一度も実行されていなかった**（管理者が手動で API を叩いた時のみ）
- `services/retention_service.run_retention_cycle()` に 1 パス分を集約し、
  `scripts/retention-job.py`（`--apply` 必須・既定は dry-run）と
  `deploy/civilpdf-retention.service` / `.timer`（毎日 03:30 JST）を追加
- `run_deletion_job` / `archive_expired_documents` に `dry_run` を追加。
  管理者 API も `?dry_run=true` に対応
- **`install-systemd.sh` はこのタイマーを自動有効化しない**（物理削除を伴うため、
  運用担当の明示的な判断で有効化する設計）
- 実測（Local PostgreSQL）: dry-run で対象検出のみ・ファイル無変更 → `--apply` で
  期限切れ文書が `ARCHIVED`、猶予超過文書のファイルが物理削除され `file_path` が NULL 化、
  猶予期間内の文書は無変更、`gdpr_physical_deletion` が監査チェーンへ追記されることを確認

#### 🟡 技術的負債（SQLAlchemy 2.1 互換 / 未使用依存）
- `api/stats.py` が `Document.id.in_(subquery)` に `Subquery` を直接渡しており、SQLAlchemy 2.0 の
  `SAWarning: Coercing Subquery object into a select()` が出ていた（2.1 で削除予定）。
  `select(subquery.c.id)` を明示的に渡すよう修正し、生成 SQL は同一のまま警告を解消
  （テスト実行時の警告が 11 件 → 5 件に減少）
- **未使用依存 `@tanstack/react-router` を削除**。`package.json` に宣言されているが
  `src/` `e2e/` のどこからも import されておらず、ビルド成果物にも含まれていなかった
  （`router-*.js` チャンクは `react-router` のみで構成）。他パッケージからの参照も無し。
  併用している `@tanstack/react-query` は現役のため残置。lock から 97 エントリを削減

#### 検証
- **Runtime 主要業務フロー実検証（Local PostgreSQL + 実 HTTP、27/27 PASS）**:
  `/health` `/health/ready` → 4ロール login → `/auth/me` → RBAC 拒否（viewer の project 作成 403、
  engineer の sidecar 取込 403、viewer の監査CSV 403）→ project 作成 → **PDF 実アップロード** →
  **Editor連携（review-sidecar → `editor_reviewed`/`editor_draft`、flatten-check → `finalized`）** →
  承認ワークフロー起票 → 承認（`approved`）→ 通知 → 全文検索 + reindex → stats →
  CSV エクスポート2種 → ごみ箱/復元 → **監査ハッシュチェーン `chain_valid: true`（15 レコード）**。
  実 HTTP 経由で PostgreSQL ENUM 修正が機能することを実証（修正前は同経路が 500）
- backend: **431 passed / 4 skipped**（新規 31 件: CSV 14・保持 12・health 5。skip は PG 専用 ENUM 検査）
- integration: **20 passed**
- frontend: `npm run test` **272 passed**、**Playwright E2E 6 passed**、`npm run lint` / `npm run build` 成功
  （E2E は `vite preview` の本番ビルドに対して実行。ローカルの Playwright ブラウザが
  バージョン不一致だったため `npx playwright install chromium` で導入してから実行）
- 依存変更後の再検証: `npm audit --audit-level=high` **exit 0**、`npm ci` **exit 0**
  （＝ `package.json` と `package-lock.json` が同期している。CI と同じ条件）、
  再インストール後の `npm run build` も成功
- ruff check / ruff format --check: clean
- frontend: `npm run build` 成功、`npm run test` 272 passed（フロント変更なし）
- Local PostgreSQL: `alembic upgrade head`（`g3c4d5e6f7g8` → `n4o5p6q7r8s9`）後の schema parity OK（16 テーブル）、
  Read/Write・トランザクション rollback・8 並列での監査チェーン採番衝突なし・
  `documents(project_id)` のインデックス使用を EXPLAIN で確認
- `bash -n` / `shellcheck -S warning`: clean

#### 未対応（承認が必要）
- **Neon の `civildx_owner` パスワード再発行と `DATABASE_URL` 更新**（Credential 変更は承認必須）。
  これが完了するまで本番の DB 依存機能は復旧しない
- 復旧後の本番再起動・主要業務フロー実検証・オンデマンドバックアップ・復元訓練

### 2026-09-18 — 本番運用評価に基づく重大リスク修正（CTO並列監査）

セキュリティ・DB・アーキテクチャ・QA/CI・UI/UX/競合の5観点を並列監査し、証跡ベースで
重大リスクを特定・修正した。詳細は `docs/evaluation/2026-09-18-production-readiness-assessment.md` 参照。

- **セキュリティ P0**: MVP公開デモ用認証バイパス（`AUTH_BYPASS`, 未pushのローカルコミット
  7a22585 で導入）が無条件で ADMIN 権限を発行していた不備を修正。`_get_or_create_mvp_viewer_user`
  を新設し、バイパス時は VIEWER 権限のみ付与（書き込み/管理系APIは403で拒否）。DEBUGバイパス
  （開発用、常にADMIN）とは経路を分離。テスト4件追加（`tests/console/test_auth.py`）
- **データ整合性 P0**: `audit_logs.sequence_number` に UNIQUE 制約を追加（migration
  `m3n4o5p6q7r8`）し、`create_chained_audit_log()` に行ロック(`SELECT...FOR UPDATE`)＋衝突時
  リトライを実装。改ざん検知（ハッシュチェーン）の前提だった一意な連番を、DB制約とロックの
  二重で保証（従来はアプリ側の非ロックな読み取り→採番のみで、同時書込みによる連番衝突・
  チェーン破断の余地があった）
- **性能**: `documents(project_id/owner_id/status)` にインデックス追加（migration
  `l2m3n4o5p6q7`）。`list_documents`/`export_documents` が全件フルスキャンしていた状態を解消
- **開発体験**: `config.py` の `Settings` に `extra="ignore"` を追加。リポジトリ直下 `.env`
  （docker-compose用キーを含む）が原因でリポジトリrootからの `pytest` 実行が
  `ValidationError` で即落ちしていた問題を修正
- **セキュリティ（CI）**: frontend の `nanoid`（GHSA-2v37-7h3g-55p8, High）・`browserslist`
  （GHSA-c83g-rgw3-j3cx 等, High）を `package.json` の `overrides` で修正版に固定。直近main CI
  （2026-08-15, run #31864267636）が `npm audit --audit-level=high` で失敗していた原因を解消
  （ローカル再現で exit code 0 を確認。実際のCI再グリーン化は次回push後に確認予定）
- **文書修正**: README「CI 12/12 success」表記が実態（直近main 11/12・1か月未実行）と乖離して
  いたため実態表記へ訂正。`docs/architecture/system-architecture.md` の実装済みルーター一覧を
  5件→実装済み19件へ全面更新（`aiofiles`は使用中、`celery`/`redis`は依存宣言のみで未使用と
  実コードで確認）。`docs/deployment/mvp-preview-environment.md` に AUTH_BYPASS の実態
  （VIEWER権限化）と MVP環境が502で到達不可である事実を追記
- **検証**: 上記変更に対し `tests/console/test_auth.py`（22件）・`alembic upgrade/downgrade`
  往復・frontend vitest（271件）で回帰なしを確認。backend全体テストはローカル環境の実行速度
  制約でフル完走未確認（別途CI経由での確認を推奨、既知の制約として記録）

### 2026-08-13 — MVP / Prototype 公開（v0.9.0）

- **P0 修正**: `LICENSE` に残っていた未解決の Git 競合マーカーを除去（Copyright を Kensan196948G に一本化。GitHub のライセンス検出が復帰）
- **セキュリティ**: `python-jose`（ecdsa PYSEC-2026-1325 の影響）→ `PyJWT 2.13` へ移行し、pip-audit の ignore を撤廃（Issue #106 解消）
- **レート制限**: 認証エンドポイント（`/auth/token`・`/auth/m365/login` 10回/60秒/IP、`/auth/refresh` 30回、パスワード再設定 5回）にスライディングウィンドウ制限を追加（429 + `Retry-After`）
- **CSV エクスポート**: `GET /documents/export.csv`（RBAC 準拠）と `GET /audit-logs/export.csv`（管理者限定・出力自体を監査）。UTF-8 BOM・数式インジェクション対策済み。WebUI に出力ボタンを追加
- **MVP ダミーデータ**: `scripts/seed_demo_data.py`（冪等・`--reset` 対応）— 組織6/ユーザー10/プロジェクト5/文書21（PDF実ファイル）/ワークフロー5/通知/監査チェーン/DX同期/同意記録を架空値で投入
- **MVP 環境**: `docker-compose.mvp.yml`（SQLite + seed 自動投入）、`scripts/mvp-smoke.py`（実 HTTP 15 項目検証）、Cloudflare Tunnel `civilpdf-mvp` を新設
- **公開 URL**: 本番 https://civilpdf.mirai-dx-platform.com/ / MVP https://civilpdf-mvp.mirai-dx-platform.com/
- **文書整合**: README・API リファレンス・要件定義書の実装状態・WebUI 画面一覧・Runbook のバージョン表記を実装と同期。`VERSION` 0.9.0
- **テスト**: 新規 11 件（レート制限 6 + CSV エクスポート 3 + フロント CSV ヘルパー 2）。conftest のテスト鍵を 32 バイト以上へ。CI 実測 691 件（backend 394 + integration 20 + frontend vitest 271 + Playwright 6）・12/12 success

### 2026-08-12 — 本番適用（systemd / SQLite）

- `alembic upgrade head` を本番DBへ適用（h4x5y6z7a8b9 → **k1l2m3n4o5p6**）:
  login lockout・password reset・notifications・**dx_sync_metrics**
- 本番env に `TIMESTAMP_HMAC_KEY` を追加（production fail-fast 対応）
- backend / frontend を再起動し、`GET /api/v1/stats/dx-sync`（401）・
  frontend（HTTP 200）・`dx_sync_metrics` テーブル作成を確認
- バックアップ: `~/civildx-backups/pre-dx-metrics-20260812/`

### 2026-08-12 — 本番DBを Neon PostgreSQL へ移行

- Neon プロジェクト `civilpdf-dx-production`（PG 18.4・aws-ap-southeast-1）を作成し、
  `alembic upgrade head`（k1l2m3n4o5p6）を適用
- `scripts/migrate-sqlite-to-neon.py` を新設し、SQLite → PostgreSQL のデータ移行を実行
  （日時/Boolean/JSON 変換・整数PKシーケンス同期・行数検証を内包）
- `~/.config/civilpdf/civilpdf.env` の `DATABASE_URL` を Neon へ切替・backend 再起動
  （alembic `PostgresqlImpl`・/health 200・/stats/dx-sync 401 を確認）
- `scripts/backup-production.sh` / `deploy/civilpdf-backup.service` を PostgreSQL 対応へ更新
  （pg_dump 18 自動選択・custom format・pg_restore 検証）
- ロールバック手順を docs/deployment/neon-postgresql-migration.md に更新

### 2026-08-12 — 復元訓練の PostgreSQL 対応（Issue #130）

- `scripts/restore-drill.sh` が PostgreSQL バックアップ（`civilpdf.dump`）を検出すると、
  `pg_restore --clean --if-exists --no-owner --no-acl` で復元し、alembic head・uploads 件数・
  /health・認証フローまで検証（`--database-url` / `DRILL_DATABASE_URL` 対応）
- Neon 一時ブランチで実ドリルを実施し **DRILL PASS**（2026-08-12T23:47 JST・訓練後ブランチ削除）
- 全文検索（tsvector + GIN）は実装済みであることを本番 Neon で確認（search_vector 列・GIN インデックス）

### 2026-08-12 — DX 同期監視基盤と sidecar 上限拡大（Editor v1.12.3 連携）

- **`dx_sync_metrics` テーブル新設**（migration `k1l2m3n4o5p6`）— review-sidecar 送信の
  成功/失敗をサーバー側で 1 リクエスト 1 行記録（ミドルウェア `middleware/dx_metrics.py`）。
  監査ログとは独立した SLI 集計用の正本
- **`GET /api/v1/stats/dx-sync` 追加**（Admin 限定）— 総数/成功/失敗/成功率（全体・30日）、
  エラー種別（auth/rbac/not_found/too_large/invalid/server）、直近 6 か月の月次系列
- **sidecar 上限を 2 MiB → 8 MiB に拡大**（`api/editor.py`）— Editor v1.12.3 と整合。
  写真級の印鑑画像が増える場合はクライアント圧縮へ移行（Editor Issue #92）
- テスト: `test_editor_integration.py`（413・metrics 記録 3 件）、`test_stats.py`
  （dx-sync 集計・Admin 限定）を追加

### 2026-08-12 — Phase 1 中核機能（SSO/パスワードリセット/ごみ箱/ページネーション/通知/権限棚卸し/オフサイトバックアップ）

- **OIDC SSO（Entra ID / HENNGE）**: 認可コード + PKCE フロー（`GET /auth/oidc/login` → `GET /auth/oidc/callback`）。JWKS 署名・issuer/audience/nonce 検証、自動プロビジョニング、state httpOnly cookie。MFA は IdP（Conditional Access）で強制。設定手順: `docs/deployment/oidc-sso-setup.md`
- **パスワード再設定**: 自己申請（トークン SHA-256 + 60分期限）と管理者再設定（`POST /users/{id}/password-reset`）。ログイン画面に申請ダイアログ、ユーザー管理に再設定ボタン
- **ごみ箱と復元**: `GET /documents/trash` / `POST /documents/{id}/restore` と UI（一覧から除外・復元可能）
- **サーバーサイドページネーション**: `GET /documents/?include_meta=true` と UI ページャー
- **通知センター**: `notifications` テーブル + API（一覧/未読数/既読化）。ワークフロー作成・次承認者・完了/却下時に自動通知。WebUI ベル（30秒ポーリング）
- **権限棚卸し**: `GET /users/permissions-report`（JSON/CSV、admin のみ・監査記録あり）+ WebUI ボタン
- **GET 系監査**: 文書ダウンロードを `document.downloaded` としてハッシュチェーン監査ログへ記録
- **PostgreSQL 全文検索**: FTS5 に加え PG では `search_vector`（tsvector + GIN）に対応（migration `j1k2l3m4n5o6`）
- **オフサイトバックアップ**: `scripts/backup-offsite.sh`（rclone→R2/S3）+ systemd timer（毎日03:00 JST）
- **セッション管理**: WebUI の 30 分アイドルタイムアウト（自動ログアウト）
- **E2E 拡充**: Playwright 3→6 件（通知バッジ・ページネーション・SSO/パスワード再設定画面）
- **テスト**: 674 件体制（backend 400・frontend 268・playwright 6）

### 2026-08-12 — 本番運用前総合評価とセキュリティ強化（PR #120/#121/#122）

- **セキュリティ（#122）**:
  - RBAC 境界の一元化（`services/access_control.py`）— 文書/プロジェクト/ワークフロー/リビジョン/Editor/電子納品/検索/AI/統計/組織メンバーに組織・プロジェクト所属＋ロール制御。未許可は 404
  - refresh token の API 利用を拒否（access/refresh の type 検証）
  - 本番（DEBUG=false）で `SECRET_KEY` / `TIMESTAMP_HMAC_KEY` 既定値なら起動失敗（fail-fast）
  - M365 非対話ログインを既定拒否化（`M365_ALLOWED_NETWORKS` 必須・`TRUST_PROXY_HEADERS` で X-Forwarded-For 制御）
  - アップロード: PDF マジックバイト検証・プロジェクト所属検証・ストリーミング保存・filename サニタイズ
  - 文書削除を論理削除化（`deletion_requested_at` + archived。物理削除は GDPR バッチへ委譲）
  - 承認ワークフローの順序強制（後続ステップ先行承認は 409）
  - 監査ログ DB 永続化（ログイン/パスワード/文書/ユーザー/プロジェクト/ワークフロー/組織/AI 操作をハッシュチェーン付きで記録）
  - ログイン失敗 5 回で 15 分ロック（Alembic `i1j2k3l4m5n6`）＋管理者 unlock
  - パスワード 8 文字以上＋文字種 2 種以上を強制
  - ユーザー削除の FK ガード・Editor sidecar 2MB 上限・組織メンバー一覧を管理者限定
- **フロントエンド UX/アクセシビリティ（#120）**:
  - 401 リフレッシュの単一フライト化と失敗時クリーンアップ
  - 破壊的操作（文書/プロジェクト削除・ユーザー無効化）の確認ダイアログ
  - モーダルの role/aria-labelledby/Escape/フォーカストラップ（共通フック `useModalDialog`）
  - フォーム label/autoComplete/role=alert、テーブル th scope・横スクロール対応
  - PDF プレビュー iframe sandbox、デモ通知・虚構データの除去、再試行バナー
- **運用・文書・CI（#121）**:
  - Neon/PostgreSQL 移行ガイド・秘密鍵ローテーション手順（`docs/deployment/`）
  - `VERSION`（0.8.0）一元化＋`scripts/verify-version-sync.sh`
  - API リファレンス・WebUI 画面一覧・tech-stack を実装と同期
  - CI に gitleaks・npm audit・ops-checks（bash -n/shellcheck/version sync）・カバレッジ閾値 80% を追加
  - systemd ユニットの `%h` 展開・backup/restore スクリプトの安全ガード
- **テスト**: 657 件体制（backend 388・frontend 266・playwright 3）

### 2026-08-06 — Production Hardening（本番運用可能化）

- **マイグレーション修理（Issue #109）**: `alembic upgrade head` を新規 DB・既存 DB（create_all 由来）・部分適用状態で冪等化。`audit_logs` の正規作成、`ai_settings` の migration 追加、PostgreSQL `ALTER TYPE` の `autocommit_block` 化
- **CI**: SQLite + PostgreSQL の fresh upgrade とモデル完全一致検証ジョブ（`backend-migrations`）を追加
- **デプロイ**: systemd `ExecStartPre=alembic upgrade head` を復活し本番適用済み
- **セキュリティ**: API と HTML（vite dev/preview）双方に CSP / HSTS / nosniff / X-Frame-Options / Referrer-Policy / Permissions-Policy を付与。AuditMiddleware が Bearer トークンから user_id を記録
- **依存関係**: `react-router@8.3.0` / `axios@1.19.0` へ更新し npm audit 0 を再達成
- **運用**: 日次バックアップ（SQLite online backup + uploads + env、14 日保持・systemd timer）、ヘルスチェックスクリプト、運用 Runbook（`docs/operations/runbook.md`）を追加
- **監視/アラート**: 5 分毎ヘルスチェック（systemd timer）＋障害/復旧のメール通知（msmtp・30 分スロットル）。四半期毎のバックアップ復元訓練（`scripts/restore-drill.sh`）を追加し、初回訓練 PASS
- **テスト**: 633 件体制（backend 351・integration 20・frontend 259・playwright 3）

### 追加 (アプリ配信ページ本番化 — PDF Editor Client 配布窓口)

- **リリースノート API** `GET /api/v1/apps/release-notes`（`?channel=stable|beta|insider`）
  - 配信ページのリリースノートをフロント直書きから backend の単一の真実へ移管
- **ビルド情報 API** `GET /api/v1/apps/build-info`
  - 製品/安定版/ビルド番号/コミット/ビルド日/対応OS/最低サポート版を返却
  - `APPS_BUILD_*` 環境変数をリクエスト時読み取り（秘密情報は非掲載）
- **配布物チェックサム**: `APPS_SHA256_<PKG_ID>` から SHA-256 を解決し `releases`/`download` に反映
- **macOS `.pkg` パッケージ**を追加（`.dmg` 維持・MDM/Jamf 一括展開向け）
- **Windows `.msi` インストーラー**を追加（`.exe` と選択式・GPO/SCCM サイレント展開向け）
- 配信ページ UI: リリースノート/ビルド情報ボタンを実 API 化、`dev:mock` で配信ページが動作、展開対象/KPI は「デモ」明示
- 運用手順: `docs/deployment/app-distribution.md` を追加

### 計画中

- アプリ配信: 展開対象/KPI の実 MDM（Intune / Jamf）連携
- PDF Editor デスクトップ本体 + ビルドパイプライン新規構築（Issue #62 / Scope B）

---

## [0.7.0] — 2026-06-01

### 追加 (Phase 7: AI/OCR 統合)

- **AI 文書分類** `POST /api/v1/ai/documents/{id}/classify`
  - Claude Haiku による建設業図面自動分類（平面図/立面図/断面図/構造図/設備図）
  - プロジェクト種別自動タグ付け（土木/建築/設備/道路/橋梁）
  - 分類結果を `Document.tags` + `extra_data["ai_classification"]` に保存
- **AI 構造データ抽出** `POST /api/v1/ai/documents/{id}/extract`
  - 工事名・施工会社・現場住所・金額・工期・担当者・チェックリストを JSON 抽出
- **AI 要約** `GET /api/v1/ai/documents/{id}/summary`
  - 承認者向け 3〜5 行自動サマリー生成
- **セマンティック検索** `GET /api/v1/search/documents`
  - SQLite FTS5 全文検索（unicode61 トークナイザー、プレフィックス検索対応）
  - `mode=semantic` で Claude AI がクエリを建設業専門語に展開（「橋梁」→「bridge, RC構造, 補修…」）
  - `POST /search/documents/reindex` — 管理者向け FTS5 インデックス再構築
  - `GET /search/documents/suggest` — AI クエリ拡張候補
- フロントエンド: Documents ページに AI 分類ボタン・AI タグ列・分類結果モーダル追加
- フロントエンド: AI 検索バー UI（keyword/semantic モード切替・スニペット強調表示）
- `anthropic>=0.40.0` を requirements.txt に追加

### 修正

- **IDOR 脆弱性 [HIGH]** — AI API 全エンドポイントに `_check_document_access()` 追加
  - 非所有者・非管理者への 404 隠蔽（403 ではなく 404 で文書存在を秘匿）
- **XSS 修正** — 検索スニペット表示で `dangerouslySetInnerHTML` → React `split+map` 安全描画
- **SQLite JSON カラム変換** — FTS JOIN 時の tags フィールドを `json.loads()` で安全変換

### テスト追加

- `tests/console/test_ai.py`: AI API 13 件（IDOR 防御テスト含む）
- `tests/console/test_search.py`: Search API 13 件（keyword/semantic/reindex/RBAC）

---

## [0.6.1] — 2026-05-26

### 追加 (Phase 6.1: プロフィール管理 API)

- `PATCH /api/v1/auth/me` — 認証済みユーザーのフルネーム更新
- `POST /api/v1/auth/me/password` — パスワード変更（現在パスワード確認付き）
- Settings ページ: プロフィール編集フォーム・パスワード変更フォーム
- auth テスト 7 件追加（合計 164 件）
- フロントエンドテスト 103 件通過

### 修正

- FastAPI 0.136.3 + starlette 1.1.0 アップグレード（**PYSEC-2026-161** セキュリティ修正）
- `HTTP_422_UNPROCESSABLE_CONTENT` / `HTTP_413_CONTENT_TOO_LARGE` 定数名修正
- conftest DB override を `scope=package` fixture に移動（pytest 干渉解消）
- OCR API: pypdf 実装（stub 削除）

---

## [0.5.1] — 2026-05-19

### 追加 (Phase 5.1: コンプライアンス基盤)

- PDF/A バリデーター（ISO 14289 準拠、pypdf + veraPDF フォールバック）
- GDPR Art.17 削除権（論理削除マーク → 物理削除バッチジョブ）
- ISO 19650 メタデータ UI（文書種別・プロジェクト情報・改訂番号）
- プライバシー管理（同意記録 ConsentRecord、CCPA 対応）
- 保持ポリシー管理（電子帳簿保存法 7 年、書類種別別期間）
- 監査チェーン（SHA-256 ハッシュチェーン、改ざん検知エンドポイント）
- M365 非対話式認証統合（Fernet 暗号化、Client Credentials Flow）
- ワークフロー詳細 UI（承認ステップ操作モーダル、RBAC 承認/却下）
- PDF プレビュー機能（Blob URL + iframe、JWT 保護、Escape/× クローズ）
- E2E 統合テスト 20 件（認証/文書/承認/GDPR/RBAC 5 シナリオ）

---

## [0.4.0] — 2026-05-15

### 追加 (Phase 4: フロントエンド API 接続)

- フロントエンド全画面リアル API 接続（グレースフルフォールバック）
- Dashboard KPI stats API 統合（getStats エンドポイント）
- Projects ページ RBAC + 検索 + 削除テスト（13 件）
- vitest `.claude/` 除外設定（ClaudeOS 内部テスト混入防止）
- Settings ページ実装（プロフィール/システム情報/セキュリティポリシー）

---

## [0.3.0] — 2026-05-12

### 追加 (Phase 3: 監査・M365・PDF)

- 監査ログ機能（AuditLog モデル + API + UI）
- 統計 API（ダッシュボード KPI 集計）
- frontend LAN systemd 公開（dev:lan @ port 5181）
- フロントエンドテスト拡充（Dashboard/Documents/Workflows 等）

---

## [0.2.0] — 2026-05-11

### 追加 (Phase 1–2: 基盤整備)

- FastAPI バックエンド基盤（JWT 認証・RBAC・PDF 管理 API・承認ワークフロー API）
- SQLAlchemy モデル設計（User/Document/Project/Workflow）
- React フロントエンド基盤（Vite + TanStack Query + Zustand）
- Alembic マイグレーション
- Docker Compose
- GitHub Actions CI/CD（lint / test / security scan）
- ユニットテスト 157 件（backend 98% カバレッジ）

---

[Unreleased]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.5.1...v0.6.1
[0.5.1]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.4.0...v0.5.1
[0.4.0]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mirai-construction-dx/CivilPDF-DX/compare/v0.1.0...v0.2.0
