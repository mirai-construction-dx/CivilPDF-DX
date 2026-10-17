# CivilPDF-DX staging 環境 Runbook

**文書番号:** CPDF-DEPLOY-STG
**対象:** 本番前の検証（migration リハーサル・スモーク）を担当する運用者・開発者
**最終更新:** 2026-10-16
**決定:** [docs/architecture/ADR-0005-staging-environment.md](../architecture/ADR-0005-staging-environment.md)（`Conforms-to: MCDX-ADR-0010`）
**識別子の正本:** [infra/staging/identifiers.json](../../infra/staging/identifiers.json)

---

## 1. 目的

本番と同じ実行形態（Docker Compose・PostgreSQL 16・`alembic upgrade head`）で起動し、
本番の手前に「本番に触らずに検証できる面」を用意する。dev/MVP では再現しない不具合
（migration の適用漏れ・スキーマ差分・認証フロー・CORS など）を本番前に検出すること、
および本番操作（migration 適用など）のリハーサルを行うことを目的とする。

staging は「本番前の検証環境」であり、**可用性の高い環境（HA）ではない**（§9 の限界を参照）。

## 2. URL と識別子

| 項目                   | 値                                                                       |
| ---------------------- | ------------------------------------------------------------------------ |
| 公開 URL（予定）       | `https://civilpdf-stg.mirai-dx-platform.com`                             |
| ローカル確認           | `http://127.0.0.1:18971`（loopback のみ）                                |
| tunnel 名 / config     | `civilpdf-stg` / `~/.cloudflared/civilpdf-stg-config.yml`                |
| tunnel id              | **未作成（人間ゲート U-1）**                                             |
| Access application     | `civilpdf-stg`（**未作成・人間ゲート U-2**。bypass/everyone を置かない） |
| compose project / file | `civilpdf-stg` / `docker-compose.staging.yml`                            |
| env file / example     | `~/.config/civilpdf/stg.env`（0600）/ `.env.stg.example`                 |
| database / volumes     | `civilpdf_stg` / `stg_postgres_data`, `stg_uploaded_files`               |
| systemd units          | `civilpdf-stg.service`, `civilpdf-stg-cloudflared.service`               |
| ポート帯               | 18970 番台（本番 18970 / staging 18971）                                 |

## 3. 環境の分離

| 観点            | 本番                                                      | MVP                                  | staging                                                     |
| --------------- | --------------------------------------------------------- | ------------------------------------ | ----------------------------------------------------------- |
| 目的            | 実運用                                                    | レビュー・デモ                       | 本番前の検証                                                |
| URL             | `civilpdf.mirai-dx-platform.com`                          | `civilpdf-mvp.mirai-dx-platform.com` | `civilpdf-stg.mirai-dx-platform.com`                        |
| compose project | `civilpdf-dx`                                             | （mvp）                              | `civilpdf-stg`                                              |
| DB              | PostgreSQL 16 `civilpdf`                                  | SQLite                               | PostgreSQL 16 `civilpdf_stg`                                |
| データ          | 実データ                                                  | 架空デモ                             | 架空デモ（seed）                                            |
| 認証            | ログイン必須                                              | AUTH_BYPASS 可                       | ログイン必須（AUTH_BYPASS 不使用）                          |
| 待受            | `127.0.0.1:18970`                                         | `:5183`                              | `127.0.0.1:18971`                                           |
| 入口            | Tunnel `civilpdf-dx` + Access                             | Tunnel `civilpdf-mvp`                | Tunnel `civilpdf-stg` + Access（未作成）                    |
| 秘密            | `~/.config/civilpdf/civilpdf.env`                         | compose 内ダミー                     | `~/.config/civilpdf/stg.env`                                |
| systemd         | `civilpdf-dx.service` + `civilpdf-dx-cloudflared.service` | mvp units                            | `civilpdf-stg.service` + `civilpdf-stg-cloudflared.service` |

staging は本番の DB・Secrets・tunnel・Access・ポートを一切共有しない。
MVP を staging の代わりにしない（SQLite・AUTH_BYPASS では本番の migration 経路を検証できない）。

## 4. 起動（ローカル / ホスト）

前提: 本番チェックアウト（`~/Projects/Mirai-Construction-DX/CivilPDF-DX`）に
`docker-compose.staging.yml` と `.env.stg.example` がある。
staging の秘密は**リポジトリの外**（`~/.config/civilpdf/stg.env`, mode 0600）に置く。
リポジトリ内に `.env.stg` を置く必要はない（置く場合も gitignore 済みのシンボリックリンクに限る）。

