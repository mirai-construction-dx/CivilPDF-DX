# Windows 11 ネイティブ版 展開前事前確認情報シート
## CivilPDF-DX — みらい建設工業

> **目的**: 2週間後（2026-06-20 目安）の Windows 11 ネイティブ版展開に備え、CMDB・cert フォルダ精査済みの実データをまとめた事前情報シート。
>
> **更新日**: 2026-06-06 / **作成**: CTO (Claude) / **精査ソース**: `CMDB/CMDB.csv`, `CMDB/cmdb_alive.csv`, `cert/ADEntraIDCert.txt`, `cert/VMSV3001.txt`, `cert/GMSV0002.txt`
>
> ⚠️ **セキュリティ方針**: パスワード・Client Secret は本書に**記載しません**。
> 実際の認証情報は `cert/` フォルダ（ローカル限定・gitignored）を参照してください。
> Tenant ID / Client ID（非秘匿識別子）は記載します。

---

## 📌 1. 組織・ドメイン基本情報

| 項目 | 値 | 出典 |
|---|---|---|
| 組織名 | みらい建設工業 | CMDB/branch_master.csv |
| Active Directory ドメイン | `mirai.local` | cert/ADEntraIDCert.txt |
| AD ドメインコントローラ | `VMSV3001` | cert/ADEntraIDCert.txt |
| AD 管理者アカウント | `administrator` / `mirai\administrator` | cert/VMSV3001.txt |
| AD 管理者パスワード | ⚠️ `cert/VMSV3001.txt` 参照 | cert/ フォルダ |
| 展開サーバ候補ホスト名 | `GMSV0002` | cert/GMSV0002.txt |
| GMSV0002 管理者アカウント | `mirai\administrator` | cert/GMSV0002.txt |
| GMSV0002 パスワード | ⚠️ `cert/GMSV0002.txt` 参照 | cert/ フォルダ |

---

## 📌 2. ネットワーク情報（CMDB 精査済み）

### 2.1 ネットワークセグメント構成

| セグメント | アドレス範囲 | 用途 | 出典 |
|---|---|---|---|
| 社内 LAN（サブネット A） | `172.23.10.0/24` | 一般クライアント・固定端末 | CMDB.csv |
| 社内 LAN（サブネット B） | `172.23.11.0/24` | テレワーク・Surface 端末 | CMDB.csv |
| VPN / WAN 接続 | `10.212.134.0/24` | リモートワーク・Surface Go3 | CMDB.csv |
| 入札用ネットワーク（別系統） | `192.168.210.x`, `192.168.213.x` | 入札専用端末（CivilPDF-DX 対象外） | CMDB.csv |

> 💡 CivilPDF-DX は `172.23.0.0/16` (LAN) に展開することを推奨。
> テレワーク利用者は VPN 経由（`10.212.134.0/24` → LAN）でアクセスする。

### 2.2 展開サーバ IP 情報（要確認）

| 項目 | 値 | 備考 |
|---|---|---|
| 展開サーバ ホスト名 | `GMSV0002` | cert/GMSV0002.txt で確認済み |
| 展開サーバ IP アドレス | **要確認・要固定化** | 172.23.10.x または 172.23.11.x 推奨 |
| サブネットマスク | `255.255.0.0 (/16)` | 172.23.0.0/16 に準拠 |
| デフォルトゲートウェイ | **要確認** | AD サーバ (VMSV3001) に同一セグメントを指定 |
| プライマリ DNS | `VMSV3001 の IP` | AD DC を DNS として指定（mirai.local 名前解決） |

### 2.3 CMDB 稼働端末サマリ（2026-06-03 時点）

| OS | 総数 | 稼働中 | ICMP 応答 |
|---|---|---|---|
| Windows 11 | 多数 | 複数 | 172.23.x.x / 10.212.x.x 混在 |
| Windows 10 | 多数 | 複数 | 同上 |

> 最新の生存確認は `CMDB/cmdb_alive.csv` / `CMDB/cmdb_reachable.csv` を参照。

### 2.4 プロキシ設定（要確認）

| 項目 | 値 |
|---|---|
| 社内プロキシ | **要確認** （社内 IT 管理者へ確認） |
| 例外 (no_proxy) | `localhost,127.0.0.1,*.mirai.local,172.23.0.0/16` 推奨 |
| HTTPS プロキシ経由の外部アクセス | `login.microsoftonline.com`, `graph.microsoft.com` が通過できること（§3 参照） |

---

## 📌 3. 外部連携情報 — Microsoft 365 / Entra ID

### 3.1 Azure AD アプリ登録情報

