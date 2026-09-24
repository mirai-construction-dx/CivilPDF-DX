# CivilPDF-DX Windows 11 移行チェックリスト

> 作成日: 2026-05-19  
> 対象環境: Windows 11 (本番機)  
> 移行元: Linux (Ubuntu)  
> 所要時間目安: 2〜3時間（事前準備完了済みの場合）

---

## 📋 事前確認

移行作業を始める前に、以下が用意されていることを確認してください。

| 確認項目 | 詳細 |
|---|---|
| Windows 11 PC | 管理者権限でログインできること |
| インターネット接続 | ソフトウェアダウンロードのため |
| Git リポジトリへのアクセス | GitHub の認証情報（PAT または SSH キー） |
| Azure AD の情報 | テナントID・クライアントID（M365 連携用） |
| SSL 証明書ファイル | `.crt` と `.key`（HTTPS を使う場合） |

---

## 🔴 STEP 1｜必要ソフトウェアのインストール

> **順番通りに行うこと。特に Python は「Add to PATH」を忘れずにチェックする。**

### 1-1. Python 3.12

1. [https://python.org/downloads/](https://python.org/downloads/) からダウンロード
2. インストーラー起動時 **「Add Python 3.12 to PATH」に必ずチェック**
3. 「Install Now」で実行

```powershell
# インストール確認
python --version
# → Python 3.12.x と表示されればOK
```

### 1-2. Node.js 24 LTS

1. [https://nodejs.org/](https://nodejs.org/) から LTS 版をダウンロード
2. デフォルト設定のままインストール

```powershell
node --version   # → v24.x.x
npm --version    # → 10.x.x
```

### 1-3. Git

1. [https://git-scm.com/download/win](https://git-scm.com/download/win) からダウンロード
2. インストール時「Use Visual Studio Code as Git's default editor」を選択（任意）

```powershell
git --version    # → git version 2.x.x
```

### 1-4. Microsoft Visual C++ Build Tools

> Python の一部パッケージ（bcrypt, cryptography 等）のビルドに必要です。

1. [https://visualstudio.microsoft.com/visual-cpp-build-tools/](https://visualstudio.microsoft.com/visual-cpp-build-tools/) からダウンロード
2. インストーラーで「C++ によるデスクトップ開発」にチェックを入れてインストール

### 1-5. OpenJDK 17（veraPDF 用）

1. [https://adoptium.net/](https://adoptium.net/) から「Temurin 17 LTS」をダウンロード
2. インストール時「Add to PATH」にチェック

```powershell
java --version   # → openjdk 17.x.x と表示されればOK
```

### 1-6. veraPDF（PDF/A バリデーション）

1. [https://verapdf.org/software/](https://verapdf.org/software/) からインストーラーをダウンロード
2. デフォルト（`C:\Program Files\verapdf\`）にインストール

```powershell
# 動作確認
& "C:\Program Files\verapdf\verapdf.bat" --version
```

### 1-7. PostgreSQL 16

1. [https://www.enterprisedb.com/downloads/postgres-postgresql-downloads](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads) からダウンロード
2. インストール時に設定するパスワードを必ず控えること
3. インストール後、pgAdmin または psql でデータベースを作成

```sql
-- psql (管理者) で実行
CREATE DATABASE civilpdf;
CREATE USER civilpdf WITH PASSWORD 'ここに安全なパスワードを設定';
GRANT ALL PRIVILEGES ON DATABASE civilpdf TO civilpdf;
```

### 1-8. NSSM（Windows サービス管理）

1. [https://nssm.cc/download](https://nssm.cc/download) からダウンロード
2. `nssm.exe` を `C:\Windows\System32\` にコピー（または PATH が通ったフォルダに配置）

```powershell
nssm version    # → NSSM 2.24 と表示されればOK
```

### 1-9. nginx for Windows

1. [https://nginx.org/en/download.html](https://nginx.org/en/download.html) から Stable 版をダウンロード
2. `C:\nginx\` に展開

---

## 🔴 STEP 2｜リポジトリのクローン

```powershell
# PowerShell で実行（管理者不要）

# クローン
git clone https://github.com/mirai-construction-dx/CivilPDF-DX.git C:\CivilPDF
cd C:\CivilPDF

# 重要: 改行コードを LF に固定（必ず実行すること）
git config core.autocrlf false
git config core.eol lf
```

> ⚠️ **この設定を忘れると Python スクリプトや設定ファイルの改行コードが壊れる場合があります。**

---

## 🔴 STEP 3｜Python 仮想環境のセットアップ

```powershell
cd C:\CivilPDF

# 仮想環境を作成
python -m venv .venv

# 仮想環境を有効化
.venv\Scripts\Activate.ps1

# 依存パッケージをインストール
pip install -r src\console\backend\requirements.txt
pip install -r src\console\backend\requirements-dev.txt
```

**トラブルシューティング:**

| エラー | 原因 | 対処 |
|---|---|---|
| `error: Microsoft Visual C++ 14.0 is required` | Build Tools 未インストール | STEP 1-4 を実施してから再実行 |
| `pip: command not found` | Python が PATH に入っていない | Python を再インストール（Add to PATH にチェック） |

---

## 🔴 STEP 4｜環境変数ファイル (.env) の作成

```powershell
# .env.example をコピー
Copy-Item C:\CivilPDF\.env.example C:\CivilPDF\.env
```

コピーした `.env` をテキストエディタで開き、以下を編集します。

```env
# データベース（PostgreSQL に変更）
DATABASE_URL=postgresql://civilpdf:ここにパスワード@localhost:5432/civilpdf

# アップロードフォルダ（Windows パス）
UPLOAD_DIR=C:/CivilPDF/uploads

# セキュリティキー（32文字以上のランダム文字列）
SECRET_KEY=ここに安全なランダム文字列を設定

# Microsoft 365 連携
M365_TENANT_ID=Azure AD のテナントID
M365_CLIENT_ID=アプリ登録のクライアントID

# Fernet 暗号化キー（下記コマンドで生成）
M365_FERNET_KEY=

# veraPDF パス
VERAPDF_PATH=C:/Program Files/verapdf/verapdf.bat
```

**Fernet キーの生成方法:**

```powershell
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → 生成された文字列を M365_FERNET_KEY= の後ろにそのままコピー
```

---

## 🔴 STEP 5｜アップロードフォルダの作成

```powershell
# アップロード先フォルダを作成
New-Item -ItemType Directory -Force -Path C:\CivilPDF\uploads
New-Item -ItemType Directory -Force -Path C:\CivilPDF\logs
```

---

## 🔴 STEP 6｜データベースマイグレーション

```powershell
cd C:\CivilPDF\src\console\backend
..\..\..\..\.venv\Scripts\Activate.ps1

# マイグレーション実行
$env:PYTHONPATH = "C:\CivilPDF\src\console\backend"
alembic upgrade head
```

成功すると以下のようなメッセージが表示されます:
```
INFO  [alembic.runtime.migration] Running upgrade  -> xxxxxxxx, ...
```

---

## 🔴 STEP 7｜フロントエンドのビルド

```powershell
cd C:\CivilPDF\src\console\frontend
npm install
npm run build
# → dist\ フォルダに静的ファイルが生成される
```

---

## 🔴 STEP 8｜nginx の設定

```powershell
# 設定ファイルをコピー
Copy-Item C:\CivilPDF\scripts\windows\nginx.conf C:\nginx\conf\nginx.conf
```

`C:\nginx\conf\nginx.conf` をエディタで開き、以下を実環境に合わせて変更:

| 変更箇所 | デフォルト値 | 変更後 |
|---|---|---|
| `server_name` | `civilpdf.local` | 実際のホスト名またはIPアドレス |
| `ssl_certificate` | `C:/nginx/ssl/civilpdf.crt` | 実際の証明書パス |
| `ssl_certificate_key` | `C:/nginx/ssl/civilpdf.key` | 実際の秘密鍵パス |
| `root`（静的ファイル） | `C:/CivilPDF/src/console/frontend/dist` | そのまま（ビルド済みのパス） |

**SSL 証明書の配置:**

```powershell
# SSL フォルダを作成
New-Item -ItemType Directory -Force -Path C:\nginx\ssl

# 証明書ファイルをコピー（ファイル名は実際のものに合わせること）
Copy-Item .\civilpdf.crt C:\nginx\ssl\civilpdf.crt
Copy-Item .\civilpdf.key C:\nginx\ssl\civilpdf.key
```

> HTTPS が不要な場合（LAN 内のみ）は、`nginx.conf` の HTTPS サーバーブロックを削除し、HTTP のみで設定可能です。

---

## 🔴 STEP 9｜Windows サービスの登録

PowerShell を **「管理者として実行」** で開き、以下を実行します。

```powershell
cd C:\CivilPDF\scripts\windows
.\install-services.ps1 -InstallDir C:\CivilPDF
```

実行後、以下が表示されれば成功:

```
✅ CivilPDF-Backend 登録完了
✅ CivilPDF-Frontend 登録完了
✅ Firewall: CivilPDF Backend port 8000
✅ Firewall: CivilPDF Frontend port 5181
✅ インストール完了!
```

**サービスの確認:**

```powershell
Get-Service CivilPDF-Backend, CivilPDF-Frontend
```

| Name | Status | 意味 |
|---|---|---|
| CivilPDF-Backend | Running | ✅ 正常 |
| CivilPDF-Frontend | Running | ✅ 正常 |
| CivilPDF-Backend | Stopped | ❌ ログを確認 |

---

## 🔴 STEP 10｜動作確認

```powershell
# バックエンド ヘルスチェック
Invoke-WebRequest http://localhost:8000/health
# → StatusCode: 200, Content: {"status":"ok"} と表示されればOK

# フロントエンド確認
Start-Process "http://localhost:5181"
# → ブラウザでログイン画面が表示されればOK
```

---

## 🔴 STEP 11｜nginx サービスの登録（本番 HTTPS 用）

```powershell
# PowerShell（管理者）で実行
nssm install nginx C:\nginx\nginx.exe
nssm set nginx AppDirectory C:\nginx
nssm set nginx Start SERVICE_AUTO_START
Start-Service nginx

# 確認
Invoke-WebRequest https://civilpdf.local/health
```

---

## 📋 全 STEP 完了チェックリスト

```
□ STEP 1  Python / Node.js / Git / Build Tools / Java / veraPDF / PostgreSQL / NSSM / nginx インストール済み
□ STEP 2  git clone 完了、core.autocrlf = false 設定済み
□ STEP 3  .venv 作成、pip install 完了（エラーなし）
□ STEP 4  .env ファイル作成・編集済み（DATABASE_URL / SECRET_KEY / M365 / VERAPDF_PATH）
□ STEP 5  C:\CivilPDF\uploads と logs フォルダ作成済み
□ STEP 6  alembic upgrade head 完了（エラーなし）
□ STEP 7  npm run build 完了（dist\ フォルダ生成確認）
□ STEP 8  nginx.conf 編集済み、SSL 証明書配置済み
□ STEP 9  Windows サービス登録済み（CivilPDF-Backend / CivilPDF-Frontend が Running）
□ STEP 10 http://localhost:8000/health → 200 OK 確認
□ STEP 10 http://localhost:5181 → ログイン画面表示確認
□ STEP 11 nginx サービス登録済み（本番 HTTPS 使用の場合）
```

---

## ⚠️ よくあるトラブルと対処法

| 症状 | 原因 | 対処 |
|---|---|---|
| `pip install` でビルドエラー | C++ Build Tools 未インストール | STEP 1-4 を実施後に再実行 |
| `alembic: command not found` | 仮想環境が有効化されていない | `.venv\Scripts\Activate.ps1` を実行してから再試行 |
| ファイルアップロードが失敗する | UPLOAD_DIR のフォルダが存在しない | `New-Item -Path C:\CivilPDF\uploads -ItemType Directory` |
| veraPDF が動作しない | Java 未インストール、または PATH 未設定 | `java --version` で確認。未インストールなら STEP 1-5 を実施 |
| サービスが起動しない | .env が未作成、またはパスが誤り | `C:\CivilPDF\logs\backend-stderr.log` を確認 |
| ポート 8000 が使用中 | IIS や他のサービスが占有 | `netstat -an \| findstr 8000` で確認後、競合サービスを停止 |
| フロントエンドが API に繋がらない | CORS_ORIGINS に新ホスト名が未設定 | `.env` の `CORS_ORIGINS` にアクセス元 URL を追加 |
| git pull 後に文字化け | 改行コードが CRLF になった | `git config core.autocrlf false` → `git checkout .` |

---

## 🔄 Linux から最新コードを取り込む手順（移行後の定期更新）

```powershell
cd C:\CivilPDF

# 最新コードを取得
git fetch origin
git pull origin main

# Python 依存関係を更新
.venv\Scripts\Activate.ps1
pip install -r src\console\backend\requirements.txt

# DB マイグレーション（スキーマ変更がある場合）
cd src\console\backend
$env:PYTHONPATH = "C:\CivilPDF\src\console\backend"
alembic upgrade head
cd C:\CivilPDF

# フロントエンド再ビルド
cd src\console\frontend
npm install
npm run build
cd C:\CivilPDF

# サービス再起動
Restart-Service CivilPDF-Backend
Start-Sleep -Seconds 3
Restart-Service CivilPDF-Frontend
```

---

## 📞 問い合わせ先・参考リンク

| 内容 | URL |
|---|---|
| NSSM 公式 | https://nssm.cc/ |
| veraPDF 公式 | https://verapdf.org/ |
| nginx for Windows | https://nginx.org/en/docs/windows.html |
| OpenJDK (Temurin) | https://adoptium.net/ |
| PostgreSQL for Windows | https://www.enterprisedb.com/ |
| Azure AD アプリ登録 | https://portal.azure.com/ |
| 詳細デプロイ手順 | `docs/windows-deployment.md` |
