# CivilPDF-DX 運用 Runbook

**文書番号:** CPDF-OPS-001  
**対象:** 本番ホスト（`civilpdf.mirai-dx-platform.com` / Docker Compose + Cloudflare Tunnel + systemd 運用ユニット）  
**最終更新:** 2026-09-18

---

## 1. 本番構成の一覧（2026-09-18 実測）

| 項目 | 値 |
|---|---|
| 公開 URL | `https://civilpdf.mirai-dx-platform.com/` |
| TLS | Cloudflare（エッジで終端。オリジンは 127.0.0.1 のみバインド） |
| アプリ本体 | **docker compose スタック**（`docker-compose.prod.yml`・db + backend + frontend の3コンテナ） |
| Frontend | nginx + SPA + `/api/` リバースプロキシ（`127.0.0.1:18970`） |
| Backend | uvicorn ×N（コンテナ内 8000。起動時に `alembic upgrade head` を適用） |
| DB | **PostgreSQL 16**（compose `db` コンテナ・named volume・**ホストにポート未公開**）。運用は [local-postgresql.md](../deployment/local-postgresql.md) |
| アップロード | named volume `uploaded_files`（コンテナ内 `/app/uploads`） |
| スタック制御 | system unit `civilpdf-dx.service`（`/etc/systemd/system/`） |
| Tunnel | cloudflared（system unit `civilpdf-dx-cloudflared.service` / `~/.cloudflared/civilpdf-dx-config.yml` → `127.0.0.1:18970`） |
| 環境設定 | `<production checkout>/.env`（git 管理外・compose 用）＋ `~/.config/civilpdf/civilpdf.env`（運用スクリプト用・0600） |
| バージョン | 正本はリポジトリ `VERSION`（現在 0.9.0）。`APP_VERSION` でデプロイ時上書き。整合検証は `scripts/verify-version-sync.sh` |

> **旧構成（ホスト直 uvicorn 8180 + vite preview 5182）は 2026-09-18 に退役。**
> 退役手順は §2.1 を参照。

## 2. デプロイ手順（新リリース）

0. リリース前確認: `./scripts/verify-version-sync.sh` で `VERSION`・env 例・文書の整合を確認
1. バックアップ取得: `./scripts/backup-production.sh`
2. リポジトリを main の検証済み commit へ更新（本番チェックアウトは `~/Projects/Mirai-Construction-DX/CivilPDF-DX`。2026-09 の GitHub 組織移管に伴い旧 `~/Projects/Mirai-DX-Project/CivilPDF-DX` から移動・旧パスは消滅。compose プロジェクト名はディレクトリ名 `CivilPDF-DX` 由来の `civilpdf-dx` のままなので、新パスから同じ本番スタックを操作できる。本番 env はこの checkout の `.env`（Git 管理外））。以降の手順（イメージ再ビルド docker compose -f docker-compose.prod.yml up -d --build、スモーク ./scripts/healthcheck-civilpdf.sh、ログ確認 docker compose logs --tail 100 backend）は compose 本番構成で実施する。旧構成（ホスト直 uvicorn 8180 / vite preview 5182）は 2026-09-18 に退役: 旧 civilpdf-backend.service は Neon 失効認証情報（2026-08-29 失効）を参照し続け /health が 200 でも DB 依存リクエストが 500 の状態で稼働していた（2026-09-18 実測）、旧 civilpdf-backup.service は 21日間 Neon への pg_dump に失敗し続けていた。退役手順は deploy/civilpdf-backend.service 等の RETIRED 注記を参照。
3. 反映前の読み取り専用チェック（手順 2 で main を更新した**後**、`up -d --build` の**直前**に実行）: `./scripts/pre-deploy-check.sh`。checkout が main かつ origin/main と一致・追跡ファイルの変更なし・`.env` が group/others に権限なし（600 推奨）・ヘルス/バックアップ鮮度・ロールバック用イメージタグ・配布リンクを確認する。**FAIL が 0 件になるまで再ビルドに進まない**

## 3. バックアップと復旧

### バックアップ
- `deploy/civilpdf-backup.timer` が毎日 02:30 JST に `deploy/civilpdf-backup.service` を起動
- 保存先: `~/civildx-backups/<UTCタイムスタンプ>/`
  - compose 本番（現行）: `civilpdf.dump`（db コンテナ内 pg_dump・版数は必然一致）＋ `uploads.tar.gz`（backend コンテナ内 named volume の tar）＋ `civilpdf.env`（compose の .env・0600）
  - ホスト直 PostgreSQL 運用時: `civilpdf.dump`（pg_dump --format=custom・pg-tools.sh がサーバーと同一メジャーのクライアントを自動選択）＋ `uploads/` ディレクトリ
  - SQLite 運用時: `civilpdf_dev.db`（SQLite online backup API で一貫性保証）＋ `uploads/` ディレクトリ
