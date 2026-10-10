# CivilPDF-DX — 承認ワークフロー 差戻し・再申請（WEB-WF-005）実装 (2026-10-10)

## 📊 サマリ

| 項目 | 結果 |
| --- | --- |
| 依頼 | 「対象 Repository の既存仕様と開発ルールに沿って依頼機能を実装し、テスト・文書を更新する」 |
| 依頼の特定 | 依頼文に機能名の明示が無かったため、リポジトリ内の未実装要件から **WEB-WF-005 差戻し・再申請**（`docs/requirements.md` §3.2.5）を対象と決定。候補と影響は設計書に記録（後述「依頼の特定」） |
| 変更範囲 | 本リポジトリ内のみ。DB migration・本番設定・認証/権限モデル・commit/push/merge は未実施 |
| 状態 | 実装・テスト・文書更新 完了。独立検証を実施 |

## 🎯 依頼の特定（仕様が曖昧だった点の扱い）

依頼文には実装対象の機能名が無く、リポジトリ内に「依頼機能」という名称の機能も存在しなかった。
推測で確定せず、以下を記録したうえで、要件文書に**仕様が明記されている未実装項目**から選定した。

| 候補 | 出典 | 採否 |
| --- | --- | --- |
| **WEB-WF-005 差戻し・再申請** | `docs/requirements.md` §3.2.5 | **採用**。「任意ステップへの差戻し・再申請フロー」と業務仕様が明記され、承認依頼（承認依頼 → 差戻し → 再申請）の一連の流れを担う |
| WEB-DOC-006 文書ダウンロード（ZIP） | §3.2.4 | 見送り（「依頼」ではなく配布系） |
| WEB-PROJ-004/005 ステータス・工期管理 | §3.2.3 | 見送り（DB カラム追加が必要になり、migration 禁止の制約と両立しにくい） |
| WEB-WF-004/006/007 並列承認・代理承認・期限 | §3.2.5 | 見送り（今回の最小実装と独立性が高く、別タスクが妥当） |

決定と影響は `docs/architecture/workflow-return-resubmit-design.md` の Decision Log（D1〜D12）に記録した。

## ✅ 実装内容

### バックエンド（Lead が担当）

- `src/console/backend/api/schemas.py`: `ApprovalDecision.decision` に `"return"` を追加（`approve` / `reject` / `return`）。既存 2 値の契約は不変。
- `src/console/backend/api/workflows.py`:
  - `decide_step`: `return` で step=`returned` / workflow=`returned` / `completed_at=null` / 文書=`draft`、起票者へ理由つき通知。**先行ステップに承認済みがある場合だけ** 409（承認済みの巻き戻しは仕様が無いため）。**`returned` の間は decide 自体を 409 で拒否**（再申請を経ずに承認完了へ進む抜け道を塞ぐ・設計 D14）
  - `resubmit_workflow`（`POST /{workflow_id}/resubmit`）: 起票者または admin のみ。全ステップを `pending` に戻し、workflow=`in_progress` / 文書=`pending_review`、先頭承認者へ通知
  - 監査アクション: `approve` / `reject` は**従来どおり** `workflow.step.decided`（既存の監査運用・フィルタを壊さない）。差戻しのみ `workflow.step.returned`、再申請は `workflow.resubmitted`（設計 D13）
- **DB migration は不要**（新カラム・新 enum 値なし。文書は既存ラベル `draft` に戻す）

### フロントエンド（fe-impl が担当）

- `src/console/frontend/src/api/workflows.ts`: `decideStep` の union 拡張、`resubmitWorkflow` 追加
- `src/console/frontend/src/pages/Workflows.tsx`: `returned` バッジ、条件付き「差戻し」ボタン（D11）、条件付き「再申請」パネル（D10: admin または文書 owner）、エラー detail 表示
- `src/console/frontend/src/mock/mockAdapter.ts`: `return` / `resubmit` の契約を模擬。`GET /documents/{id}` を追加（owner 判定用）
- テスト: `Workflows.test.tsx` 18→27 件、`mockAdapter.test.ts` 10→13 件

## 🧪 検証（実行したコマンドと結果）

