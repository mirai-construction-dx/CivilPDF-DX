---
id: ADR-0007
title: AI Provider（Anthropic）の直接呼び出しを期限付きの暫定例外とし、全社 Model Gateway 経由へ移す
status: proposed
category: ai-provider
date: 2026-10-28
deciders: ["@Kensan196948G"]
approval: null
affects: [civilpdf-dx]
supersedes: null
superseded_by: null
review_by: 2026-12-25
---

# ADR-0007: AI Provider（Anthropic）の直接呼び出しを期限付きの暫定例外とし、全社 Model Gateway 経由へ移す

Deviates-from: MCDX-ADR-0005 — バックエンドが Anthropic を直接呼んでいる（文書の分類・抽出・要約、検索語の拡張、接続テスト）。全社 Model Gateway の契約が公開されるまでの暫定例外とし、期限は 2026-12-25（提案値）。

- 状態: **proposed（未承認）**。オーナーの承認前であり、採択された決定ではない。
- 承認: **未承認**（承認者・承認日は空欄）
  - 承認者:
  - 承認日:
- 見直し期限: 2026-12-25（提案値）
- 関連: [adr-draft-ai-provider-route.md](adr-draft-ai-provider-route.md)（起票前の論点整理）、MCDX-ADR-0005、MCDX-ADR-0006、MCDX-ADR-0007

## 背景

全社 ADR MCDX-ADR-0005（proposed）は、Domain Product が AI Provider を直接呼ばず、全社の Model Gateway を経由することを求める。
Gateway の契約が公開されるまでの暫定例外は、条件を満たしたうえでローカル ADR に `Deviates-from` を書くこととしている。
本リポジトリはその例外 ADR を持っていなかった。

### 実装の実測（2026-10-28、`origin/main` `923fd10`）

| 呼び出し箇所 | Provider と方式 | 送る内容 | 有効化の条件 |
| --- | --- | --- | --- |
| `src/console/backend/api/ai.py` `classify_document`（`POST /ai/documents/{id}/classify`） | Anthropic SDK `anthropic.Anthropic(api_key=...).messages.create`（同期・非ストリーム、`max_tokens=256`） | 文書タイトル＋本文（OCR 結果または PDF 抽出テキスト）先頭 3000 字 | 管理者の停止スイッチ ON かつ API キーあり |
| 同 `extract_document_data`（`POST .../extract`） | 同上（`max_tokens=512`） | タイトル＋本文先頭 4000 字 | 同上 |
| 同 `get_document_summary`（`GET .../summary`） | 同上（`max_tokens=256`） | タイトル＋本文先頭 5000 字 | 同上 |
| `src/console/backend/api/search.py` `_expand_query_with_claude` | 同上（モデルは固定の小型モデル） | 利用者の検索語 | 同上。失敗時は元の検索語に戻る |
| `src/console/backend/api/ai_settings.py` `test_ai_connection`（`POST /ai-config/test`、管理者のみ） | 同上（`max_tokens=10`） | 固定文字列 `ping` のみ | **停止スイッチを見ない**（キーがあれば呼ぶ） |

- キーの置き場所: 管理画面から入力し、Fernet で暗号化して DB に保存する。DB に無ければ環境変数 `ANTHROPIC_API_KEY` を使う（`services/ai_settings.py` `get_api_key`）。応答はキーの有無（bool）だけを返す。
- 停止スイッチ: `ai_settings.enabled`（既定 `False`）。設定行が読めないときも無効として扱う（fail closed、`services/ai_settings.py` `is_ai_enabled`）。キーがあるだけでは有効にならない。
- 監査: 文書 3 操作は成功時に `ai.document_classified` / `ai.document_extracted` / `ai.document_summarized`、送信後の失敗時に `ai.document_<op>_failed` をチェーン監査に記録する。記録するのはモデル名などのメタデータだけで、プロンプト・本文・応答は記録しない。**Provider 名の欄は無い**（モデル名から推定はできる）。検索語の拡張と接続テストは監査に記録しない。
  - 更新（PR #179）: `services/ai_audit.py` が、送信の監査 detail を一か所で組み立てる（`provider`=`anthropic`、`model`、`operation`、`sent_chars`、`result`、失敗時は `error_type`）。文書 3 操作は既存のアクション名と既存項目を保ったまま、これらの項目を加える。検索語の拡張は `ai.query_expanded`、接続テストは `ai.connection_tested` として記録する。送信前に拒否した経路は何も送らないので、記録しない。既存の `detail` 列を使うため migration は無い。
- 文書のアクセス制御: 閲覧権限の無い文書・削除申請中の文書は 404 にし、AI に送らない（`_check_document_access`）。
- 実行環境による制限: **無い**。`ENVIRONMENT`（`config.py` の `environment`）を見ておらず、本番・staging でも停止スイッチとキーが揃えば呼ぶ。本番で停止スイッチが ON かどうかは、本 ADR の作成時点で確認していない（値は本番 DB にある）。
  - 更新（PR #178）: 判定関数 `services/ai_settings.py` `direct_call_allowed` を追加した。上表の 5 か所はすべて、停止スイッチ・キー・文書本文より前にこの判定を見る。許可するのは、明示フラグ `AI_DIRECT_CALL_ALLOWED`（既定 false、staging / 本番の compose・env 定義には入れない）が true で、かつ `ENVIRONMENT` が development / test / local のときだけ。それ以外の環境や、設定を読めない場合は拒否する（文書 3 操作と接続テストは 503、検索語の拡張は元の検索語に戻る）。

