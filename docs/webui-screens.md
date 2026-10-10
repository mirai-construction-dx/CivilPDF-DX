# CivilPDF-DX WebUI 画面一覧

> 実装コード（`src/console/frontend/src/App.tsx`・`components/enterprise/EnterpriseLayout.tsx`・`pages/`・`components/enterprise/views/`）から 2026-08-12 時点で整理した一覧です。

## ルーティング

| ルート | 画面 | 実装ファイル | 認証 |
|---|---|---|---|
| `/login` | ログイン | `pages/Login.tsx` | 不要 |
| `/*`（ログイン後） | Enterprise シェル（下記ビューを内部切替） | `components/enterprise/EnterpriseLayout.tsx` | 必須 |

Enterprise シェルは URL ベースのルートではなく、内部ステート（`currentView`）でビューを切り替えます。認証ガードは `components/ProtectedRoute.tsx` が担当します。

## シェル内ビュー一覧

| ビュー ID | メニュー名 | 実装ファイル | 状態 |
|---|---|---|---|
| `lp` | 概要 | `components/enterprise/views/LandingView.tsx` | 実装済み |
| `dashboard` | ダッシュボード | `components/enterprise/views/DashboardView.tsx`（サブビュー: overview / stats / dist / users） | 実装済み |
| `documents` | 図書管理 | `pages/Documents.tsx` | 実装済み |
| `projects` | プロジェクト | `pages/Projects.tsx` | 実装済み |
| `upload` | 取込/解析 | `components/enterprise/views/UploadView.tsx` | 実装済み |
| `viewer` | ビューア | `components/enterprise/views/ViewerView.tsx` | 実装済み |
| `workflow` | ワークフロー | `pages/Workflows.tsx` | 実装済み |
| `apps` | アプリ配布 | `components/enterprise/views/AppsView.tsx` | 実装済み |
| `editor` | Editor連携 | `components/enterprise/views/EditorSyncView.tsx` | 実装済み |
| `security` | セキュリティ | `components/enterprise/views/SecurityView.tsx` | 実装済み |
| `audit` | 監査 | `pages/AuditLogs.tsx` | 実装済み |
| `m365` | Microsoft365 | `components/enterprise/views/M365View.tsx` | 実装済み |
| `privacy` | プライバシー | `components/enterprise/views/PrivacyView.tsx` | 実装済み |
| `users` | ユーザー管理 | `pages/Users.tsx` | 実装済み |
| `settings` | システム設定 | `pages/Settings.tsx` | 実装済み |

## 主要画面の概要

### ログイン（`/login`）

- `POST /api/v1/auth/token` で access/refresh token を取得し、`GET /api/v1/auth/me` でユーザー情報を Zustand ストアへ保存します。
- 未認証ユーザーは `ProtectedRoute` により `/login` へリダイレクトされます。

### ダッシュボード（`dashboard`）

- `views/DashboardView.tsx` が実装主体です。期間・フィルタ・サブビューは Enterprise シェルのサイドバーで切替えます。
- バックエンドは `/api/v1/stats/` 等へ接続されています。
- なお `pages/Dashboard.tsx` は現在のシェルから参照されていない未使用ファイルです（削除候補）。

### 図書管理（`documents`）

- `pages/Documents.tsx`。文書一覧・アップロード・削除・ごみ箱/復元・タイムスタンプ関連モーダル・CSV 出力を提供します。
- 利用 API: `GET/POST/DELETE /api/v1/documents/...`、`GET /api/v1/documents/export.csv`。

### プロジェクト（`projects`）

- `pages/Projects.tsx`。プロジェクト一覧・作成・電子納品関連を提供します。
- 利用 API: `GET/POST /api/v1/projects/...`、電子納品チェック/生成。

### 承認ワークフロー（`workflow`）

- `pages/Workflows.tsx`。一覧・詳細・ステップ承認/却下/差戻し・差戻し後の再申請を提供します。
- 利用 API: `GET/POST /api/v1/workflows/...`、`POST /api/v1/workflows/{id}/steps/{sid}/decide`（`approve` / `reject` / `return`）、`POST /api/v1/workflows/{id}/resubmit`。
- 「再申請」は admin、または `GET /api/v1/documents/{id}` で取得した文書の所有者にのみ表示します（バックエンドでも同じ条件で強制）。

### 監査（`audit`）

- `pages/AuditLogs.tsx`。監査ログ一覧・チェーン検証・CSV 出力（管理者限定）を提供します。
- 利用 API: `GET /api/v1/audit-logs/`、`GET /api/v1/audit-logs/verify`、`GET /api/v1/audit-logs/export.csv`。

### ユーザー管理（`users`）

- `pages/Users.tsx`。ユーザー一覧を表示します（admin / manager 以外は画面内でアクセス制御）。
- 利用 API: `GET /api/v1/users/`。

### システム設定（`settings`）

- `pages/Settings.tsx`。AI 設定などシステム設定を提供します。
- 利用 API: `GET/PUT /api/v1/ai-config` 等。

## 未実装・確認済みの差分

- `pages/Dashboard.tsx` はシェルから参照されていない（旧実装の残置）。
- 旧ドキュメントにあった「PDF 監査ビューア `/pdf-audit`」「通知設定 `/notifications`」「AI 管理 `/ai-settings`」は、現行コードにルート/ビューとして存在しません（要件上の将来候補）。
- シェル内ナビゲーションは URL を持たないため、ブラウザの戻る/進むや直リンクは `/login` とルート以外に未対応です（改善候補）。

## 認証・権限の基本方針

- 全シェルビューは認証必須です。
- 画面内の権限制御は主にフロントエンドで実施しています（例: ユーザー管理は admin / manager 以外を拒否）。
- バックエンド側でも RBAC（組織・プロジェクト所属＋ロール）を強制し、未許可は 404 で秘匿します（PR #122 以降）。