- 保持: 14 日間（`scripts/backup-production.sh` 内 `RETENTION_DAYS`）
- RPO: 最大 24 時間（timer 起動に失敗した場合に備え、手動実行も可）
- RTO: 目標 30 分（復旧手順は下記）

#### バックアップの成否判定（重要）
`scripts/backup-production.sh` は次の 3 点を保証します。監視・手動確認もこの基準で行ってください。

1. **アトミック公開**: 内容は隠しディレクトリ `.incomplete-<stamp>` に作成し、ダンプ検証後にのみ公開名へリネームします。
   失敗時は `.incomplete-*` が削除されるため、**失敗した run が「バックアップがある」ように見えることはありません**。
2. **サイズ検証**: `civilpdf.dump` が 0 バイトならエラー終了します（`pg_dump` の認証失敗は 0 バイトファイルを残すため）。
3. **復元可能性検証**: `pg_restore --list` でダンプを読み直してから公開します。

そのため「ディレクトリが存在する＝バックアップ成功」ではありません。**有効なバックアップ**は
`.incomplete-*` 以外かつダンプ/DB ファイルが 1 バイト以上あるものだけです。
`scripts/healthcheck-civilpdf.sh` がこの基準で最新バックアップの鮮度（既定 36 時間）を検査します。

> 🚨 **2026-08-29〜2026-09-18 の実障害**: Neon の PostgreSQL 認証情報が無効化され、
> 毎日のバックアップが 0 バイトのダンプを生成し続けました（21 日間）。
> `/health` が DB を見ていなかったため監視は緑のままでした。詳細は
> [インシデント記録](incident-2026-08-29-database-credential.md) を参照してください。

> ⚠️ **SQLite 暫定期間**の backup は `scripts/backup-production.sh`（online backup）を使用します。
> 現在の本番は**ローカル PostgreSQL**（`pg_dump`）です（[ローカル PostgreSQL 運用ガイド](../deployment/local-postgresql.md) §4 バックアップ）。
> `pg_dump`/`pg_restore` は**サーバーと同じメジャー**が必要です（同ガイド「🔴」節を参照）。

### 復旧手順（compose 本番）
1. cd <production checkout> && docker compose -f docker-compose.prod.yml stop backend
2. DB 復元: cat ~/civildx-backups/<stamp>/civilpdf.dump | docker compose -f docker-compose.prod.yml exec -T db pg_restore -U civilpdf -d civilpdf --clean --if-exists --no-owner
3. uploads 復元: cat ~/civildx-backups/<stamp>/uploads.tar.gz | docker compose -f docker-compose.prod.yml exec -T backend tar xzf - -C /app/uploads
4. docker compose -f docker-compose.prod.yml start backend
5. ./scripts/healthcheck-civilpdf.sh と主要機能スモーク

## 4. 監視

- 定期監視: `deploy/civilpdf-monitor.timer` が 5 分毎に `deploy/civilpdf-monitor.service` を起動し、
  `scripts/healthcheck-civilpdf.sh` を実行。検査項目は
  ① backend `/health`（プロセス生存）② **backend `/health/ready`（DB 到達性）**
  ③ frontend ④ 公開 URL ⑤ 認証ゲート ⑥ **最新バックアップの鮮度**
- **`/health` と `/health/ready` の使い分け（重要）**
  - `/health`: liveness。プロセスが応答するかだけを見る（DB には触れない）
  - `/health/ready`: readiness。`SELECT 1` を実行し、DB 不通なら **503** を返す
  - 監視・外形監視・ロードバランサは **`/health/ready`** を見ること。
    `/health` だけを見ると DB 障害を検知できない（2026-08-29 の実障害の直接原因）
- バックアップ鮮度: 有効なバックアップが `CIVILPDF_BACKUP_MAX_AGE_HOURS`（既定 36 時間）より
  古い場合に FAIL。一時的に無効化する場合は `CIVILPDF_SKIP_BACKUP_CHECK=1`
- 外部アラート: 障害検知時に `scripts/alert-notify.sh` が msmtp（Gmail）でメール通知（既定 30 分間隔のスロットリング付き）。復旧時にも 1 回通知
  - 通知先は `CIVILPDF_ALERT_TO`（`~/.config/civilpdf/civilpdf.env`）で変更可
  - 手動テスト: `./scripts/alert-notify.sh --test`
