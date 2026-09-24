# CivilPDF-DX Windows 11 デプロイ手順書

## 📌 前提条件

| ソフトウェア | バージョン | 取得先 |
|---|---|---|
| Python | 3.12.x | https://python.org/downloads/ |
| Node.js | 24.x LTS | https://nodejs.org/ |
| Git | 2.x | https://git-scm.com/download/win |
| PostgreSQL | 16.x | https://www.enterprisedb.com/downloads/postgres-postgresql-downloads |
| OpenJDK | 17+ | https://adoptium.net/ (veraPDF 用) |
| NSSM | 2.24+ | https://nssm.cc/download |
| nginx for Windows | 1.25+ | https://nginx.org/en/download.html |
| Microsoft Visual C++ Build Tools | 2022 | https://visualstudio.microsoft.com/visual-cpp-build-tools/ |

> **注意**: Python インストール時に「Add Python to PATH」にチェックを入れること。

---

## 🔧 1. リポジトリのクローン

```powershell
# PowerShell (管理者不要)
git clone https://github.com/mirai-construction-dx/CivilPDF-DX.git C:\CivilPDF
cd C:\CivilPDF

# Git 改行コード設定 (LF 維持)
git config core.autocrlf false
git config core.eol lf
```

---

## 🐍 2. Python 仮想環境セットアップ

```powershell
cd C:\CivilPDF

# 仮想環境作成
python -m venv .venv

# 有効化
.venv\Scripts\Activate.ps1

# 依存関係インストール
pip install -r src\console\backend\requirements.txt
pip install -r src\console\backend\requirements-dev.txt
```

> **トラブルシューティング**: `pip install` でビルドエラーが出た場合、
> 「Microsoft C++ Build Tools」が未インストールの可能性があります。

---

## 🗄️ 3. PostgreSQL セットアップ

```sql
-- PostgreSQL 管理者として実行
CREATE DATABASE civilpdf;
CREATE USER civilpdf WITH PASSWORD 'civildx_secure_password';
GRANT ALL PRIVILEGES ON DATABASE civilpdf TO civilpdf;
```

```powershell
# .env ファイル作成
Copy-Item .env.example .env
# .env を編集して DATABASE_URL を PostgreSQL に変更:
# DATABASE_URL=postgresql://civilpdf:civildx_secure_password@localhost:5432/civilpdf
```

---

## 📁 4. 環境変数 (.env) 設定

`.env` を以下の通り設定します:

```env
DATABASE_URL=postgresql://civilpdf:civildx_secure_password@localhost:5432/civilpdf
SECRET_KEY=<32文字以上のランダム文字列>
UPLOAD_DIR=C:/CivilPDF/uploads
M365_TENANT_ID=<Azure AD テナントID>
M365_CLIENT_ID=<アプリ登録のクライアントID>
M365_FERNET_KEY=<Fernet鍵: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
VERAPDF_PATH=C:/verapdf/verapdf.bat
```

---

## 🗃️ 5. データベースマイグレーション

```powershell
cd C:\CivilPDF\src\console\backend
.venv\Scripts\Activate.ps1

# マイグレーション実行
$env:DATABASE_URL = "postgresql://civilpdf:civildx_secure_password@localhost:5432/civilpdf"
alembic upgrade head
```

---

## ⚛️ 6. フロントエンドビルド

```powershell
cd C:\CivilPDF\src\console\frontend
npm install
npm run build
# → dist/ フォルダに静的ファイルが生成される
```

---

## 🔧 7. Windows サービス登録 (NSSM)

```powershell
# PowerShell を「管理者として実行」
cd C:\CivilPDF\scripts\windows
.\install-services.ps1 -InstallDir C:\CivilPDF

# アンインストール時:
# .\install-services.ps1 -Uninstall
```

---

## 🌐 8. nginx 設定

```powershell
# nginx フォルダを C:\nginx に展開
# 設定ファイルをコピー
Copy-Item C:\CivilPDF\scripts\windows\nginx.conf C:\nginx\conf\nginx.conf

# server_name を実際のホスト名に変更
# SSL 証明書を C:\nginx\ssl\ に配置

# nginx をサービスとして登録
nssm install nginx C:\nginx\nginx.exe
nssm set nginx AppDirectory C:\nginx
nssm set nginx Start SERVICE_AUTO_START
Start-Service nginx
```

---

## 🔒 9. セキュリティ設定

### Windows Firewall
`install-services.ps1` 実行時に自動設定されます。確認:
```powershell
Get-NetFirewallRule -DisplayName "CivilPDF*"
```

### TLS 1.2/1.3 強制 (レジストリ)
```powershell
# TLS 1.0/1.1 無効化 (Windows Server 向け)
# 通常の Windows 11 では設定不要
```

### BitLocker
アップロードディレクトリ `C:\CivilPDF\uploads` が含まれるドライブで
BitLocker を有効化することを推奨します。

---

## ☕ 10. veraPDF (Java) インストール

```powershell
# OpenJDK 17 インストール後
# veraPDF を C:\verapdf\ に展開
# .env に追加:
# VERAPDF_PATH=C:/verapdf/verapdf.bat

# 動作確認
C:\verapdf\verapdf.bat --version
```

---

## ✅ 11. 動作確認チェックリスト

```powershell
# バックエンドヘルスチェック
Invoke-WebRequest http://localhost:8000/health

# フロントエンド
# ブラウザで http://localhost:5181 を開く

# サービス状態
Get-Service CivilPDF-Backend, CivilPDF-Frontend

# ログ確認
Get-Content C:\CivilPDF\logs\backend-stderr.log -Tail 50
```

---

## 🔄 12. Git による更新手順 (2週間後の移行)

```powershell
# Linux から最新をプッシュ後、Windows で:
cd C:\CivilPDF

git fetch origin
git checkout main
git pull origin main

# Python 依存関係更新
.venv\Scripts\Activate.ps1
pip install -r src\console\backend\requirements.txt

# DBマイグレーション
cd src\console\backend
alembic upgrade head

# フロントエンドビルド
cd ..\frontend
npm install
npm run build

# サービス再起動
Restart-Service CivilPDF-Backend
Restart-Service CivilPDF-Frontend
```

---

## ⚠️ よくある問題

| 症状 | 原因 | 対処 |
|---|---|---|
| `pip install` でビルドエラー | Visual C++ Build Tools 未インストール | Build Tools をインストール後、再実行 |
| `verapdf: command not found` | PATH 未設定 | `.env` の `VERAPDF_PATH` を絶対パスで指定 |
| `database.py` で SQLite エラー | `pool_size` 非対応 | database.py の `_build_engine()` を確認 |
| ファイルアップロード失敗 | `UPLOAD_DIR` パス誤り | `.env` の `UPLOAD_DIR` を `C:/CivilPDF/uploads` に設定 |
| NSSM サービスが起動しない | Python/node パス誤り | `nssm edit CivilPDF-Backend` でパスを確認 |
| ポート 8000 が使用中 | IIS や他のサービスが占有 | `netstat -an \| findstr 8000` で確認 |
