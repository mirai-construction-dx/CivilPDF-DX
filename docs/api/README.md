# CivilPDF-DX API リファレンス

> 実装された FastAPI ルーターから 2026-08-13 時点で生成した一覧です。
> OpenAPI の正本はアプリの `/openapi.json`（Swagger UI: `/docs`）です。

## ベース URL

```
https://<your-domain>/api/v1/
```

## 認証

- API は原則 `Authorization: Bearer <access_token>` が必要です。
- トークン取得: `POST /api/v1/auth/token`（フォーム認証）
- トークン更新: `POST /api/v1/auth/refresh`（`refresh_token` のみ利用可能）
- Entra ID / HENNGE ONE OIDC SSO: `GET /auth/oidc/login` → `GET /auth/oidc/callback`（認可コード + PKCE、#124 で実装済み）
- Microsoft 365 は非対話ブリッジ（`POST /api/v1/auth/m365/login`）。既定拒否（`M365_ALLOWED_NETWORKS` 必須）
- 認証不要: `GET /health`、`GET /`

## エンドポイント一覧

### 認証

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/api/v1/auth/token` | メール/パスワードでトークン発行（レート制限あり） |
| POST | `/api/v1/auth/refresh` | refresh token でトークン更新 |
| GET | `/api/v1/auth/me` | ログインユーザー情報 |
| PATCH | `/api/v1/auth/me` | 自分自身のプロフィール更新 |
| POST | `/api/v1/auth/me/password` | パスワード変更 |
| POST | `/api/v1/auth/password-reset/request` | パスワード再設定申請（60分・単回） |
| POST | `/api/v1/auth/password-reset/confirm` | パスワード再設定確定 |
| POST | `/api/v1/auth/m365/login` | M365 非対話ログインブリッジ（ネットワーク制限） |
| GET | `/api/v1/auth/oidc/login` | OIDC SSO 開始（PKCE） |
| GET | `/api/v1/auth/oidc/callback` | OIDC コールバック |

### ユーザー管理

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/users/` | ユーザー一覧 |
| POST | `/api/v1/users/` | ユーザー作成 |
| GET | `/api/v1/users/permissions-report` | 権限棚卸しレポート（admin・JSON/CSV） |
| GET | `/api/v1/users/{user_id}` | ユーザー詳細 |
| PATCH | `/api/v1/users/{user_id}` | ユーザー更新 |
| DELETE | `/api/v1/users/{user_id}` | ユーザー削除（FK ガード付き） |
| POST | `/api/v1/users/{user_id}/password-reset` | 管理者による再設定 |

### PDF 文書管理

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/documents/` | 文書一覧（サーバーサイドページネーション） |
| POST | `/api/v1/documents/` | PDF アップロード（マジックバイト・所属検証） |
| GET | `/api/v1/documents/export.csv` | 可視文書の CSV 出力（RBAC 適用） |
| GET | `/api/v1/documents/trash` | ごみ箱一覧 |
| GET | `/api/v1/documents/{doc_id}` | 文書詳細 |
| PATCH | `/api/v1/documents/{doc_id}` | 文書メタデータ更新 |
| GET | `/api/v1/documents/{doc_id}/download` | PDF ダウンロード（監査記録） |
| POST | `/api/v1/documents/{doc_id}/timestamp` | タイムスタンプ付与 |
| GET | `/api/v1/documents/{doc_id}/timestamp/verify` | タイムスタンプ検証 |
| DELETE | `/api/v1/documents/{doc_id}` | 文書削除（論理削除＝ごみ箱化） |
| POST | `/api/v1/documents/{doc_id}/restore` | ごみ箱から復元 |

### 承認ワークフロー

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/workflows/` | ワークフロー一覧 |
| POST | `/api/v1/workflows/` | ワークフロー作成（多段階・順序強制） |
| GET | `/api/v1/workflows/{workflow_id}` | ワークフロー詳細 |
| POST | `/api/v1/workflows/{workflow_id}/steps/{step_id}/decide` | 承認/却下決定 |

### プロジェクト / 電子納品

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/projects/` | プロジェクト一覧 |
| POST | `/api/v1/projects/` | プロジェクト作成 |
| GET | `/api/v1/projects/{project_id}` | プロジェクト詳細 |
| POST | `/api/v1/projects/{project_id}/members/{user_id}` | メンバー追加 |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | メンバー削除 |
| GET | `/api/v1/projects/{project_id}/electronic-delivery/check` | 電子納品チェック（`ready` は「そのまま梱包可能か」。読み取れない文書は `unreadable_documents` に列挙） |
| POST | `/api/v1/projects/{project_id}/electronic-delivery` | 電子納品 ZIP 生成。読み取れない文書があると **409**（fail-closed）。`?allow_partial=true` で読み取れる分のみ生成（省略件数は `X-CivilPDF-Omitted-Documents` ヘッダ） |

**電子納品パッケージの対象**: 削除申請済み（ごみ箱／GDPR 消去）の文書は常に除外されます。
生成されるパッケージは常に内部整合（INDEX.XML のファイル名・サイズが ZIP 実体と一致）で、
0 バイトの PDF は含まれません。生成は `electronic_delivery.generated` として監査チェーンに記録されます。

### 監査ログ / 統計

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/audit-logs/` | 監査ログ一覧（管理者・ページネーション/フィルタ） |
| GET | `/api/v1/audit-logs/export.csv` | 監査ログ CSV 出力（管理者・出力自体も監査） |
| GET | `/api/v1/audit-logs/verify` | 監査チェーン検証（管理者） |
| GET | `/api/v1/stats/` | 全体統計 |
| GET | `/api/v1/stats/security` | セキュリティイベント統計（管理者） |
| GET | `/api/v1/stats/security-config` | セキュリティ設定統計 |
| GET | `/api/v1/stats/projects` | プロジェクト統計 |
| GET | `/api/v1/stats/daily` | 日次統計 |
| GET | `/api/v1/stats/dx-sync` | DX 同期 SLI（管理者） |

