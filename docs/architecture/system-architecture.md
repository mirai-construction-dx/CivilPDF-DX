# CivilPDF-DX システム構成図

建設・土木業特化 PDF プラットフォームの全体アーキテクチャ定義書。

---

## 1. システム全体構成図

```mermaid
flowchart TB
    subgraph clients["クライアント層"]
        GUI["GUIアプリ\n(Windows .exe)\nElectron / C++"]
        WEB["管理コンソール\n(WebUI)\nReact 19 + Vite"]
    end

    subgraph backend["バックエンド層"]
        API["Backend API\nFastAPI (Python 3.12)\n/api/v1/*"]
        WORKER["非同期ワーカー\n(将来: Celery / ARQ)\nOCR・AI処理キュー"]
    end

    subgraph data["データ層"]
        PG[("PostgreSQL 15\nメインDB")]
        REDIS[("Redis\nセッション・キャッシュ\n(将来実装)")]
        FS["ファイルストレージ\nローカル / S3互換\n/uploads/*"]
    end

    subgraph external["外部サービス"]
        CLAUDE["Claude API\nAI検索・要約・OCR補正"]
        ENTRA["Entra ID (AAD)\nOIDC / M365 SSO\n(実装済み)"]
        HENNGE["HENNGE ONE\nSAML / OIDC\n(将来実装)"]
    end

    GUI -->|"REST / HTTPS"| API
    WEB -->|"REST / HTTPS\naxios + React Query"| API

    API -->|"SQLAlchemy ORM"| PG
    API -->|"aiofiles"| FS
    API -->|"aioredis (将来)"| REDIS
    API -->|"非同期キュー"| WORKER

    WORKER -->|"Anthropic SDK"| CLAUDE
    WORKER --> FS

    API -->|"OAuth2 OIDC (将来)"| ENTRA
    API -->|"SAML 2.0 (将来)"| HENNGE
```

---

## 2. コンポーネント詳細

### 2.1 GUIアプリ（Windowsデスクトップ）

| 項目       | 内容                                                               |
| ---------- | ------------------------------------------------------------------ |
| 形態       | Windows 実行ファイル (.exe)                                        |
| 責務       | PDF 閲覧・注釈・OCR・図面比較・電子印鑑・電子納品チェック・AI検索  |
| オフライン | ローカルキャッシュによるオフライン動作対応（同期パネルで競合解決） |
| 通信       | Backend API へ REST/HTTPS で接続                                   |
| 認証       | JWT Bearer トークン＋Entra ID（M365 ログイン `/auth/m365/login`・OIDC）|
| 実装状況   | 計画中（MVP フェーズ外）                                           |

### 2.2 管理コンソール（WebUI）

| 項目              | 内容                                                       |
| ----------------- | ---------------------------------------------------------- |
| フレームワーク    | React 19 + Vite + TypeScript                               |
| 状態管理          | Zustand (認証状態) + TanStack Query v5 (サーバー状態)      |
| HTTP クライアント | axios（`/src/console/frontend/src/api/client.ts`）         |
| スタイリング      | Tailwind CSS v3                                            |
| ルーティング      | React Router v6                                            |
| 責務              | ユーザー・プロジェクト・ドキュメント・承認ワークフロー管理 |
| 実装状況          | MVP 完成済み（6 画面）                                     |

### 2.3 Backend API

| 項目           | 内容                                                                                    |
| -------------- | --------------------------------------------------------------------------------------- |
| フレームワーク | FastAPI (Python 3.12)                                                                   |
| ORM            | SQLAlchemy 2.x（同期モード）                                                            |
| バリデーション | Pydantic v2                                                                             |
| 認証           | JWT (HS256) — `PyJWT` + `passlib[bcrypt]`（2026-08 `python-jose` から移行、Issue #106） |
| ファイル処理   | `aiofiles` による非同期 PDF 保存（`api/documents.py`）                                  |
| API バージョン | `/api/v1/` プレフィックス                                                               |
| CORS           | `fastapi.middleware.cors.CORSMiddleware`                                                |
| ドキュメント   | Swagger UI (`/docs`)、ReDoc (`/redoc`)                                                  |
| ヘルスチェック | `GET /health`                                                                           |
| 実装状況       | 本番稼働中（2026-08-06〜）。19 ルーター構成                                             |

**実装済みルーター（2026-09-18 時点、`main.py` の `include_router` 実測。旧版は5件のみ記載しており実態と乖離していたため全件へ更新）:**