| 項目 | 値 | 機密レベル |
|---|---|---|
| **Entra ID Tenant ID** | `a7232f7a-a9e5-4f71-9372-dc8b1c6645ea` | 公開可（GUID のみ） |
| **Entra ID Client ID** | `22e5d6e4-805f-4516-af09-ff09c7c224c4` | 公開可（GUID のみ） |
| **Client Secret** | ⚠️ `cert/ADEntraIDCert.txt` 参照 | **機密 — 絶対に git に含めない** |
| シークレット有効期限 | cert/ADEntraIDCert.txt 発行時より確認 | 180 日以内に更新運用要 |
| 認証フロー | Client Credentials Flow（非対話式） | MS Graph `User.Read.All` 利用 |

> ⚠️ **重要**: Client Secret は `.env` ファイルに**平文で書かない**。
> CivilPDF-DX バックエンドは Fernet 暗号化して DB に保存する設計（管理 API 経由で設定）。

### 3.2 必要な Azure AD アプリ権限

| API | 権限名 | 権限種別 | 管理者同意 | 用途 |
|---|---|---|---|---|
| Microsoft Graph | `User.Read.All` | **Application**（委任ではなく） | ✅ 必須 | メール→ユーザー存在確認・entra_id 取得 |
| Microsoft Graph | `Directory.Read.All` | Application | 任意 | グループ参照する場合のみ（現在不使用） |

> 💡 管理者同意 URL（ブラウザで開きテナント管理者が承認）:
> ```
> https://login.microsoftonline.com/a7232f7a-a9e5-4f71-9372-dc8b1c6645ea/adminconsent?client_id=22e5d6e4-805f-4516-af09-ff09c7c224c4
> ```
> ※ この操作は **Azure AD テナント管理者権限** が必要。

### 3.3 必要なインターネット接続（M365 機能に必要）

| 宛先 FQDN | ポート | プロトコル | 用途 |
|---|---|---|---|
| `login.microsoftonline.com` | `443` | HTTPS | MSAL トークン取得（Client Credentials） |
| `graph.microsoft.com` | `443` | HTTPS | MS Graph ユーザー検索 API (`/v1.0/users/{email}`) |

> これら 2 つは CivilPDF-DX バックエンドが**サーバから直接**接続します。
> プロキシ経由の場合は CONNECT メソッドが通過できること、または HTTPS プロキシバイパスを設定してください。

---

## 📌 4. CivilPDF-DX サービスポート要件

### 4.1 Inbound（展開サーバへの接続）

| ポート | プロトコル | 用途 | 接続元 |
|---|---|---|---|
| `8080` / `443` | TCP | フロントエンド（Nginx / IIS ARR 経由） | 社内 LAN ユーザー |
| `8000` | TCP | FastAPI バックエンド（直接 or Nginx プロキシ経由） | Nginx / ローカル |
| `3389` | TCP | RDP 管理接続（管理者のみ） | 管理者端末 |

> 本番推奨: 外部向け公開は `443`（HTTPS）のみ。`8000` はローカルループバックのみ許可。

### 4.2 Outbound（展開サーバから外部への接続）

| 宛先 | ポート | 用途 |
|---|---|---|
| `login.microsoftonline.com` | `443` | M365 認証（§3.3 参照） |
| `graph.microsoft.com` | `443` | MS Graph API（§3.3 参照） |
| `api.anthropic.com` | `443` | Claude AI 機能（文書分類・要約等、任意） |
| VMSV3001 の IP | `389` / `636` / `88` | AD LDAP / LDAPS / Kerberos（AD 参加時） |
| PostgreSQL サーバ | `5432` | DB 接続（同ホスト localhost 可） |
| `github.com` | `443` | git clone / pull（展開時のみ） |

---

## 📌 5. ログイン認証の実装状況確認

### 5.1 認証方式一覧（実装済み）

| 認証方式 | 実装状況 | 画面 | API エンドポイント |
|---|---|---|---|
| **一般ログイン（メール + パスワード）** | ✅ 実装済み・テスト通過 | ログイン画面「パスワード」タブ | `POST /api/v1/auth/login` |
| **Microsoft 365 非対話式認証** | ✅ 実装済み・テスト通過 | ログイン画面「Microsoft 365」タブ | `POST /api/v1/auth/m365/login` |

### 5.2 一般ログイン（JWT 認証）の仕様

```
利用者操作: メールアドレス + パスワード入力 → ログイン
バックエンド: bcrypt ハッシュ照合 → JWT アクセストークン + リフレッシュトークン発行
RBAC: admin / manager / engineer / viewer（DB 管理）
```

