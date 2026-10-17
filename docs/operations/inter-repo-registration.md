# リポジトリ間登録の Runbook

- 決定: [ADR-0006](../architecture/ADR-0006-cross-repo-integration.md)
- マニフェスト: `infra/integration/system.json`
- 検証: `python scripts/verify-integration-manifest.py`

CivilPDF-DX は `system_id = civilpdf` を宣言しているが、中央台帳への登録は
**本リポジトリの外**で行う。登録が完了するまで `registration.*` は `pending` のままにする。

## 1. 前提

| 項目 | 値 |
| --- | --- |
| system_id | `civilpdf` |
| repository | `mirai-construction-dx/CivilPDF-DX` |
| staging FQDN | `civilpdf-stg.mirai-dx-platform.com`（未公開・人間ゲート） |
| staging identifiers | `infra/staging/identifiers.json` |
| 連携 ADR | `docs/architecture/ADR-0006-cross-repo-integration.md` |

> 中央で別 ID が既に発番されていた場合は、その ID を正として ADR-0006 と
> `infra/integration/system.json` を更新する（独自 ID を増やさない）。

## 2. Mirai-Platform-Infra への登録

1. `Mirai-Platform-Infra` の `systems.yaml` に `civilpdf` を追加する PR を作る。
   - 既存エントリのスキーマに合わせる（`system_id` / 表示名 / リポジトリ / 所有者 / 環境）。
   - 参照: `Mirai-Platform-Infra/systems.yaml`（現在 `CivilPDF-DX` は未登録コメントのみ）。
2. CI が通ったら squash merge（中央ポリシー）。
3. マージ後、本リポジトリの `registration.platformInfra` を `registered` に変更する PR を出す。

## 3. Mirai-Harness-Core への登録

1. `Mirai-Harness-Core/registries/systems.yaml` に `civilpdf` を追加する PR を作る。
2. 先に `core.lock.json` + `contracts/` の pin 方法を決める
   （`Mirai-Harness-Core/docs/consumer-guide.md` の `mhc pull` / `mhc verify`）。
3. マージ後、本リポジトリの `registration.harnessCore` を `registered` に、
   `consumes[core.contracts].status` を `implemented` に変更する。

## 4. Civil-Docs-Platform との IF-09 合意

1. [CDP IF-09 契約案](../api/cdp-if-09-contract.md) を CDP 側の担当とレビューする。
2. CDP の outbox アダプタから `POST /api/v1/integration/pdf-jobs` を呼ぶ実装を入れる。
3. 受入テスト（契約書 §6）を通してから `registration.civilDocsPlatform` を `registered` に変更する。

## 5. 完了条件（Definition of Done）

- [ ] `python scripts/verify-integration-manifest.py` が OK
- [ ] 兄弟リポジトリのローカル checkout がある場合
      `python scripts/verify-integration-manifest.py --check-siblings` で
      台帳に `civilpdf` が現れる
- [ ] `registration.*` が実態と一致している（`pending` のまま放置しない）
- [ ] 本番 secret・Access・公開 DNS は MCDX-ADR-0004 決定 3 の人間ゲートを通す
