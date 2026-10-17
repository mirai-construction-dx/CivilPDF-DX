# ADR-0006 — リポジトリ間連携の境界と契約

- 状態: Accepted（2026-10-17 / CTO 全権委譲下で決定）
- 決定者: CTO（本セッション）
- 上位決定: `MCDX-ADR-0004`（merge/release governance）、`MCDX-ADR-0010`（staging 環境パターン）
- 関連: [ADR-0005 staging 環境](ADR-0005-staging-environment.md)、`GITHUB_POLICY.md`、`infra/integration/system.json`

## 1. 背景（実測）

Mirai-Construction-DX には 17 リポジトリがあるが、CivilPDF-DX は中央台帳・契約に未登録で、
他のリポジトリからは「存在はするが接続できないシステム」として扱われている。

| 相手 | 実測 | 根拠 |
| --- | --- | --- |
| `Mirai-Platform-Infra` | `system_id` 未登録（「ID が未確定のため未登録: CivilPDF-DX」） | `Mirai-Platform-Infra/systems.yaml:51` |
| `Mirai-Harness-Core` | 登録は mcip / mcah / civil-docs-platform / ceos のみ。`contracts`・`core.lock.json` も無い | `Mirai-Harness-Core/docs/integration-audit-2026-10-05.md:38`、`Mirai-Platform-Infra/docs/inter-repo-integration-register.md:29` |
| `Civil-Docs-Platform` | IF-09「CDP → CivilPDF-DX：確定 PDF の PDF/A 化・電子納品処理の依頼」が要件に存在するが、変換 API は未実装。DB CHECK に宛先 `civilpdf` だけがある | `Civil-Docs-Platform/docs/design-source/…要件定義書…html:468`、`docs/operations/integration-status.md:118`、`migrations/versions/0001_initial_schema.py:397` |
| `Mirai-Construction-Agent-Harness` | blueprint に `mcah_tool → civilpdf`（MCP 経由）と `civilpdf → cde`（確定版登録）のエッジがある | `blueprint/pages/data-ownership.json:79-83`、`overview.json:615-620,688-691` |
| `Mirai-Construction-DX-Portfolio` | `civilpdf | CivilPDF-DX | PDF Product`（MCIP・MCAH の下流） | `docs/design/PORT-BD-001…:71` |
| `Mirai-Architecture-Decisions` | staging 家族パターン `MCDX-ADR-0010` に本リポジトリが準拠済み（ADR-0005） | `adr/MCDX-ADR-0010-staging-environment-pattern.md:59-79` |

**共有 DB は禁止**（ドメイン間の DB 共有を依存禁止に列挙）。したがって連携は
**HTTP / MCP の明示的な契約**で行い、DB を共有しない。

## 2. 決定

### D-1. `system_id = civilpdf`

- 既存の語彙（Portfolio / MCAH blueprint / CDP の outbox 宛先）と一致する `civilpdf` を採用する。
- **中央台帳への登録は本リポジトリの外**（`Mirai-Platform-Infra/systems.yaml`、
  `Mirai-Harness-Core/registries/systems.yaml`）であり、登録 PR は本 ADR を根拠に出す。
- 中央で別 ID が既に発番されていた場合は、その ID を正とし本 ADR とマニフェストを更新する
  （独自 ID の増殖を避ける）。

### D-2. 連携プロトコルは非同期 HTTP ジョブ + MCP

- 同期 RPC で重い変換を呼ばない。`POST` でジョブを作成し、状態を `GET` で返す。
- 冪等性キー（`Idempotency-Key`）を必須にし、再送で二重実行しない。
- サービス間認証は共有秘密による HMAC（`X-CivilPDF-Timestamp` / `X-CivilPDF-Signature`）とし、
  replay window を設ける。人間ユーザーの JWT とは別系統にする。
- MCP は読み取り系ツールのみを公開し、`Mirai-Harness-Core` の allowlist 登録後に有効化する。

### D-3. データ所有権

| ドメイン | 所有者 | 備考 |
| --- | --- | --- |
| 文書・版・承認・監査証跡・電子納品パッケージ | CivilPDF-DX | 他システムは API 経由で参照する |
| CDE レコード | Civil-Docs-Platform | 承認確定後に CivilPDF-DX が登録を要求する |
| Core 契約（`contracts`） | Mirai-Harness-Core | 本リポジトリは pin して消費する |

所有権の正本は `infra/integration/system.json` の `ownership`。

### D-4. Core 契約の pin を連携の前提条件にする

MCP 公開・イベント連携より前に `core.lock.json` + `contracts/` を固定する。
それまでは「未統合（`not-integrated`）」と明示し、実装済みと主張しない。

### D-5. 未実装を実装済みと書かない

マニフェストの `status` は `implemented` / `planned` / `not-implemented` / `not-integrated` のみ。
`planned` は「契約は決めたがコードが無い」、`not-implemented` は「契約も未確定」を意味する。
`scripts/verify-integration-manifest.py` が語彙と参照ファイルの実在を検査する。

### D-6. Core のシステム台帳には「前提が揃うまで」登録しない

Mirai-Platform-Infra の `systems.yaml` には **2026-10-17 に `civilpdf` として登録**した
（PR: Mirai-Platform-Infra #62。`uses_core: false` / `production: false`）。

一方、Mirai-Harness-Core の `registries/systems.yaml` は `audience` と `db_schema` を
必須とする。CivilPDF-DX は Core 共有 DB を利用せず（D-3）、MCP audience も未公開である。
空文字や架空の `db_schema` で埋めると「共有 DB を使っている」「MCP を公開済み」と
読めてしまうため、**Core pin と MCP サーバ公開が済むまで Core 台帳へは登録しない**。
手順は [inter-repo-registration.md](../operations/inter-repo-registration.md) §3 に置く。

## 3. インターフェース一覧（現時点）

| ID | 方向 | プロトコル | 状態 | 契約 |
| --- | --- | --- | --- | --- |
| `civilpdf.integration-discovery` | 受信（任意 → CivilPDF） | HTTP | **`implemented`** | [Integration API](../api/integration-api.md) |
| `civilpdf.pdf-postprocess` | 受信（CDP → CivilPDF） | HTTP | `planned` | [CDP IF-09 契約案](../api/cdp-if-09-contract.md) |
| `civilpdf.mcp` | 受信（MCAH → CivilPDF） | MCP | `not-implemented` | — |
| `core.contracts` | 消費（Core → CivilPDF） | vendored-contracts | `not-integrated` | Core `docs/consumer-guide.md` |
| `cdp.cde-registration` | 送信（CivilPDF → CDP） | HTTP | `not-implemented` | CDP 側に受入 API なし |

`civilpdf.integration-discovery` は `GET /api/v1/integration/catalog`（公開）と
`GET /api/v1/integration/ping`（HMAC 署名必須）で構成する。実装は
`src/console/backend/api/integration.py` / `services/service_auth.py`。
`catalog` は本 ADR のマニフェストと一致することをテストで固定している。

## 4. 人間ゲート（この ADR では自動化しない）

1. 中央台帳（Infra / Core）への `civilpdf` 登録
2. MCP allowlist への追加
3. 本番 secret・Cloudflare Access の作成
4. `MCDX-ADR-0004` 決定 3 に基づく公開 DNS 追加の Approval PR

## 5. 検証

```bash
python scripts/verify-integration-manifest.py
python scripts/verify-integration-manifest.py --check-siblings   # ローカルに兄弟 repo がある場合
```

CI では `scripts/verify-version-sync.sh` から実行され、`ops-checks` の中で落ちる。