- 初回管理者は `scripts/create_admin.py` で作成（`docs/deployment/docker-production-deployment.md §5` 参照）
- パスワード変更: ログイン後 Settings → セキュリティ

### 5.3 Microsoft 365 非対話式認証の仕様（Client Credentials Flow）

```
利用者操作: メールアドレスのみ入力（パスワード不要）
              ↓
バックエンド: MSAL で Azure AD からアプリトークン取得（Client Credentials）
              ↓
              MS Graph /v1.0/users/{email} でユーザー存在確認
              ↓
              accountEnabled チェック（無効なら 403）
              ↓
              CivilPDF-DX DB のユーザーレコードと照合（entra_id → email の順）
              ↓
              CivilPDF-DX JWT 発行（ロールは DB が真実、M365 グループは使用しない）
```

**自動プロビジョニング**: `auto_provision=true`（管理者が admin UI で設定）の場合、M365 に存在するが DB に未登録のユーザーが初回ログイン時に `viewer` ロールで自動作成される。

**IP 制限**: `.env` の `M365_ALLOWED_NETWORKS` に LAN セグメントを指定できる。
```
M365_ALLOWED_NETWORKS=172.23.0.0/16,10.212.134.0/24
```
未設定の場合は全 IP から M365 ログインが可能（社内展開初期は未設定で OK、本番強化時に設定）。

### 5.4 テストカバレッジ（実装品質確認）

| テストファイル | テスト件数 | 確認内容 |
|---|---|---|
| `tests/console/test_m365_auth.py` | 15 件 | M365 ログイン全シナリオ（無効・未登録・自動プロビジョン・IP 制限・Fernet 暗号化等） |
| `tests/console/test_m365.py` | 14 件 | M365 管理 API（設定保存・接続テスト・Fernet 暗号化） |
| `tests/console/test_auth.py` | 7 件 | 一般ログイン・パスワード変更 |

**全 368 件テスト通過・CI 全ジョブ pass 済み（2026-06-03 CTO Production Ready 宣言）**

---

## 📌 6. 展開後の M365 設定手順（管理者 UI）

展開後、管理者アカウントでログインし、以下の順序で M365 連携を有効化する。

### 手順 1: Azure AD アプリ情報を登録

```
ブラウザで https://<展開サーバ>/ を開く
→ admin@example.com でログイン（scripts/create_admin.py で作成したアカウント）
→ Settings（設定）ページ → Microsoft 365 連携タブ
→ 以下を入力して保存:
    Tenant ID:     a7232f7a-a9e5-4f71-9372-dc8b1c6645ea
    Client ID:     22e5d6e4-805f-4516-af09-ff09c7c224c4
    Client Secret: cert/ADEntraIDCert.txt 記載の値をコピー
```

> ⚠️ Client Secret はこの画面入力時のみ平文で扱い、保存後は Fernet 暗号化されて DB に格納される（画面上では再表示されない）。

### 手順 2: 接続テスト

```
同 Settings ページ → 「接続テスト」ボタンをクリック
→ 200 OK + "M365 connection OK" が返れば設定完了
（内部で MS Graph /v1.0/me を呼び出してトークン有効性を確認）
```

### 手順 3: 自動プロビジョニング設定（任意）

```
「自動プロビジョニング」チェックを有効にする
→ M365 登録済みユーザーが初回ログイン時に viewer ロールで自動作成される
→ 有効にしない場合は、事前に管理者が Users ページで手動登録が必要
```

### 手順 4: IP 制限設定（任意・本番強化時）

バックエンド `.env` に追記して再起動:
```env
M365_ALLOWED_NETWORKS=172.23.0.0/16,10.212.134.0/24
```

---

## 📌 7. git clone 展開手順（Windows 11 ネイティブ）

```powershell
# 管理者 PowerShell で実行
# 前提: Git for Windows / Python 3.12 / Node.js 20 LTS / PostgreSQL 16 インストール済み

# 1. リポジトリ取得
$base = "C:\Apps\CivilPDF-DX"
New-Item -ItemType Directory -Force -Path $base | Out-Null
Set-Location $base
git clone https://github.com/mirai-construction-dx/CivilPDF-DX.git .
git checkout main

# 2. バックエンド依存インストール
Set-Location "$base\src\console\backend"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 3. 環境変数ファイル作成
Copy-Item "$base\.env.prod.example" "$base\.env"
# .env を編集して POSTGRES_PASSWORD / SECRET_KEY / TIMESTAMP_HMAC_KEY を設定

# 4. DB マイグレーション
$env:PYTHONPATH = "$base\src\console\backend"
Set-Location "$base\src\console\backend"
alembic upgrade head

# 5. 初回管理者作成
python "$base\scripts\create_admin.py" `
  --email admin@example.com `
  --username admin `
  --password "<強力なパスワード>"

