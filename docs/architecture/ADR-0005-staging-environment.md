---
id: ADR-0005
title: CivilPDF-DX の staging 環境（identifiers SSOT・loopback・Access・DB 分離）
status: accepted
category: hosting-infra
date: 2026-10-16
deciders: ["@Kensan196948G"]
approval: null
affects: [civilpdf-dx]
supersedes: null
superseded_by: null
conforms_to: MCDX-ADR-0010
review_by: 2027-04-16
---

# ADR-0005: CivilPDF-DX の staging 環境

## ステータス

**accepted（ローカル staging 実装・検証: 2026-10-17）。** 対象リポジトリ: CivilPDF-DX。外部公開の承認を意味しない。
`Conforms-to: MCDX-ADR-0010`（全社 staging 家族パターン）。
関連: `MCDX-ADR-0002`（本番の実行基盤）、`MCDX-ADR-0003`（本番 DB と入口）、`MCDX-ADR-0004`（マージとリリース）、
`docs/deployment/mvp-preview-environment.md`（MVP プレビュー環境）、`docs/operations/runbook.md`（本番運用の正本）。

本 ADR は **accepted**（2026-10-17、CTO 全権委譲下で実装・検証済み）。ただし外部公開は
人間ゲート（§未決定 U-1/U-2）が解消されるまで行わない（fail closed）。

## 背景

CivilPDF-DX の公開面は現在 2 つある。

| 環境            | URL                                           | 実体                                                                                                                                                     |
| --------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 本番            | `https://civilpdf.mirai-dx-platform.com/`     | docker compose スタック（`civilpdf-dx`・db + backend + frontend・ローカル PostgreSQL 16）を system unit が制御し、Cloudflare Tunnel `civilpdf-dx` で公開 |
| MVP / Prototype | `https://civilpdf-mvp.mirai-dx-platform.com/` | SQLite + 架空ダミーデータ。レビュー・デモ用で本番の実行形態を練習しない                                                                                  |

本番の手前に「本番の実行形態（PostgreSQL 16 + Alembic + compose スタック + 実データ相当の流れ）で検証できる環境」が無い。
MVP は SQLite・AUTH_BYPASS 前提であり、`docker-compose.mvp.yml` の起動経路は
`alembic upgrade head` を検証しない（`seed_demo_data.py` の `create_all` に依存）。
そのため「dev では再現せず本番に出すまで気付けない欠陥」を本番前に検出する面が無く、
全社 ADR `MCDX-ADR-0010` が定める staging 家族パターンに CivilPDF-DX だけが未対応である。

`MCDX-ADR-0010` は stg の適用を必須としないが、作る場合は 6 項目に従うことを定める。本 ADR はそれに従い、
CivilPDF-DX の staging を **本番と同じ compose 形状・別 DB・loopback 受信・Access 保護** で作る。

## 決定

`MCDX-ADR-0010` の 6 項目を、CivilPDF-DX の具体値に対応させる。値の正本は
`infra/staging/identifiers.json` とし、本 ADR と同時に更新する。

### 1. 名前（hostname `<name>-stg.mirai-dx-platform.com`）

| 項目 | 本番                                     | staging                                      |
| ---- | ---------------------------------------- | -------------------------------------------- |
| FQDN | `civilpdf.mirai-dx-platform.com`         | `civilpdf-stg.mirai-dx-platform.com`         |
| URL  | `https://civilpdf.mirai-dx-platform.com` | `https://civilpdf-stg.mirai-dx-platform.com` |
| zone | `mirai-dx-platform.com`                  | 同一 zone（`mirai-dx-platform.com`）         |

`<name>` は本番 hostname の先頭部分 `civilpdf` と一致させ、`-stg` を付ける。
本リポジトリは静的画面を docker compose の nginx（frontend コンテナ）で配るため、
`MCDX-ADR-0010` が言う Cloudflare Pages プロジェクトは持たない。stg も同じく compose の nginx で配る。

### 2. 入口の保護（Cloudflare Tunnel + Access のみ・fail closed）

- 外部に出す入口は Cloudflare Tunnel + Access に限る。本番とは**別の** tunnel（`civilpdf-stg`）と**別の** Access application（`civilpdf-stg`）を使う。
- `bypass` / `everyone` のポリシーを置かない。本番 `civilpdf` のポリシーを流用しない。
- **Access が用意できない間は stg を公開しない。** tunnel・DNS レコード・Access application は未作成であり、作成は人間ゲート（§未決定 U-1/U-2）。
- stg の公開 DNS・custom domain の追加は `MCDX-ADR-0004` 決定 3 の Approval PR の対象とする。