| プレフィックス          | ルーターファイル                                        | 主要領域                               |
| ----------------------- | ------------------------------------------------------- | -------------------------------------- |
| `/api/v1/auth`          | `api/auth.py`                                           | ログイン・トークン更新・プロフィール   |
| `/api/v1/users`         | `api/users.py`                                          | ユーザー管理（管理者限定）             |
| `/api/v1/projects`      | `api/projects.py`, `api/electronic_delivery.py`         | プロジェクト管理・電子納品             |
| `/api/v1/documents`     | `api/documents.py`, `api/editor.py`, `api/revisions.py` | 文書CRUD・CSV出力・Editor連携・版管理  |
| `/api/v1/workflows`     | `api/workflows.py`                                      | 承認ワークフロー                       |
| `/api/v1/organizations` | `api/organizations.py`                                  | 組織階層                               |
| `/api/v1/audit-logs`    | `api/audit_logs.py`                                     | 監査ログ・CSV出力・改ざん検知検証      |
| `/api/v1/stats`         | `api/stats.py`                                          | ダッシュボード統計・DX同期メトリクス   |
| `/api/v1/m365`          | `api/m365.py`                                           | Microsoft 365 連携                     |
| `/api/v1/ocr`           | `api/ocr.py`                                            | OCR                                    |
| `/api/v1/privacy`       | `api/privacy.py`                                        | GDPR削除権・保持ポリシー               |
| `/api/v1/ai`            | `api/ai.py`                                             | AI分類・構造化抽出・要約（Claude API） |
| `/api/v1/ai-config`     | `api/ai_settings.py`                                    | AI利用設定                             |
| `/api/v1/search`        | `api/search.py`                                         | 全文検索                               |
| `/api/v1/notifications` | `api/notifications.py`                                  | 通知                                   |
| `/api/v1/apps`          | `api/apps.py`                                           | PDF Editor Client 配信                 |

`api/csv_export.py` はルーターではなく共有ヘルパー（CSVストリーミング生成・数式インジェクション対策）で、
`documents.py`/`audit_logs.py` から呼び出される。単独では `include_router` されない設計で正しい。

### 2.4 PostgreSQL

| 項目             | 内容                                                                                                                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| バージョン       | **ローカル PostgreSQL 16**（現行は compose スタックの db コンテナ・named volume。2026-09-18 に Neon を廃止しローカルへ完全移行。開発/テストは SQLite）                                                              |
| 主要テーブル     | `users`, `organizations`, `projects`, `documents`, `document_versions`, `approval_workflows`, `approval_steps`, `audit_logs`, `notifications`, `dx_sync_metrics` 等                 |
| マイグレーション | Alembic（本番・開発共通）/ テストのみ `Base.metadata.create_all`                                                                                                                    |
| 接続             | SQLAlchemy 接続プール（`SessionLocal`）                                                                                                                                             |
| インデックス     | `documents(project_id/owner_id/status)` 追加（migration `l2m3n4o5p6q7`, 2026-09-18）。`audit_logs.sequence_number` を UNIQUE 化し改ざん検知の前提を保証（migration `m3n4o5p6q7r8`） |

### 2.5 ファイルストレージ

| 項目 | 内容                                                                      |
| ---- | ------------------------------------------------------------------------- |
| MVP  | ローカルファイルシステム（`settings.upload_dir`、デフォルト `./uploads`） |
| 将来 | S3 互換オブジェクトストレージ（MinIO / AWS S3 / Azure Blob）              |
| 構造 | `uploads/{project_id}/{uuid}.pdf`                                         |
| 制限 | PDF のみ (`application/pdf`)、最大サイズ `settings.max_file_size_mb` MB   |

### 2.6 AI / Claude API（実装済み）

| 項目       | 内容                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------- |
| 用途       | 文書の分類・構造化抽出・要約（`/api/v1/ai/*`）、セマンティック検索のクエリ拡張                |
| 呼び出し   | API リクエスト内で同期的に呼ぶ（非同期ワーカーは未導入）                                      |
| 停止スイッチ | 管理者が `/api/v1/ai-config` で有効化したときだけ呼ぶ（既定は無効・fail closed）             |
| キー       | DB に Fernet 暗号化で保存（`/api/v1/ai-config`）。なければ環境変数 `ANTHROPIC_API_KEY`        |
| SDK        | Anthropic Python SDK                                                                          |

---

## 3. 認証フロー

### 3.1 現在の JWT 認証（MVP 実装済み）

