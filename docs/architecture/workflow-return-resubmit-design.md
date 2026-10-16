# 承認ワークフロー 差戻し・再申請（WEB-WF-005）— 実装設計と決定事項

> 対象: `docs/requirements.md` §3.2.5 `WEB-WF-005 差戻し / 任意ステップへの差戻し・再申請フロー`
> 実装: `src/console/backend/api/workflows.py`, `src/console/backend/api/schemas.py`, `src/console/frontend/src/pages/Workflows.tsx`
> 作成: 2026-10-10（要件が「未着手」であり、要求の原文に詳細な業務仕様が無いため、決定と影響をここに記録する）

## 1. 現状と差分（実装前）

| 項目 | 要求（requirements.md） | 実装前の現状 |
| --- | --- | --- |
| WEB-WF-005 | 任意ステップへの差戻し・再申請フロー | **未着手**。`/workflows/{id}/steps/{sid}/decide` は `approve` / `reject` の 2 値のみ |
| 却下（WEB-WF-002） | ステップ承認・却下・コメント | 実装済。`reject` はワークフローを `rejected` で終端し、文書を `rejected` にする |
| 通知 | 差戻し時の通知（§8.5 通知トリガーに「差戻し」を含む） | 通知種別は `workflow.assigned` / `workflow.decided` のみ |

差戻し（`reject` と違い、赤入れして書き直させたうえで**同じ承認フローを再開できる**状態）と、
起票者による**再申請**が無いため、実務では「却下 → 文書を作り直してワークフローも作り直す」運用になっていた。

## 2. 決定事項（Decision Log）

要求原文に業務仕様の記載が無いため、以下は**推測ではなく明示的な決定**として記録する。
破壊的変更・DB migration の本番適用・権限モデル変更は行わない。

| # | 論点 | 決定 | 理由・影響 |
| --- | --- | --- | --- |
| D1 | 「却下」と「差戻し」の区別 | `ApprovalDecision.decision` に `"return"` を追加し、`reject` は従来どおり**終端**（既存挙動を不変に保つ） | 既存クライアント・既存テストの契約を壊さない。追加値なので後方互換 |
| D2 | 差戻し可能なステップ | ステップの承認者であれば、**先行ステップに承認済みが無い限り**どのステップからでも差戻せる（先行が `pending` のままの後続からの差戻しも許可）。差戻し後は承認フローを先頭から再開する | 承認済みの上流判断を巻き戻す取消仕様が未定義のため、それだけを禁止する。未承認の先行は失う判断が無く、先頭から再開すれば整合する |
| D3 | 差戻し後の各ステータス | ステップ `returned` / ワークフロー `returned` / 文書 `draft`。`workflow.completed_at` は NULL に戻す | 文書を再編集可能な `draft` に戻すのが再申請の前提。**新しい enum 値を DB に追加しない**（下記 D4） |
| D4 | DB スキーマ変更 | **マイグレーション不要**。`approval_steps.status` / `approval_workflows.status` / `document_status` は既存の値域で表現する | `documents.status` は PostgreSQL enum。新ラベルを追加すると本番 DB の migration が必要になり、本タスクの禁止事項に該当する。`draft` / `pending_review` / `rejected` / `approved` は既存ラベル |
| D5 | 再申請の権限 | 文書の `owner_id` 本人、または `admin` | 自分の文書を再申請する操作。管理者は例外として許可（既存の管理者権限の範囲内） |
| D6 | 再申請時の挙動 | 全ステップを `pending` に戻し、先頭承認者へ通知。文書は `pending_review`。ワークフローは `in_progress` | 「同じ承認フローを再開する」という再申請の意味を最小の状態遷移で表現。承認者は作成時の並びを維持 |
| D7 | 通知 | 差戻し: `workflow.decided`（起票者へ、理由コメント付き）／再申請: `workflow.assigned`（先頭承認者へ） | 既存の通知種別・通知センターをそのまま利用。新しい種別は追加しない |
| D8 | 監査 | 差戻し `workflow.step.returned`、再申請 `workflow.resubmitted` を `create_chained_audit_log` に追記 | §3.2.6 WEB-AUDIT-001「承認の主要操作を記録」に適合 |
| D9 | 差戻しの記録 | ステップの `comment` と `decided_at` を使う。**新カラムは追加しない** | 理由コメントは既存の `comment` 列で参照可能（AT-WF-007 と同じ扱い） |
| D10 | 再申請ボタンの表示条件（フロント） | 表示条件は **admin である** または **`GET /api/v1/documents/{document_id}` の `owner_id` が自分**。判定できないときは表示しない | `WorkflowResponse` は `document_id` のみで所有者を持たないため、既存の文書 API で所有者を取得する（既存契約を変えない） |
| D11 | 差戻しボタンの表示条件（フロント） | 自分の `pending` ステップのうち、**先行ステップに `approved` が無い**ものだけ「差戻し」を表示 | バックエンドの 409（設計 D2）と一致させ、押せて失敗する UI を作らない |
| D12 | 監査ログ画面の表記 | 本変更では `AuditLogs.tsx` のアクション表を**変更しない** | 同画面のラベル表は元から実アクション名（`workflow.created` / `workflow.step.*`）と不一致（既存の不整合）。既存挙動を本タスクで黙って変えない |
| D13 | 既存の監査アクション名 | `approve` / `reject` は従来どおり `workflow.step.decided` のまま。差戻しは `workflow.step.returned`、再申請は `workflow.resubmitted` | 監査ログの action でフィルタする既存運用（SIEM・CSV 抽出）を壊さない。判断の内訳は `detail.decision` に従来どおり入る |
| D14 | `returned` 中のステップ操作 | 差戻し中（`workflow.status == "returned"`）の `decide` は 409。再申請するまで承認・却下・再差戻しを受け付けない | これを許すと、差戻しされた依頼が `resubmit` を経ずに承認完了へ進み、差戻しの統制が無効化される（第 5 ラウンドの独立検証で検出） |