| コマンド | 結果 |
| --- | --- |
| `.venv-mvp/bin/python -m pytest tests/console/test_workflows.py -q` | **29 passed**（既存 13 + 追加 16） |
| 関連 backend 6 ファイル（workflows / authz / route / phase1 / audit / compliance） | **103 passed** |
| `.venv-mvp/bin/python -m pytest tests/console tests/integration -q` | **553 passed / 4 skipped（失敗 0）** — 2026-10-10 の隔離修正後 |
| `.venv-mvp/bin/python -m pytest tests/integration -q` | **20 passed** |
| `.venv-mvp/bin/python -m ruff check src/console/backend/ tests/ scripts/` | All checks passed |
| `.venv-mvp/bin/python -m ruff format --check …` | 127 files already formatted（整形後に再実行） |
| `npm test -- --run`（frontend） | Test Files 34 passed / **Tests 305 passed**（flaky 修正後 3 回連続 green） |
| `npm run lint`（frontend） | エラー 0 |
| `npm run build`（frontend） | 成功（tsc -b && vite build） |
| `npm run format:check` | **実行不可**: ローカル node_modules に `prettier` 未インストール（`prettier: not found`。devDependency には 3.9.9 あり）。代替 `npx --offline prettier --check .` は成功 |

### 既知の flaky（2026-10-10 に修正済み）

`src/test/EditorSyncView.test.tsx > EditorSyncView > loads the document list into the selector` が全 34 ファイル一括実行時にまれに失敗していた（6 回中 1 回）。
原因は **`../api/stats` が未モックで、このファイルが毎テスト実 HTTP を発行していた**こと。全件並列時に所要時間が 865ms まで膨張し、
`waitFor` の既定予算 1000ms の 86.5% を消費していた（直列実行では 227ms に戻ることを実測）。
`vi.mock("../api/stats", …)` と `getDxSyncStats` のモック値を追加して実 I/O を除去（Production code は変更なし）。修正後は 305 passed が 3 回連続。

### 既知の失敗（2026-10-10 に修正済み・環境依存テスト）

1. `tests/console/test_enum_parity.py` の **3 件**と
2. `tests/console/test_health.py::TestReadiness::test_ready_returns_200_when_database_answers` の **1 件**は、
   いずれも **conftest が `DATABASE_URL` を隔離していなかった**ことが原因。`get_db` の差し替えは FastAPI 依存のみを
   覆うため、`main.py` が直接使う `database.engine` は `.env` の PostgreSQL を指したままだった。
   `tests/console/conftest.py` / `tests/integration/conftest.py` の import 前に `DATABASE_URL` を一時 SQLite へ設定して解消。
   再発検知のため `tests/console/test_environment_isolation.py::test_app_engine_is_isolated_from_the_deployed_database`
   を追加（修正を外すと fail することを実証済み）。

いずれも `src/console/backend/api/workflows.py` / `schemas.py` を経由しない（health・enum parity は本変更の
非依存モジュールで、`main.py` / `database.py` / `config.py` / `health.py` は未変更）。本変更は enum の追加も
migration の追加もしていない（`DocumentStatus.DRAFT` は既存ラベルを使用）ため、変更前から同じ結果になる。
CI では「Backend Migrations (fresh DB)」ジョブが migration 後の PostgreSQL で実行する。

## 🔁 Agent Team / SubAgent / Agent Loop

| Round | 実施 | 担当 | 結果 |
| --- | --- | --- | --- |
| R0 | リポジトリ規約・未コミット差分・未実装要件の調査、対象機能の決定 | Lead | 対象=WEB-WF-005。未コミットの `state.json`（hook 生成物）は保持 |
| R1 | 読取専用レコン（並列 2 件） | fe-recon / be-recon | フロントの修正対象 5 ファイル、backend のテスト基盤・enum 制約・権限契約を把握。設計 D1〜D12 を確定 |
| R2 | backend 実装 + テスト追加（Lead）／frontend 実装 + テスト追加（fe-impl）※書込み範囲を分離 | Lead / fe-impl | pytest 24 passed、frontend 298 passed、lint/build 成功 |
| R3 | 独立検証（コード・権限・テスト・文書・範囲） | verifier | High 1・Medium 3・Low 5 の指摘。うち High-1（監査アクション名の改名）と Medium-2/3（差戻し条件の不一致）を修正対象と判定 |
| R4 | 指摘の修正（backend・テスト・設計書） | Lead | 監査アクション名を `workflow.step.decided` に戻し（差戻しのみ新名）、`return` の順序ガードを「先行に approved が無いこと」だけに簡素化、テストを 24→28 件へ |
| R5 | 修正後の再検証（監査アクション名・return 条件・回帰） | verifier | 前回指摘はすべて解消。ただし**新たな回帰を 1 件検出**（差戻し中に先行ステップを承認すると `resubmit` を経ずに承認完了へ到達できる） |
| R6 | 回帰の修正（`returned` 中の decide を 409）＋テスト・設計 D14 追加 | Lead | `pytest tests/console/test_workflows.py` 29 passed |
| R7 | UI 抑止とモックの追従（returned 中は操作ボタンを出さない／returned 中の decide を 409） | fe-impl | frontend 301 passed / lint / build 成功 |
| R7b | モックの二重決定ガードを backend に一致（`Step already decided`） | fe-impl | frontend 302 passed |
| R7c | モックの承認順序ガードを backend に一致 | fe-impl | frontend 303 passed |
| R8 | 最終検証（returned ガード・モック一致・回帰・文書・範囲） | verifier | **Critical / High / Medium の指摘なし**。Low 3 件（モックの 422/404 順序、展開済みフォームの抑止、Editor 値域の記載） |
| R8b | Low 3 件の解消（UI 抑止・モック順序・文書）＋最終テスト | Lead / fe-impl | frontend 305 passed、backend 29 passed、関連 103 passed |