### MCDX-ADR-0005 決定 2 の条件との照合

| 条件 | 現状 | 判定 |
| --- | --- | --- |
| 本番相当の環境では無効 | 判定関数 `direct_call_allowed` が、明示フラグ（既定 false）と許可リストの `ENVIRONMENT`（development / test / local）の両方を満たすときだけ許可する。production・staging・未知の値では、5 か所とも呼ばない（接続テストを含む） | 充足（PR #178） |
| 既定は `disabled` | 停止スイッチの既定は OFF、fail closed | 充足 |
| Gateway が使えないときに直接呼び出しへ切り替えない | Gateway の経路がまだ無いため、切り替えも無い | 充足（経路追加時に再確認） |
| 送るのは internal 以下のデータだけ | 文書本文を送る。文書には顧客情報・個人情報が含まれうる。区分による送信制御は無い | **未充足** |
| 監査に Provider 名を残す | 5 か所すべてで、Provider に送るたびにチェーン監査へ provider・model・操作種別・操作者・対象文書・送信文字数・結果を記録する（本文・キーは記録しない） | 充足（PR #179） |
| 期限 2026-12-25 | 本 ADR で提案 | 本 ADR で充足（承認後） |

### Gateway 経由へ移せるか

移せる。根拠は次のとおり。

- 呼び出しはすべて「system 1 つ＋user メッセージ 1 つ＋`max_tokens`」の単発・非ストリームで、ツール呼び出しや会話履歴を使っていない。
- 文書 3 操作は `_get_anthropic_client` と `_send_to_ai` の 2 関数に集約されている。検索語の拡張と接続テストを合わせても、置き換え箇所は 4 か所である。
- 停止スイッチ・アクセス制御・監査は呼び出しの外側にあり、経路を変えても残せる。

移行を止めている条件は本リポジトリの外にある。全社 Model Gateway の Domain Product 向け契約（エンドポイント・認証・版管理）が公開されていない（MCDX-ADR-0005 決定 4）。
契約が無いまま独自に接続を作ることは MCDX-ADR-0006 の暫定規則に反するため、採らない。

## 候補と評価

| 観点 | A: 期限付きの暫定例外とし、不足条件を是正する | B: 直ちに直接呼び出しを撤去する | C: Gateway への接続を先に独自実装する |
| --- | --- | --- | --- |
| MCDX-ADR-0005 との整合 | △（期限と条件付き） | ◎ | ✕（契約が無い） |
| 既存機能への影響 | 本番での扱いは是正 1 次第 | 分類・抽出・要約・意味検索が止まる | なし |
| 秘密情報 | 当面キーを持ち続ける | キーを外せる | — |

## 決定（提案）

案 A を提案する。オーナーの承認までは決定ではない。

### 暫定例外の範囲

- 対象は上表の 5 か所に限る。新しい直接呼び出しを足さない。
- Provider は Anthropic に限る。別の Provider を直接呼ぶ実装を足さない。

### 例外を続けるための是正（別 PR で行う。本 PR はコードを変更しない）

1. **本番相当の環境では無効にする。** `ENVIRONMENT` が本番・staging の場合は、停止スイッチが ON でも直接呼び出しを拒否して 503 を返す（接続テストを含む）。本番での機能停止を伴うため、オーナーの判断を経て出す。→ PR #178 で実装。
2. **送る範囲を internal 以下に限る。** 機密区分（MCDX-ADR-0007）の対応付けが決まるまで、非本番では顧客データ・個人情報を含む文書を AI 操作の対象にしない運用とし、画面の注意書きで明示する。
3. **監査に Provider 名を残す。** 既存の `ai.document_*` の detail に `provider: anthropic` を足す（アクション名は変えない）。検索語の拡張と接続テストにも監査を足す。→ PR #179 で実装。
4. **接続テストにも停止スイッチを適用する。**
5. Gateway が使えないときに直接呼び出しへ切り替える実装を作らない（fail closed）。

### 終了条件（Gateway 経由への移行）

1. 全社 Model Gateway の Domain Product 向け契約が版付きで公開されること（MCDX-ADR-0005 決定 4）。
2. 上記の後、`_get_anthropic_client` / `_send_to_ai`、検索語の拡張、接続テストを Gateway のクライアントに置き換え、Anthropic SDK の直接利用と、本リポジトリでの Provider キーの保管をやめる。本番の secret の削除は Approval PR で行う。
3. 監査のアクション名（`ai.document_*`）は移行後も維持する。

### 見直し

- 期限 2026-12-25（提案値）までに終了条件 1 が満たされない場合は、例外の継続か案 B への切り替えを改めて判断し、本 ADR を更新する。

## 影響

- 本 PR は文書の追加だけで、動作は変わらない。
- 承認されると、是正 1〜4 を別 PR で実装する。是正 1 は本番の挙動を変えるため、オーナーの判断を要する。

## 未確認事項

- 本番・staging で停止スイッチが ON になっているか（DB の値）。
- 本番の環境変数に Provider のキーが置かれているか（値は確認しない）。