### 3. 秘密の置き場（値はリポジトリに置かない）

- 正本: `~/.config/civilpdf/stg.env`（mode 0600）。
- リポジトリには**変数名だけ**を `.env.stg.example` として置く（実値は空欄/プレースホルダ）。
- CI へ渡す値は GitHub Environment `staging` に分離する（`STAGING_ADMIN_EMAIL` / `STAGING_ADMIN_PASSWORD`）。
- 本番 `~/.config/civilpdf/civilpdf.env` を流用しない。値は本番と別に生成する。

### 4. 受信の範囲（loopback のみ・ポート帯）

| サービス                     | 本番               | staging            |
| ---------------------------- | ------------------ | ------------------ |
| frontend（唯一の公開ポート） | `127.0.0.1:18970`  | `127.0.0.1:18971`  |
| db / backend                 | ホストへ公開しない | ホストへ公開しない |

CivilPDF-DX のポート帯は **18970 番台（18970 本番 / 18971 staging）** とする。
stg のコンテナが待ち受けるのは loopback（`127.0.0.1`）に限り、LAN へ新しい受信ポートを開けない。
`POSTGRES_PASSWORD` は compose で必須（`${POSTGRES_PASSWORD:?}`）とし、未設定では起動しない。

### 5. DB の分離（stg は本番と別・実データを入れない）

| 項目           | 本番                                                 | staging                                 |
| -------------- | ---------------------------------------------------- | --------------------------------------- |
| DB             | PostgreSQL 16（compose `db` コンテナ・named volume） | PostgreSQL 16（stg 専用 `db` コンテナ） |
| database       | `civilpdf`                                           | `civilpdf_stg`                          |
| volume         | `postgres_data`                                      | `stg_postgres_data`                     |
| uploads volume | `uploaded_files`                                     | `stg_uploaded_files`                    |

stg の DB は本番と共有せず、コピーでも論理レプリカでもない。
**stg に実データ（顧客・個人・現場）を入れない。** stg は `scripts/seed_demo_data.py` の
架空デモデータ（予約ドメイン `.example`）のみを投入する。

### 6. 環境の識別（`staging`・画面マーカー）

- 環境識別子は `staging`（`ENVIRONMENT=staging`）。`development` / `test` と同じ値を使わない。
  これにより `DEBUG=false` のときの `validate_production_settings`（既定鍵での起動拒否）が stg でも効く。
- backend の `/health` は `environment` を返し、stg では `staging` を返す（監視・スモークが本番/MVP と区別する）。
- 画面に stg であることを示すマーカーを置く。**ただし frontend のマーカーは別 PR とする**（本 ADR では扱わない）。
- 構成の制御は systemd（`civilpdf-stg.service` + `civilpdf-stg-cloudflared.service`）で行う。

## 構成（識別子）

正本は `infra/staging/identifiers.json`。主要値:

| 項目                   | 値                                                         |
| ---------------------- | ---------------------------------------------------------- |
| environment            | `staging`                                                  |
| FQDN / URL             | `civilpdf-stg.mirai-dx-platform.com`                       |
| tunnel 名 / config     | `civilpdf-stg` / `~/.cloudflared/civilpdf-stg-config.yml`  |
| tunnel id              | **未作成（null）** — 人間ゲート                            |
| Access application     | `civilpdf-stg` — **未作成** — 人間ゲート                   |
| listen                 | `127.0.0.1:18971`                                          |
| compose project / file | `civilpdf-stg` / `docker-compose.staging.yml`              |
| env file / example     | `~/.config/civilpdf/stg.env` / `.env.stg.example`          |
| database               | `civilpdf_stg`                                             |
| volumes                | `stg_postgres_data`, `stg_uploaded_files`                  |
| units                  | `civilpdf-stg.service`, `civilpdf-stg-cloudflared.service` |

## 本番 / MVP / staging の分離