- ログ: `docker compose -f docker-compose.prod.yml logs --tail 100 backend`（frontend/db も同様）。運用ユニットは journalctl --user -u civilpdf-monitor.service 等
- 監査ログ: WebUI 監査ページ（`/api/v1/audit-logs`）＋ DB `audit_logs` の SHA-256 ハッシュチェーン（`/api/v1/audit-logs/verify`）
- 監視ログ: `~/.local/state/civildx-monitor/monitor.log`

### 手動確認コマンド
```bash
# DB 到達性（本番は 200、DB 障害時は 503）
docker compose -f docker-compose.prod.yml exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=10)"
# 総合ヘルスチェック（DB + バックアップ鮮度を含む）
./scripts/healthcheck-civilpdf.sh
```

## 4.2 保持ポリシー / GDPR 削除の自動実行（オプトイン）

保持期限の超過アーカイブと、削除申請から猶予期間を過ぎた文書の物理削除は
`scripts/retention-job.py` が 1 パスで実行します。以前は管理者が
`POST /api/v1/privacy/admin/run-deletion-job` を手動で叩いた時だけ実行されており、
保持期限が実質的に機能していませんでした。

- タイマー: `deploy/civilpdf-retention.timer`（毎日 03:30 JST、バックアップの後）
- **`deploy/install-systemd.sh` はこのタイマーを自動有効化しません**（物理削除を伴うため、
  運用担当の明示的な判断で有効化する設計）
- 有効化手順:
  ```bash
  # まず必ず dry-run で対象を確認する（何も変更しない）
  cd <production checkout> && docker compose -f docker-compose.prod.yml cp scripts/retention-job.py backend:/tmp/ && docker compose -f docker-compose.prod.yml exec -T backend sh -c 'PYTHONPATH=/app python /tmp/retention-job.py --dry-run --grace-days 30'
  systemctl --user enable --now civilpdf-retention.timer
  ```
- 安全装置:
  - `--apply` を付けない限り **必ず dry-run**（タイマー誤設定で削除が走らない）
  - `--grace-days`（既定 30 日）が削除申請から物理削除までの冷却期間
  - 削除対象は「利用者が削除を申請した文書」のみ。猶予期間内の文書は対象外
  - 監査ログ本体は削除しない（法的証跡保持義務）。`gdpr_physical_deletion` を追記
  - 文書レコードは保持し `file_path` を NULL 化（監査チェーンの整合を維持）
- 実行結果: `journalctl --user -u civilpdf-retention.service`、`--json` で機械可読出力
- 手動での即時実行（管理者 API）: `POST /api/v1/privacy/admin/run-deletion-job?dry_run=true`

## 4.1 バックアップ復元訓練（四半期）

- `deploy/civilpdf-restore-drill.timer` が四半期毎（1/4/7/10 月 1 日 10:00 JST）に復元訓練を自動実行
- `scripts/restore-drill.sh` は最新バックアップを一時領域へ復元し、① DB 整合性 ② `alembic upgrade head` 適用 ③ uploads 件数 ④ backend 起動 ⑤ ログイン→`/auth/me`→`/projects` を検証（本番データには触れない）
- 失敗時はアラートメール送信＋`~/.local/state/civildx-drill/drill.log` に記録
- 手動実行: `./scripts/restore-drill.sh`

## 4.3 PDF Editor 配布リンク監視と新版の配布

- **日次監視**: `scripts/monitor-civilpdf.sh`（5 分毎）が、ヘルスチェックの後（EXIT trap）に `scripts/editor-asset-watch.sh` を呼び、
  `CIVILPDF_ASSET_CHECK_INTERVAL`（既定 1440 分＝1 日）に 1 回だけ `scripts/check-editor-assets.py` を実行する（ヘルス監視の終了コードには影響しない）
  - 検査対象は**稼働中の backend コンテナ**（`CIVILPDF_BACKEND_CONTAINER`、既定 `civilpdf-dx-backend-1`）から取る: `APPS_RELEASE_BASE_URL` と、そのイメージの `apps.py` が配っているファイル名。作業ツリーが別ブランチでも、本番の実態を検査する
  - URL が空、またはコンテナが作り直し中で読めない場合はスキップし、`CIVILPDF_ASSET_RETRY_INTERVAL`（既定 60 分）後に再試行する
  - アセットに届かなければ「PDF Editor 配布リンク異常」、検査スクリプト自体が失敗したら「配布リンク検査の実行失敗」を 1 回メール通知する。メール送信に失敗した場合は通知済みにせず再送する。復旧時にも 1 回通知する
  - 手動実行: `./scripts/editor-asset-watch.sh --force`（ログは `~/.local/state/civildx-monitor/monitor.log`）
  - ⚠️ `APPS_RELEASE_BASE_URL` とイメージの版は**同時に**更新すること（env だけ新しいタグにすると、旧イメージのファイル名で 404 と判定されて通知が出る）