```mermaid
sequenceDiagram
    actor User
    participant WebUI as 管理コンソール<br/>(React)
    participant API as Backend API<br/>(FastAPI)
    participant DB as PostgreSQL

    User->>WebUI: メール + パスワード入力
    WebUI->>API: POST /api/v1/auth/token<br/>Content-Type: application/x-www-form-urlencoded<br/>username=email&password=***
    API->>DB: SELECT users WHERE email=? AND status='active'
    DB-->>API: User レコード
    API->>API: bcrypt.verify(password, hashed_password)
    API->>DB: UPDATE users SET last_login=NOW()
    API-->>WebUI: {access_token, refresh_token, token_type:"bearer"}
    WebUI->>WebUI: localStorage に access_token / refresh_token 保存
    WebUI->>API: GET /api/v1/auth/me<br/>Authorization: Bearer {access_token}
    API->>API: JWT 検証 (HS256, SECRET_KEY)
    API-->>WebUI: UserResponse (id, email, role, ...)
    WebUI->>WebUI: Zustand store に user 保存 → /dashboard へ遷移

    Note over WebUI,API: 以降の全リクエスト
    WebUI->>API: Authorization: Bearer {access_token}
    API->>API: get_current_user() 依存注入
    API-->>WebUI: レスポンス

    Note over WebUI,API: トークン期限切れ時
    WebUI->>API: POST /api/v1/auth/refresh<br/>{refresh_token}
    API->>API: JWT 検証 (type="refresh")
    API-->>WebUI: 新しい {access_token, refresh_token}
```

### 3.2 Entra ID OIDC 認証（実装済み・下図は想定フロー）

```mermaid
sequenceDiagram
    actor User
    participant GUI as GUIアプリ / WebUI
    participant API as Backend API
    participant Entra as Entra ID (AAD)

    User->>GUI: ログインボタン
    GUI->>Entra: 認可リクエスト (PKCE)<br/>response_type=code<br/>scope=openid profile email
    Entra->>User: Microsoft ログイン画面
    User->>Entra: 認証情報入力
    Entra-->>GUI: 認可コード (code)
    GUI->>Entra: POST /token<br/>code + code_verifier
    Entra-->>GUI: id_token + access_token
    GUI->>API: POST /api/v1/auth/oidc<br/>Bearer {id_token}
    API->>Entra: JWKS エンドポイントで検証
    API->>API: ユーザー DB 照合 / 初回プロビジョニング
    API-->>GUI: CivilPDF JWT (access_token + refresh_token)
```

---

## 4. データフロー

### 4.1 PDF アップロード → OCR → AI 分析 → 承認フロー

```mermaid
flowchart TD
    A["ユーザー\nPDF ファイル選択"] --> B["WebUI / GUIアプリ\nPOST /api/v1/documents\nmultipart/form-data"]
    B --> C{"Backend API\nバリデーション"}
    C -->|"MIME ≠ PDF\nまたはサイズ超過"| ERR["400 / 413 エラー返却"]
    C -->|"OK"| D["aiofiles\nローカルストレージへ保存\nuploads/{project_id}/{uuid}.pdf"]
    D --> E["PostgreSQL\ndocuments テーブルへ INSERT\nstatus=draft"]
    E --> F["DocumentResponse 返却\n201 Created"]

    F --> G{"OCR キュー\n(将来実装)"}
    G --> H["OCR エンジン\n(Tesseract / クラウド OCR)"]
    H --> I["Claude API\nOCR テキスト補正・構造化"]
    I --> J["PostgreSQL UPDATE\nocr_text / ocr_processed=true"]

    J --> K["AI 分析キュー\n(将来実装)"]
    K --> L["Claude API\n図面分類・検索インデックス生成\n電子納品チェック"]
    L --> M["PostgreSQL UPDATE\nextra_data (AI メタデータ)"]

    M --> N["ユーザー\n承認フロー開始\nPOST /api/v1/workflows"]
    N --> O["PostgreSQL\napproval_workflows + approval_steps INSERT\nstatus=in_progress"]
    O --> P["承認者\nPOST /workflows/{id}/steps/{sid}/decide\ndecision=approve/reject"]
    P --> Q{"全ステップ承認?"}
    Q -->|"Yes"| R["PostgreSQL UPDATE\nworkflow.status=approved\ndocument.status=approved"]
    Q -->|"No / reject"| S["PostgreSQL UPDATE\nworkflow.status=rejected\ndocument.status=rejected"]
```

---

## 5. ネットワーク構成

### 5.1 対応デプロイ方式