| 観点     | 本番                              | MVP                                    | staging                                  |
| -------- | --------------------------------- | -------------------------------------- | ---------------------------------------- |
| 目的     | 実運用                            | レビュー・デモ                         | 本番前の検証（migration リハーサル等）   |
| URL      | `civilpdf.mirai-dx-platform.com`  | `civilpdf-mvp.mirai-dx-platform.com`   | `civilpdf-stg.mirai-dx-platform.com`     |
| DB       | compose PostgreSQL 16 `civilpdf`  | SQLite                                 | compose PostgreSQL 16 `civilpdf_stg`     |
| データ   | 実データ                          | 架空デモ                               | 架空デモ（`seed_demo_data.py`）          |
| 実行形態 | compose（prod）                   | compose（dev サーバー/`vite preview`） | compose（prod と同形・Alembic 適用）     |
| 認証     | ログイン必須                      | AUTH_BYPASS 可                         | ログイン必須（AUTH_BYPASS を使わない）   |
| 待受     | `127.0.0.1:18970`                 | `:5183`                                | `127.0.0.1:18971`                        |
| 入口     | Tunnel `civilpdf-dx` + Access     | Tunnel `civilpdf-mvp`                  | Tunnel `civilpdf-stg` + Access（未作成） |
| 秘密     | `~/.config/civilpdf/civilpdf.env` | compose 内ダミー値                     | `~/.config/civilpdf/stg.env`             |

MVP と staging は役割が異なる。MVP は「誰でも見られるデモ」、staging は「本番と同じ実行形態で検証する面」であり、
MVP を staging の代わりにしない（SQLite・AUTH_BYPASS では本番の migration 経路を検証できない）。

## 帰結

### 良い帰結

- 本番と同じ compose 形状（PostgreSQL 16 + `alembic upgrade head`）で起動するため、
  migration・スキーマ・認証フローの欠陥を本番前に検出できる。
- 本番の unit・tunnel・DB・ポートに触らないことが構成として保証される（別名・別ポート・別 DB・別 tunnel）。
- `/health` の `environment` により、監視・スモークが環境を取り違えない。

### 悪い帰結・限界

- **stg は開発ホストの compose スタックである。** 電源断・再起動・ホスト障害で本番と同時に落ちる。
  stg は「本番に触らずに検証する面」であって **可用性の高い検証環境（HA）ではない**。
  この限界は `docs/deployment/staging-environment.md` に明記する。
- `MCDX-ADR-0002` は「新しく本番に出すアプリは Docker で動かさない」と定めるが、本 ADR は stg を compose で動かす。
  stg は本番ではないため同決定に抵触しないが、**stg が本番の実行形態を完全には練習していない**という限界は残る
  （本番も compose である CivilPDF-DX では、この差は他リポジトリより小さい）。
- メモリ・CPU・ローカル PostgreSQL の容量を stg 分だけ余分に使う。
- 別 tunnel・別 Access application を作るため、Cloudflare 側のリソースが 1 組増える（人間ゲート）。

## 未決定（本 ADR が決めないこと・人間ゲート）

未解決の U-1/U-2 は引き続き人間ゲートとし、解消するまで stg を公開しない（fail closed）。U-3/U-5 の完了状況は以下に記録する。U-4 の保持期間は未決定であり、自動削除を有効化しない。

| #   | 未決定事項                                                                                        | 決める担当   | 根拠                   |
| --- | ------------------------------------------------------------------------------------------------- | ------------ | ---------------------- |
| U-1 | staging 用 Cloudflare Tunnel `civilpdf-stg` の作成と DNS レコード `civilpdf-stg` の追加           | human kensan | 本番 zone への書き込み |
| U-2 | staging 用 Access application `civilpdf-stg` とポリシーの作成（bypass/everyone を置かない）       | human kensan | 同上                   |
| U-3 | ~~`~/.config/civilpdf/stg.env` の実値~~ **RESOLVED 2026-10-17**（0600 で作成し、DB ロールと整合） | —            | 秘密の生成             |
| U-4 | `civilpdf_stg` の保持期間（いつ破棄するか）                                                       | DevOps       | 運用                   |
| U-5 | ~~frontend の stg 画面マーカー~~ **RESOLVED 2026-10-17**（PR #167）                               | —            | 本 ADR の範囲外        |

> 2026-10-17 実測: `civilpdf-stg.service` は enabled/active、`/health` は
> `environment=staging`、スモーク 7/7 PASS、DB は `alembic upgrade head` 済み。
> 監視は `civilpdf-stg-monitor.timer`（5 分毎）。公開だけが U-1/U-2 待ちである。

## 検証

機械検証できる項目は `scripts/staging-smoke.py`（`/health` の `environment == "staging"` を含む）と
`scripts/verify-version-sync.sh` が担う。識別子は `infra/staging/identifiers.json` を正本とし、
本 ADR と同時に更新する。CI は `staging-verify.yml`（`workflow_dispatch` / `schedule` のみ・
**required check ではない**）で公開 stg への疎通を確認する。