- **新版の配布手順**（詳細は [app-distribution.md](../deployment/app-distribution.md) §3）
  1. Editor の Windows インストーラー（`.exe` / `.msi`）を取得し、Editor の更新署名鍵（minisign）で署名を検証する
  2. `gh release create editor-v<版> -R mirai-construction-dx/CivilPDF-DX --latest=false ...` で公開する
  3. `apps.py` の `_VERSION` などを PR で更新してマージする
  4. `APPS_RELEASE_BASE_URL`・`APPS_SHA256_WIN_EXE` / `APPS_SHA256_WIN_MSI` を更新し、compose を再ビルドする
  5. SHA-256 まで確認する（ホストのシェルには本番 env がないので、値を明示して実行する）:
     ```bash
     APPS_SHA256_WIN_EXE=<sha> APPS_SHA256_WIN_MSI=<sha> \
       python scripts/check-editor-assets.py --verify-sha256 --base-url <APPS_RELEASE_BASE_URL>
     ```
     `(sha256 not configured)` と表示された行は、到達性しか確認できていない
- **ロールバック**: `APPS_RELEASE_BASE_URL` を前の版のタグに戻す（または空にして「近日公開予定」表示にする）
- **注意**: monitor の systemd unit は、この作業ツリー（`~/Projects/Mirai-Construction-DX/CivilPDF-DX`）のスクリプトを直接実行している（2026-09-26 確認）。作業が終わったら main を checkout した状態に戻すこと（§8 の共有 checkout の制約を参照）

## 5. ロールバック

1. アプリロールバック: 直前リリースの commit を checkout → frontend 再ビルド → backend/frontend 再起動
2. データロールバック: バックアップから DB・uploads を復元（上記 §3）
3. マイグレーション: 今回のチェーンは冪等。破損時はバックアップ復元を優先し、`alembic downgrade` は証跡保持の観点から自動では実行しない

## 6. セキュリティ運用

- シークレット: `~/.config/civilpdf/civilpdf.env` のみ（`SECRET_KEY` / `ANTHROPIC_API_KEY` 等）。ローテーション時は値を変更後 `systemctl --user restart civilpdf-backend.service`
- 依存脆弱性: CI の `pip-audit` / `npm audit` が毎 PR 実行。ecdsa PYSEC-2026-1325 は upstream 修正待ち（Issue #106 で明示管理）
- 秘密情報の漏えい防止: CI の `gitleaks` ジョブが毎 PR 実行。ローカル確認は `gitleaks detect --source .`（[secret-management.md](../deployment/secret-management.md)）
- 鍵ローテーション: `SECRET_KEY` / `TIMESTAMP_HMAC_KEY` / `M365_FERNET_KEY` の手順は [secret-management.md](../deployment/secret-management.md) に集約
- 証明書: Cloudflare が自動管理（更新作業不要）
- アクセス: 公開面はログイン必須。`DEBUG=false` を維持（DEV AUTH BYPASS 無効化）
- 権限棚卸し: ユーザーロール（admin / manager / engineer / viewer）は WebUI 管理画面で四半期ごとに確認推奨
- OIDC SSO（Phase 1）: 設定手順は [oidc-sso-setup.md](../deployment/oidc-sso-setup.md)。MFA は Entra Conditional Access / HENNGE 側で強制
- パスワード再設定: ユーザーはログイン画面「パスワードを忘れた場合」から申請（メール送信アダプタは将来実装）。管理者は WebUI ユーザー管理 → パスワード再設定で即時対応可能
- 権限棚卸しレポート: WebUI ユーザー管理 → 「権限棚卸し CSV」、または `GET /api/v1/users/permissions-report?format=csv`（admin のみ・監査ログ記録あり）

## 7. 容量・予算

- DB: 本番は **PostgreSQL 16（compose の db コンテナ・named volume）**。開発・テストは SQLite（`src/console/backend/civilpdf_dev.db`）を併用
- スキーマ変更の検証: `docker-compose.prod.yml`（PostgreSQL 16）+ CI の PostgreSQL migration ジョブ
- 構築・移設・バックアップ・復元・ロールバック: [local-postgresql.md](../deployment/local-postgresql.md)
- 監視項目: ディスク使用量（`df -h`）、uploads サイズ、DB サイズ、エラー率（journalctl）