```bash
cd ~/Projects/Mirai-Construction-DX/CivilPDF-DX
STG_ENV="$HOME/.config/civilpdf/stg.env"

# 1) 秘密の正本を作成（0600・実値を記入。本番の値を流用しない）
install -m 600 .env.stg.example "$STG_ENV"
$EDITOR "$STG_ENV"                          # 生成例: openssl rand -hex 32

# 2) 起動（project civilpdf-stg・loopback 18971）
#    STG_ENV_FILE で backend の env_file を、--env-file で Compose の変数展開を
#    どちらもリポジトリ外の正本に向ける。本番 checkout の .env（本番秘密）を誤読しない。
STG_ENV_FILE="$STG_ENV" docker compose --env-file "$STG_ENV" \
  -f docker-compose.staging.yml up -d --build

# 3) 状態確認（db / backend はホストへポート公開しない。frontend のみ 127.0.0.1:18971）
STG_ENV_FILE="$STG_ENV" docker compose --env-file "$STG_ENV" \
  -f docker-compose.staging.yml ps

# 4) /health が environment=staging を返すことを確認
curl -s http://127.0.0.1:18971/health
```

`POSTGRES_PASSWORD` が未設定だと compose が起動を拒否する（`${POSTGRES_PASSWORD:?}`）。
db・backend は `ports:` を持たず、ホストへ公開されるのは `127.0.0.1:18971` のみ。
`STG_ENV_FILE` を省略した場合は従来どおりリポジトリ内の `.env.stg` を読む（後方互換）。

### systemd（ホスト常駐）

```bash
sudo install -m 644 deploy/civilpdf-stg.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now civilpdf-stg.service
systemctl status civilpdf-stg.service
```

外部公開（Tunnel）は、**tunnel 作成・Access application 作成（人間ゲート）完了後**に限り有効化する:

```bash
sudo install -m 644 deploy/civilpdf-stg-cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now civilpdf-stg-cloudflared.service
```

## 5. 架空デモデータ（seed）

staging には**実データ（顧客・個人・現場）を入れない。** backend の起動コマンドが
`alembic upgrade head` の後に `scripts/seed_demo_data.py` を実行し、架空データ
（予約ドメイン `.example`）のみを投入する。冪等・再実行可。

手動で再投入・初期化する場合:

```bash
# 冪等に再投入
docker compose --env-file .env.stg -f docker-compose.staging.yml exec -T backend \
  python /scripts/seed_demo_data.py

# デモ行と PDF を削除してから再投入
docker compose --env-file .env.stg -f docker-compose.staging.yml exec -T backend \
  python /scripts/seed_demo_data.py --reset
```

デモ admin（全ロール共通パスワードはデモ専用）:

| 項目     | 値                            |
| -------- | ----------------------------- |
| email    | `admin@demo.civilpdf.example` |
| password | `CivilPDF-Demo-2026!`         |

## 6. スモーク

```bash
# ローカル staging（既定 BASE_URL=http://127.0.0.1:18971）
python scripts/staging-smoke.py

# 公開 staging（Cloudflare Tunnel + Access 経由）
BASE_URL=https://civilpdf-stg.mirai-dx-platform.com python scripts/staging-smoke.py
```

スモークは `/health` が `environment == "staging"` を返すこと（本番/MVP の取り違え防止）を
最初に検証し、ログイン → `auth/me`(admin) → stats → 文書一覧 → 監査ハッシュチェーン検証を行う。
`AUTH_BYPASS` は前提にしない。資格情報は `STAGING_ADMIN_EMAIL` / `STAGING_ADMIN_PASSWORD`
で上書きできる（CI は GitHub Environment `staging` の secrets を使う）。
いずれかが失敗すると非ゼロで終了する。

CI（`.github/workflows/staging-verify.yml`）は `workflow_dispatch` と日次のみで起動し、
**required check ではない**（main の branch protection / ruleset に含めない）。

### CI での検証

PR #164 で追加した staging 定義が黙って退行しないよう、`.github/workflows/ci.yml` に
2 つのガードを置く。