書込み範囲はファイル単位で分離し、同一ファイル・Git index・branch への同時書込みは行っていない。
検証（R3 / R5 / R8）は読み取り専用で、Lead / fe-impl の書込みと同一ファイルを同時に編集していない。

## ⚠️ 未解決・範囲外

1. **先行ステップ承認後の差戻し（巻き戻し）**: 業務仕様が無いため 409 で拒否（`Cannot return a step after a previous step was approved`）。先行が未承認のままの後続からの差戻しは許可し、再申請で先頭から再開する。要件は「部分実装」として記録
2. **監査ログ画面のアクション表記**: `pages/AuditLogs.tsx` のラベル表は実アクション名（`workflow.created` / `workflow.step.decided` 等）と元から不一致。本タスクでは黙って変更せず、既存の不整合として記録（設計 D12）
3. **`npm run format:check`**: ローカル環境に `prettier` が無く実行不可（`package.json` の devDependency にはある）。CI では実行される
4. **`test_enum_parity.py` / `test_health.py` の失敗と EditorSyncView の flaky**: 上記のとおり 2026-10-10 に修正済み。`test_enum_parity` は CI の PostgreSQL ジョブ（migration 後）でのみ実行される設計は維持
5. **モックの decide 契約**: 二重決定・`returned` 中・承認順序・422/404 の相対順序まで backend と一致させた（R7b/R7c/R8b）。残る差分は「本人 403 を再現しない」（モックにセッションユーザ概念が無い）のみ
6. **並行実行の排他**: 同時 resubmit / 同時 return の行ロックは無し（既存 approve/reject と同型）。実害のある状態破壊経路は検証で確認できなかったが、未対応
7. **`GET /documents/{id}/workflow-status`（Editor 向け）**: `returned` を返しうるため `docs/api/README.md` に値域を明記した。Editor クライアント側の新値対応（`returned` の表示・ハンドリング）は別リポジトリのため未対応
8. **既存の flaky テスト**: `src/test/EditorSyncView.test.tsx > loads the document list into the selector` が全 34 ファイル一括実行時にまれに失敗（6 回中 1 回）。同ファイルは未変更で単体では 8 回連続 green。本タスクでは未対応

## 🔐 制約の順守

- 変更は本リポジトリ内のみ（他 Repository・親 Portfolio は未変更）
- commit / push / merge / branch 操作 / `git add` / `git stash` は未実施
- DB migration・本番設定・認証/権限モデル・課金・DNS・deploy は未変更
- 外部 AI / MCP / SaaS / DB への業務データ送信なし（ローカルのみ）
- 秘密情報（`.env` の値）は読み出し・出力していない

## 📎 参照

- 設計と決定: [docs/architecture/workflow-return-resubmit-design.md](../../docs/architecture/workflow-return-resubmit-design.md)
- 要件: [docs/requirements.md](../../docs/requirements.md) §3.2.5 / §9.3 / §4 API
- 実装: `src/console/backend/api/workflows.py`, `src/console/backend/api/schemas.py`
- テスト: `tests/console/test_workflows.py`, `src/console/frontend/src/test/Workflows.test.tsx`
