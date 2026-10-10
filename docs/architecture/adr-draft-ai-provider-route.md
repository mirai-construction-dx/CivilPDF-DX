# 全社 ADR 起票ドラフト: Domain Product からの AI Provider 直接接続

| 項目 | 値 |
| --- | --- |
| 状態 | **draft（未起票）** — 正本は `Mirai-Architecture-Decisions`。本ファイルは起票前に内容を固めるためのドラフトで、確定文書ではない |
| 起票先 | `Mirai-Architecture-Decisions`（ルート `AGENTS.md` は AI Provider の経路を全社 ADR 事項と定めている） |
| 起票者 | CivilPDF-DX 側の作業セッション（2026-10-10） |
| 関連 | `Mirai-Construction-DX-Portfolio/catalog/repositories.yaml`（civilpdf の relationships / forbidden_connection_types）、ルート `AGENTS.md` §3 |

> ⚠️ 本ドラフトは **CivilPDF-DX リポジトリ内に置いた提案文**です。`Mirai-Architecture-Decisions` への起票・編集は行っていません（他 Repository を変更しない制約）。

## 1. 問題

CivilPDF-DX（`category: domain-product`）は、AI 機能（図面分類・構造化抽出・要約・
セマンティック検索のクエリ拡張）で **Anthropic の SDK を直接呼び出している**。

- `src/console/backend/api/ai.py:94-111` `_get_anthropic_client()` → `anthropic.Anthropic(api_key=...)`
- 呼出し: `classify`（`:167`）／`extract`（`:288`）／`summary`（`:364`）
- 検索のクエリ拡張: `src/console/backend/api/search.py:217-219`

一方、Portfolio のカタログは CivilPDF-DX の関係を次のように設計している。

```yaml
relationships:
  - {kind: integrates, target_id: mcip, connection_type: mcp_tool_gateway}
  - {kind: integrates, target_id: mcah, connection_type: runtime_api, note: "AIはMCAH経由"}
forbidden_connection_types:
  - {type: direct_provider_from_domain_product,
     reason: "Domain ProductからAI Providerへの直接接続は禁止（MCAH経由）"}
```

つまり **設計（MCAH 経由）と実装（直接接続）が乖離**している。カタログの
`evidence_level` は `designed` であり、実装側に MCAH/MCIP のクライアントは存在しない
（`services/` に該当実装なし）。

なお、実装側には次の統制は既にある（この ADR で失ってはならない資産）。

- 管理者の**停止スイッチ**（既定 off・fail closed）: `services/ai_settings.py:66-73`、`api/ai.py:85-91`
- 送信内容の限定: 文書タイトル＋本文先頭 3000〜5000 字（`api/ai.py:170,291,367`）
- 監査: `ai.document_classified` / `ai.document_extracted` / `ai.document_summarized`（チェーン記録）
- API キーは Fernet 暗号化で DB 保管（`services/ai_settings.py:16-28`）、応答は `has_api_key` の bool のみ

## 2. 論点（決定が必要なもの）

| # | 論点 | 選択肢 |
| --- | --- | --- |
| Q1 | Domain Product からの AI 呼出し経路を MCAH/MCIP に寄せるか、現行の直接接続を許容するか | (a) MCAH 経由へ移行 (b) 直接接続を「例外」として明文化 (c) 段階移行 |
| Q2 | 寄せる場合、**モデル選択・キー管理・停止スイッチをどちらが持つか** | MCAH が一元管理 / CivilPDF-DX が保持しつつ経路のみ委譲 |
| Q3 | 文書本文（PII を含み得る）の**越境移転・同意**の判定主体 | MCAH 側のポリシー / CivilPDF-DX 側のゲート（`AI_ALLOW_EXTERNAL_TRANSFER` 等） |
| Q4 | 経路変更時に**既存の監査アクション名**（`ai.document_*`）を維持するか | 維持（推奨） / 変更 |
| Q5 | 停止スイッチの実効性を経路変更後もどう保証するか（全経路が 1 つの判定を通ること） | MCAH 側のゲート + CivilPDF-DX 側の事前判定の二重化 |

## 3. 現時点で判明している制約

- CivilPDF-DX の AI は**管理者が有効化したときだけ**動く（既定 off・fail closed）。
  そのため「誤って外部送信される」リスクは stop switch で抑えられているが、
  **有効化後の送信先・越境移転・同意**の統制は CivilPDF-DX 内に無い。
- `ConsentRecord`（GDPR 同意）はバックエンドで `api/privacy.py` 以外から参照されておらず、
  AI 送信のゲートには使われていない。
- MCP サーバ実装は CivilPDF-DX に存在しない（MCIP 接続は未実装）。

## 4. 推奨（ドラフトとしての提案）

1. **Q1 は (c) 段階移行**を推奨。移行までの間、**直接接続を「管理された例外」として
   全社 ADR に明記**し、例外の条件（停止スイッチ・送信内容の上限・監査・キー暗号化）を
   満たすことを CivilPDF-DX 側でテストで固定する。
2. **Q3 は MCAH 側と CivilPDF-DX 側の二重ゲート**を推奨（片方の設定漏れで送信されない）。
3. **Q4 は維持**を推奨（既存の監査運用・SIEM 連携を壊さない）。
4. 移行完了までは、`docs/compliance.md` の AI 節に「経路は直接接続である」旨を明記する
   （対外的な説明と実装の一致を優先）。

## 5. この ADR が決まるまでの CivilPDF-DX 側の扱い

- コードは変更しない（本ドラフト作成時点の実装を維持）。
- 上記 4 の文書注記は CivilPDF-DX 内で完結する作業として実施可能。
- MCAH/MCIP の接続実装は、経路の決定とインターフェース合意の後に行う。

## 6. 未確認事項

- MCIP/MCAH が公開している IF（バージョン・認証・レート制限・監査の受け渡し）の仕様。
  本 Repository からは正本を確認していない（他 Repository の資料の読取りが必要）。
- 全社 ADR の採番規則・起票手順（`Mirai-Architecture-Decisions/adr/README.md` を確認すること）。
- 本番環境で AI が実際に有効化されているか（停止スイッチの実値は `.env` と DB にあり未確認）。