### 通知

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/notifications/` | 通知一覧 |
| GET | `/api/v1/notifications/unread-count` | 未読数 |
| POST | `/api/v1/notifications/{notification_id}/read` | 既読化 |
| POST | `/api/v1/notifications/read-all` | 全既読化 |

### 組織 / M365 / OCR / AI

| メソッド | パス | 説明 |
|---|---|---|
| GET/POST | `/api/v1/organizations/` | 組織一覧/作成 |
| GET | `/api/v1/organizations/tree` | 組織ツリー |
| GET/PATCH/DELETE | `/api/v1/organizations/{org_id}` | 組織詳細/更新/削除 |
| GET | `/api/v1/organizations/{org_id}/members` | 組織メンバー一覧（管理者限定） |
| GET/PUT | `/api/v1/m365/config` | M365 設定取得/更新（管理者） |
| POST | `/api/v1/m365/test-connection` | M365 接続テスト（管理者） |
| GET | `/api/v1/m365/users/lookup` | M365 ユーザー検索 |
| POST | `/api/v1/ocr/process` | テキスト抽出 開始（**OCRではない**。下記注記参照） |
| GET | `/api/v1/ocr/jobs/{job_id}` | 抽出ジョブ状態（可視文書のみ） |
| GET | `/api/v1/ocr/jobs/{job_id}/result` | 抽出結果（可視文書のみ） |
| POST | `/api/v1/ai/documents/{document_id}/classify` | AI 分類 |
| POST | `/api/v1/ai/documents/{document_id}/extract` | 構造化抽出 |
| GET | `/api/v1/ai/documents/{document_id}/summary` | AI 要約 |
| GET/PUT | `/api/v1/ai-config` | AI 設定取得/更新（管理者） |

> ⚠️ **`/api/v1/ocr/*` は OCR ではありません**（2026-09-18 実装確認）
> pypdf による **PDF テキストレイヤ抽出**のみを提供します。OCR エンジン
> （Tesseract 等）は依存に含まれないため、**画像のみのスキャンPDFは文字認識できません**。
> その場合は `status="unsupported"` と理由を返し、`pages` は空になります
> （以前は「結果に見える」プレースホルダ文字列を返していました）。
> レスポンスの `engine` が実際の処理系（現在は `pypdf-text-layer`）を示します。
> `language` / `enable_vertical` は受け取りますが現行エンジンは使用しません。
> ジョブは DB に保存され、uvicorn の複数ワーカーから参照できます。
> アクセスは文書の可視性（`assert_document_visible`）に従います。
| POST | `/api/v1/ai-config/test` | AI 接続テスト（管理者） |

### 検索 / Editor 連携 / リビジョン / プライバシー / アプリ配布

> 🔒 **AI の停止スイッチ**: AI 分類・抽出・要約とセマンティック検索／サジェストは、管理者が `/api/v1/ai-config` で `enabled=true` にしたときだけ外部 AI を呼ぶ（既定は無効・fail closed）。無効な間、`/ai/*` は **503**（「AI 機能は無効化されています」）を返し、検索は元のクエリだけで動く。API キー（DB に暗号化保存、なければ `ANTHROPIC_API_KEY`）があっても、無効なら呼び出さない。

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/v1/search/documents` | 全文検索（SQLite FTS5 / PG tsvector） |
| POST | `/api/v1/search/documents/reindex` | 再インデックス（admin/manager） |
| GET | `/api/v1/search/documents/suggest` | AI サジェスト |
| POST | `/api/v1/documents/{doc_id}/review-sidecar` | Editor レビュー情報取込 |
| GET | `/api/v1/documents/{doc_id}/review-sidecar` | Editor レビュー情報取得 |
| POST | `/api/v1/documents/{doc_id}/flatten-check` | 平坦化チェック |
| POST | `/api/v1/documents/{doc_id}/editor-events` | Editor イベント記録 |
| GET | `/api/v1/documents/{doc_id}/workflow-status` | Editor 向けワークフロー状態 |
| POST | `/api/v1/documents/{doc_id}/revisions` | リビジョン追加 |
| GET | `/api/v1/documents/{doc_id}/revisions` | リビジョン一覧 |
| DELETE | `/api/v1/privacy/users/{user_id}/data` | GDPR 削除権（論理削除→猶予後物理削除） |
| GET | `/api/v1/privacy/users/{user_id}/export` | GDPR データポータビリティ（Art.20） |
| POST | `/api/v1/privacy/consent` | 同意記録（Art.7・追記型） |
| GET | `/api/v1/privacy/consent/{user_id}` | 同意状況確認 |
| POST | `/api/v1/privacy/admin/run-deletion-job` | 物理削除ジョブ実行（admin） |
| GET | `/api/v1/apps/releases` | 配布リリース一覧 |
| GET | `/api/v1/apps/release-notes` | リリースノート |
| GET | `/api/v1/apps/build-info` | ビルド情報 |
| GET | `/api/v1/apps/download/{package_id}` | ダウンロード URL・SHA-256 |

## 共通仕様

- エラーフォーマット: `{"detail": "..."}`
- 認可失敗は存在秘匿のため 404（RBAC 境界）
- レート制限: `/auth/token`・`/auth/m365/login` は 10 回/60 秒/IP（超過時 429 + `Retry-After`）
- CSV 出力は UTF-8 BOM・スプレッドシート数式インジェクション対策済み
