# セットアップガイド

## 開発環境

### 前提条件

| ソフトウェア | バージョン | 用途                      |
| ------------ | ---------- | ------------------------- |
| Node.js      | >= 20.x    | GUIアプリ・フロントエンド |
| Python       | >= 3.11    | バックエンド              |
| PostgreSQL   | >= 15      | メインDB                  |
| Redis        | >= 7       | キャッシュ・キュー        |
| Tesseract    | >= 5.x     | OCR（日本語モデル含む）   |

### Tesseract 日本語モデルのインストール

```bash
# Ubuntu / Debian
sudo apt install tesseract-ocr tesseract-ocr-jpn tesseract-ocr-jpn-vert

# Windows (Chocolatey)
choco install tesseract --params "/Languages:jpn,jpn_vert"
```

### 環境変数

`.env` ファイルをプロジェクトルートに作成（`.env.example` を参照）：

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/civilpdf
REDIS_URL=redis://localhost:6379/0
AZURE_CLIENT_ID=<your-entra-id-client-id>
AZURE_TENANT_ID=<your-entra-id-tenant-id>
ANTHROPIC_API_KEY=<your-claude-api-key>
```

### バックエンドのテスト環境（推奨: 固定バージョンの venv）

システムの Python（`~/.local` など）には、`requirements.txt` と異なるバージョンが入っていることがある。
その状態でテストすると、CI では出ない警告が出たり実行が遅くなったりする
（2026-09-26 実測: fastapi 0.139.2 / httpx 0.27.2 のままだと Starlette の httpx 非推奨警告が出て、`test_apps.py` に約 108 秒かかる。
固定バージョンの venv では警告が消え、約 27 秒で終わる）。CI と同じ条件で確認するため、venv を使う。

```bash
python3 -m venv .venv
.venv/bin/pip install -r src/console/backend/requirements.txt -r src/console/backend/requirements-dev.txt
.venv/bin/python -m pytest -q tests          # backend + integration
.venv/bin/ruff check src/console/backend tests scripts   # CI と同じ ruff 0.8.6
```

- `.venv/` は `.gitignore` 済み
- テスト DB はプロセスごとの一時ファイルなので、複数のテストを同時に実行しても衝突しない

## 本番環境

本番は docker compose スタック（`docker-compose.prod.yml`）で稼働している。手順は次を参照:

- [運用 runbook §2 デプロイ手順](../operations/runbook.md)（反映前に `./scripts/pre-deploy-check.sh` を実行する）
- [Docker 本番デプロイ](../deployment/docker-production-deployment.md)