## 3. API 契約（追加分）

| メソッド | パス | 権限 | 成功 | 主なエラー |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/workflows/{id}/steps/{sid}/decide`（`decision="return"`） | 当該ステップの承認者 | 200 `WorkflowResponse` | 403 承認者以外／409 決定済み・先行に承認済みあり・ワークフローが `returned` 中 |
| POST | `/api/v1/workflows/{id}/steps/{sid}/decide`（`decision="approve"` / `"reject"`） | 当該ステップの承認者 | 200 `WorkflowResponse` | 403 承認者以外／409 決定済み・先行未承認・ワークフローが `returned` 中 |
| POST | `/api/v1/workflows/{id}/resubmit` | 文書 `owner_id` 本人または admin | 200 `WorkflowResponse` | 403 権限外／404 ワークフロー不在／409 `returned` 以外 |

- `decision` の許可値は `approve` / `reject` / `return`。それ以外は 422（既存の `field_validator` を拡張）。
- `WorkflowResponse.status` は `pending` / `in_progress` / `approved` / `rejected` / **`returned`** をとりうる。
- `ApprovalStepResponse.status` は `pending` / `approved` / `rejected` / **`returned`** をとりうる。
- **`returned` 中は decide 不可（409）**: 差戻しされた依頼が再申請を経ずに承認完了へ進むと、差戻しの統制が無効化されるため（設計 D14）。

## 4. 状態遷移

```
[作成] workflow=in_progress, step1=pending, doc=pending_review
   │
   ├─ approve (先行が全て承認済み) ──> step2=pending 通知 …（順次）──> 全承認: workflow=approved, doc=approved
   ├─ reject  (先行が全て承認済み) ──> workflow=rejected, doc=rejected（終端・従来どおり）
   └─ return  (先行に承認済みが無い) ──> step=returned, workflow=returned, doc=draft, 起票者へ通知
                                   │
                                   └─ resubmit（起票者 or admin）──> 全 step=pending,
                                        workflow=in_progress, doc=pending_review, 先頭承認者へ通知
```

補足: `approve` / `reject` は従来どおり「先行ステップが全て承認済み」でなければ 409。
`return` はこの順序規則を適用せず、代わりに「先行に承認済みが無い」ことだけを要求する（D2）。
`workflow.status == "returned"` の間は `decide` 自体を 409 で拒否する（D14）。

## 5. 未確定・範囲外（推測で確定しない）

- 「任意ステップへの差戻し」のうち、**承認済みの上流ステップを巻き戻す**挙動は仕様が無いため対象外（D2）。該当操作は 409 で拒否する。仕様が決まった時点で別途実装する。
- 差戻し理由の必須化（空コメントの扱い）は要求に無いため任意のまま。
- メール通知（§8.5）は Phase 2。本実装はアプリ内通知のみ。
- 承認期限（WEB-WF-007）・代理承認（WEB-WF-006）・並列承認（WEB-WF-004）は対象外。
- `src/console/frontend/src/mock/mockAdapter.ts` は decide のガード（422 → 404 → 二重決定 409 → `returned` 409 → approve/reject 順序 409 → return 順序 409）と detail 文言を本設計に一致させている。差分は **本人 403 を再現しない**点のみ（モックにはセッションユーザの概念が無い）。

## 6. 参照

- `docs/requirements.md` §3.2.4 文書管理、§3.2.5 承認ワークフロー、§3.2.6 監査ログ、§9.3 受け入れ基準
- `docs/architecture/system-architecture.md`
- 実装: `src/console/backend/api/workflows.py`, `src/console/backend/api/schemas.py`
- テスト: `tests/console/test_workflows.py`, `src/console/frontend/src/test/Workflows.test.tsx`