```
オンプレミス構成（建設会社の社内サーバー）
┌─────────────────────────────────────────┐
│  社内 LAN / イントラネット                  │
│  ┌──────────┐  ┌──────────┐              │
│  │ WebUI    │  │ GUIアプリ │  ←  工事現場PC   │
│  │ (nginx)  │  │ (Windows) │              │
│  └─────┬────┘  └─────┬────┘              │
│        └──────┬───────┘                  │
│        ┌──────▼──────┐                   │
│        │  Backend API │                   │
│        │  (FastAPI)   │                   │
│        └──────┬───────┘                   │
│  ┌────────────┴──────────┐               │
│  │  PostgreSQL │  Files   │               │
│  └─────────────────────-─┘               │
└─────────────────────────────────────────┘
           ↑ HTTPS (自己署名 or 社内 CA)
    外部: Claude API / Entra ID のみ HTTPS 接続
```

### 5.2 ハイブリッド構成（クラウド連携）

| コンポーネント     | オンプレ                | クラウド                      |
| ------------------ | ----------------------- | ----------------------------- |
| GUIアプリ          | Windows クライアント PC | —                             |
| Backend API        | 社内サーバー / Docker   | Azure App Service             |
| PostgreSQL         | 社内 DB サーバー        | Azure Database for PostgreSQL |
| ファイルストレージ | NAS / 社内ディスク      | Azure Blob / AWS S3           |
| 認証               | JWT                     | Entra ID OIDC                 |
| AI API             | —                       | Claude API (HTTPS)            |

### 5.3 通信セキュリティ

| 経路             | プロトコル              | 備考                         |
| ---------------- | ----------------------- | ---------------------------- |
| WebUI → API      | HTTPS (TLS 1.2+)        | CORS ホワイトリスト制限      |
| GUIアプリ → API  | HTTPS (TLS 1.2+)        | 証明書ピニング（将来）       |
| API → PostgreSQL | TCP（社内ネットワーク） | 接続プール・暗号化オプション |
| API → Claude API | HTTPS                   | API キー認証                 |
| API → Entra ID   | HTTPS                   | JWKS 検証                    |

---

## 6. デプロイ構成

### 6.1 Docker Compose（開発・MVP）

```yaml
# docker-compose.yml 構成イメージ
services:
  db:
    image: postgres:15-alpine
    volumes: [postgres_data:/var/lib/postgresql/data]
    environment: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]

  backend:
    build: ./src/console/backend
    depends_on: [db]
    environment:
      - DATABASE_URL=postgresql://...
      - SECRET_KEY=...
      - UPLOAD_DIR=/app/uploads
    volumes: [uploads:/app/uploads]
    ports: ["8000:8000"]

  frontend:
    build: ./src/console/frontend
    ports: ["3000:80"] # nginx で配信

  nginx:
    image: nginx:alpine
    ports: ["443:443", "80:80"]
    volumes: [./nginx.conf, ./certs]
```

### 6.2 Kubernetes（本番・将来）

```
Namespace: civilpdf-dx
├── Deployment: backend (FastAPI)  — replicas: 2+
├── Deployment: frontend (nginx)   — replicas: 2+
├── StatefulSet: postgresql         — PersistentVolumeClaim
├── Deployment: worker (Celery)    — OCR/AI 非同期処理
├── Service: backend-svc (ClusterIP)
├── Service: frontend-svc (ClusterIP)
├── Ingress: nginx-ingress (TLS 終端)
├── ConfigMap: app-config
├── Secret: db-secret, jwt-secret, claude-api-key
└── PersistentVolumeClaim: uploads-pvc
```

### 6.3 環境変数（必須設定）

| 変数名                        | 用途                             | 例                                        |
| ----------------------------- | -------------------------------- | ----------------------------------------- |
| `DATABASE_URL`                | PostgreSQL 接続文字列            | `postgresql://user:pass@db:5432/civilpdf` |
| `SECRET_KEY`                  | JWT 署名鍵                       | 32 バイト以上のランダム文字列             |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT 有効期限                     | `30`                                      |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | リフレッシュトークン有効期限     | `7`                                       |
| `UPLOAD_DIR`                  | PDF 保存ディレクトリ             | `/app/uploads`                            |
| `MAX_FILE_SIZE_MB`            | PDF 最大サイズ                   | `100`                                     |
| `CORS_ORIGINS`                | CORS 許可オリジン                | `https://console.example.com`             |
| `ANTHROPIC_API_KEY`           | Claude API キー（任意・DB 設定がない場合に使用） | `sk-ant-...`                   |
| `AZURE_CLIENT_ID`             | Entra ID クライアント ID（将来） | `xxxxxxxx-...`                            |