## 7.1 オフサイトバックアップ（Phase 1）

> ℹ️ 2026-09-26 時点で `deploy/civilpdf-offsite-backup.service` は**未導入**（`install-systemd.sh` の対象外・本番では稼働していない）。導入するときは unit を個別にインストールし、timer を有効化する。

- ローカルバックアップ（§3）に加え、rclone で Cloudflare R2 / S3 へ同期可能
- 設定: `CIVILPDF_RCLONE_REMOTE=civildx-r2:civilpdf-backups` を `~/.config/civilpdf/civilpdf.env` に追加し、`rclone config` で remote を事前作成
- 手動実行: `./scripts/backup-offsite.sh`
- systemd 常設: `deploy/civilpdf-offsite-backup.service` / `.timer`（毎日 03:00 JST）を `install-systemd.sh` と同様にリンク
- 注意: ローカルバックアップに失敗している日は同期対象から除外（最新スナップショットのみ同期）

## 8. 既知の制約・残課題

- ✅ **本番 DB を Neon から脱却（2026-09-18 解決）**: Neon の認証情報失効（2026-08-29）に伴い
  Neon を廃止した。**本番データは compose スタックの db コンテナ（PostgreSQL 16）**へ保存されて
  おり、外部DB依存はゼロ。復元訓練（DRILL PASS・2026-09-18 実測）でバックアップ→復元→
  alembic head・認証フローまで検証済み。ホスト直 `civildx_prod` は移設先の構築例として
  保持（[local-postgresql.md](../deployment/local-postgresql.md)）。障害の記録は
  [インシデント記録](incident-2026-08-29-database-credential.md) を参照
- **checkout が 2 系統に分裂している（要設計判断）**: systemd units と本番 compose は
  `~/Projects/Mirai-Construction-DX/CivilPDF-DX`（本番稼働中・2026-09-26 確認）を参照している一方、
  別の作業コピー `~/Projects/Mirai-Admin-Platform/CivilPDF-DX` も存在する。
  どちらも独立した git checkout であり、**変更を一方に入れても他方には反映されない**。
  恒久的には専用リリースディレクトリへ分離することを推奨する
- **共有 checkout の制約**: 本番サービス（systemd units・MVP backend/frontend）と監視/訓練スクリプト、本番 compose のビルドコンテキストはリポジトリの作業ツリー（`~/Projects/Mirai-Construction-DX/CivilPDF-DX`）から起動する。別セッションが feature branch へ checkout を切り替えると、その間スクリプト/コードが一時的に不在になり、monitor timer 等が `203/EXEC` で失敗しうる（2026-08-06 に実測）。運用中は main を checkout した状態を維持し、複数セッションで並行作業する場合は `git worktree` を利用すること。恒久対策は専用リリースディレクトリへの分離（要設計判断）
- PDF Editor 本体は別リポジトリ（CivilPDF-Editor・非公開）で開発。コンソールは配布窓口のみ（Windows だけ提供。macOS は後日対応: Issue #147）。Issue #62・#94 は 2026-09-26 に完了として close
- ✅ ecdsa advisory（旧 Issue #106）: 依存から ecdsa が外れ、CI の ignore も撤去済み。pip-audit・npm audit ともに 0 件（2026-09-26 確認）
- 外部アラートはメール（msmtp/Gmail）のみ。Slack/Teams 等へ拡張する場合は `scripts/alert-notify.sh` を拡張
- 復元訓練は四半期 timer で自動化済み。訓練ログは `~/.local/state/civildx-drill/drill.log`
- バージョン: リポジトリ `VERSION` は 0.9.0。`scripts/verify-version-sync.sh` は CI で毎 PR 実行され、
  `docs/operations/runbook.md` の「現在 0.9.0」表記を含めて同期を検証する。ただし git タグ `v0.9.0` は未付与（リリース時に付与）
- CI 強化（2026-08-12）: `gitleaks`（secret scan）・`npm audit`・スクリプト構文/バージョン整合チェックを追加
- GitHub 保護: ruleset `central-auto-merge`（2026-08-15 作成）が有効で、
  12 個の必須ステータスチェック通過 + squash merge のみ + force push 禁止。
  Backend Lint は 2026-09-26（#146）から `tests/` と `scripts/` も ruff の検査対象
  `main` への直接 push は不可（PR 経由のみ）