# 6. フロントエンドビルド
Set-Location "$base\src\console\frontend"
npm ci
npm run build
# → dist/ フォルダに静的ファイル生成（Nginx / IIS で配信）

# 7. バックエンドサービス化（NSSM）
# docs/deployment/windows11-deployment-checklist.md §9 参照
```

---

## 📌 8. 事前確認チェックリスト（展開作業前）

### 8.1 ネットワーク・サーバ確認

- [ ] GMSV0002 の IP アドレスが 172.23.x.x に固定されていること
- [ ] DNS プライマリに VMSV3001 が設定されていること（`mirai.local` 名前解決）
- [ ] `ping login.microsoftonline.com` が成功すること（インターネット疎通）
- [ ] `ping graph.microsoft.com` が成功すること
- [ ] プロキシ経由の場合: CONNECT 443 が `login.microsoftonline.com` / `graph.microsoft.com` に通過すること
- [ ] ファイアウォール: Inbound 8080/443 が社内 LAN から通過すること

### 8.2 Azure AD 確認（展開前に IT 管理者または Microsoft Azure ポータルで確認）

- [ ] アプリ登録 `22e5d6e4-805f-4516-af09-ff09c7c224c4` が存在すること
- [ ] `User.Read.All`（Application 権限）に**管理者同意**が付与されていること
- [ ] Client Secret の有効期限が残っていること（cert/ADEntraIDCert.txt で確認）
- [ ] アプリが「無効化」されていないこと

### 8.3 展開作業確認

- [ ] `git clone` 完了・`git log` で最新コミット確認
- [ ] `.env` ファイルに必須項目記入済み（POSTGRES_PASSWORD / SECRET_KEY / TIMESTAMP_HMAC_KEY）
- [ ] `alembic upgrade head` 完了
- [ ] `scripts/create_admin.py` で初回管理者作成済み
- [ ] フロントエンド `npm run build` 完了
- [ ] バックエンド NSSM サービス起動確認 (`sc query CivilPDF-Backend`)
- [ ] `curl http://localhost:8000/api/v1/health` → `{"status":"ok"}`

### 8.4 M365 ログイン確認

- [ ] Settings ページで Tenant ID / Client ID / Client Secret を入力・保存
- [ ] 「接続テスト」→ 200 OK
- [ ] ブラウザのログイン画面「Microsoft 365」タブ → メールアドレス入力 → JWT 発行確認
- [ ] 一般ログイン（admin メール + パスワード）も動作すること

---

## 📌 9. 機密情報の参照先

| 情報 | 参照先 | 注意 |
|---|---|---|
| AD 管理者パスワード | `cert/VMSV3001.txt` | git 対象外・ローカルのみ |
| GMSV0002 ローカル管理者パスワード | `cert/GMSV0002.txt` | git 対象外・ローカルのみ |
| Entra ID Client Secret | `cert/ADEntraIDCert.txt` | git 対象外・ローカルのみ |
| DB パスワード | `.env` ファイル（展開後に設定） | git 対象外 |
| JWT SECRET_KEY | `.env` ファイル（展開後に設定） | git 対象外 |

> ⚠️ `cert/` フォルダは `.gitignore` で除外済み。絶対にコミットしないこと。
> パスワード受け渡しは暗号化メール・パスワードマネージャ・対面のみとすること。

---

## 📌 10. 参照ドキュメント

| ドキュメント | 内容 |
|---|---|
| [`docs/deployment/windows11-deployment-checklist.md`](./windows11-deployment-checklist.md) | Windows 11 展開チェックリスト詳細テンプレート |
| [`docs/deployment/docker-production-deployment.md`](./docker-production-deployment.md) | Linux Docker 本番デプロイ手順書 |
| [`docs/architecture/m365-auth-design.md`](../architecture/m365-auth-design.md) | M365 非対話式認証 設計書（シーケンス図・脅威モデル） |
| [`docs/windows-deployment.md`](../windows-deployment.md) | Windows ネイティブ展開ガイド（旧版） |
| [`CMDB/CMDB.csv`](../../CMDB/CMDB.csv) | 資産台帳（IP・OS・稼働状態） |
| [`CMDB/cmdb_alive.csv`](../../CMDB/cmdb_alive.csv) | 生存確認結果（2026-06-03 時点） |

---

*このドキュメントは CMDB フォルダ・cert フォルダを精査して自動生成（2026-06-06）。ネットワーク変更時は随時更新のこと。*