- **`scripts/verify-compose.sh`**（`ops-checks` ジョブ内・既存の required check 名は変更しない）:
  - 各 compose ファイルが well-formed であること
    （`docker compose -f <file> config --no-interpolate -q`）。
  - 解決済み config を解析し、`docker-compose.staging.yml` が project `civilpdf-stg` で
    あること、公開ホストポートが frontend の `127.0.0.1`（loopback 限定）ただ 1 つで
    あること、`db` / `backend` がホストへポート公開しないことを検証する。
    さらに `docker-compose.prod.yml` の `db` / `backend` がホストへポート公開しないことも検証する。
  - 各チェックを PASS/FAIL で出力し、失敗すると非ゼロで終了する。解決は使い捨ての
    `.env` / `.env.stg` を使うため、リポジトリの実 `.env` / `.env.stg` は読まないし書き換えない。
- **`Staging Compose Smoke`**（`staging-compose-smoke`・**required ではない新規 check 名**）:
  - `pull_request` / `push`（`main` / `develop`）で、compose・staging スクリプト・backend など
    関連ファイルが変更されたときだけ `dorny/paths-filter` ゲートで起動する。
  - `openssl rand` で捨ての `.env.stg` を生成し、
    `docker compose --env-file .env.stg -f docker-compose.staging.yml up -d --build` で
    実際に起動、healthy を待って `BASE_URL=http://127.0.0.1:18971 python scripts/staging-smoke.py`
    を実行する。
  - `if: always()` の teardown ステップで必ず
    `docker compose --env-file .env.stg -f docker-compose.staging.yml down -v` する。
  - main の ruleset には加えない（既存の required check 名を追加・変更しない）。

## 7. ロールバック

```bash
# 停止
docker compose --env-file .env.stg -f docker-compose.staging.yml down

# 直前のイメージタグへ戻して再起動（イメージタグを運用している場合）
docker compose --env-file .env.stg -f docker-compose.staging.yml up -d --build
```

- データを初期化して戻す場合は `down -v`（volume 削除）後に `up -d --build`（seed が再投入）。
- migration を戻す場合: `docker compose --env-file .env.stg -f docker-compose.staging.yml exec -T backend alembic downgrade -1`。
- systemd 運用時は `sudo systemctl restart civilpdf-stg.service`。

## 8. 受信範囲・Access・fail-closed

- stg のコンテナが待ち受けるのは **loopback（`127.0.0.1`）のみ**。LAN へ新しい受信ポートを開けない。
- 外部に出す入口は **Cloudflare Tunnel + Access のみ**。本番とは別の tunnel・別の Access application を使う。
- `bypass` / `everyone` のポリシーを置かない。本番 `civilpdf` のポリシーを流用しない。
- **Access が用意できない間は stg を公開しない（fail closed）。** tunnel / DNS / Access は未作成であり、
  作成は人間ゲート（§10）。公開 DNS・custom domain の追加は `MCDX-ADR-0004` 決定 3 の Approval PR 対象。

## 9. 限界

- stg は**開発ホストの compose スタック**である。電源断・再起動・ホスト障害で**本番と同時に落ちる**。
  stg は「本番に触らずに検証する面」であって**可用性の高い検証環境ではない**。
- `MCDX-ADR-0002` は「新しく本番に出すアプリは Docker で動かさない」と定めるが、stg は本番ではないため
  これに抵触しない。ただし本番の実行形態との差（本番も compose であるため差は小さい）は残る。
- frontend の stg 画面マーカーは**別 PR** で対応する（本ドキュメントの時点では未実装）。

## 10. 人間ゲート（未解決・UNRESOLVED）

以下は AI が作成・適用しない。完了するまで stg を公開しない。

| #   | 事項                                                                                              | 担当         |
| --- | ------------------------------------------------------------------------------------------------- | ------------ |
| U-1 | Cloudflare Tunnel `civilpdf-stg` の作成と DNS レコード `civilpdf-stg` の追加                      | human kensan |
| U-2 | Access application `civilpdf-stg` とポリシーの作成（bypass/everyone を置かない）                  | human kensan |
| U-3 | ~~`~/.config/civilpdf/stg.env` の実値~~ **解消 2026-10-17**（0600 で作成し DB ロールと整合）      | —            |
| U-4 | `civilpdf_stg` の保持期間                                                                         | DevOps       |
| U-5 | ~~frontend の stg 画面マーカー実装~~ **解消 2026-10-17**（PR #167）                               | —            |

> 2026-10-17 実測: `civilpdf-stg.service` は enabled/active で、再起動後も healthy。
> `/health` は `environment=staging`、スモークは 7/7 PASS、DB は `alembic upgrade head` 済み。
> 監視は `civilpdf-stg-monitor.timer`（5 分毎）。残る公開ゲートは U-1/U-2 のみ。
