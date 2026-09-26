# CivilPDF-DX MVP / Prototype プレビュー環境

**文書番号:** CPDF-DEPLOY-MVP
**対象:** 関係者レビュー・デモ・受入評価（本番運用は対象外）
**最終更新:** 2026-09-18（AUTH_BYPASS 追加・VIEWER 権限化を反映）

## 0. AUTH_BYPASS（未ログイン時の自動閲覧）について

`deploy/civilpdf-mvp-backend.service` / `deploy/civilpdf-mvp-frontend.service` にのみ
`AUTH_BYPASS=true` / `VITE_AUTH_BYPASS=true` を設定できます（本番 `civilpdf-backend/frontend.service`
には設定しないこと。設定されていないことを都度確認）。

- 有効時、**ログイン画面を経由せずアクセスしたユーザーは "MVP Demo Viewer"（`viewer` ロール）として自動的に扱われます**。
  管理者権限は付与されません（`src/console/backend/auth/dependencies.py` `_get_or_create_mvp_viewer_user`）。
- アップロード・承認・削除・ユーザー管理・監査ログ閲覧などの書き込み/管理系 API は
  `require_manager` / `require_admin` により 403 で拒否されます。
- 下記§2のデモアカウントで明示的にログインすれば、従来どおり admin/manager/engineer/viewer
  それぞれのロール別デモを体験できます（バイパスは「未ログイン」の場合のみ適用）。
- 壊れた/不正なトークンを提示した場合は、バイパス有効でも通常どおり 401 になります。

## 1. 公開 URL（本番と完全分離）

| 用途                | URL                                         | 内容                                                       |
| ------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| 本番                | https://civilpdf.mirai-dx-platform.com/     | 実運用（ローカル PostgreSQL 16・本番 Secrets）             |
| **MVP / Prototype** | https://civilpdf-mvp.mirai-dx-platform.com/ | SQLite・架空ダミーデータ・`civilpdf-mvp` Cloudflare Tunnel |

ローカル確認は http://localhost:5183/（`docker compose -f docker-compose.mvp.yml up -d --build`）。

MVP 環境は本番の DB・Secrets・アップロードに一切接続しません。

## 2. デモ用アカウント（すべて架空）

| ロール   | メール                          | 確認できること                                       |
| -------- | ------------------------------- | ---------------------------------------------------- |
| admin    | admin@demo.civilpdf.example     | 全機能・ユーザー管理・監査ログ/CSV・セキュリティ統計 |
| manager  | mgr-east@demo.civilpdf.example  | 承認・プロジェクト・権限棚卸しの承認側               |
| engineer | eng-tokyo@demo.civilpdf.example | アップロード・検索・承認申請                         |
| viewer   | viewer@demo.civilpdf.example    | 閲覧専用（監査ログは 403）                           |

全アカウント共通パスワード: `CivilPDF-Demo-2026!`（デモ専用。本番では使用禁止）。

ドメインは予約済みの `.example`、人物名・組織名・工事名・金額・位置情報はすべて架空です。

## 3. 投入済みダミーデータの構成

`scripts/seed_demo_data.py`（冪等・再実行可）が以下を投入します。

- 組織階層: 本社 → 支店（東日本/西日本）→ 現場事務所（東京/大阪/福岡）6 件
- ユーザー: 4 ロール 10 名（inactive 1 名含む）
- プロジェクト: 5 件（工事番号 `DEMO-PROJ-001`〜`005`、完了 1 件）
- 文書: 21 件（図面/検査/安全/契約/報告/写真/是正・承認済/レビュー待ち/下書き/アーカイブ/ごみ箱 1 件）
- PDF 実ファイル: 全件を `UPLOAD_DIR/demo/` に生成（本文にデモ表記）
- 承認ワークフロー: 5 件（pending / in_progress / approved / rejected / 3 段階）
- 通知: 未読 6 件（承認依頼・管理者向け）
- 監査ログ: ハッシュチェーン有効（`/api/v1/audit-logs/verify` で検証可）
- DX 同期メトリクス: 6 件（成功/413/auth エラー）、同意記録 4 件、M365/AI 設定（未連携状態を明示）

シード後も削除せず保持します。`--reset` を付けるとデモ行と PDF を削除してから再投入します。

## 4. 起動手順（ローカル）

```bash
# 推奨: Docker（SQLite + seed 自動投入・5183 で公開）
docker compose -f docker-compose.mvp.yml up -d --build

# または直接実行
python -m venv .venv-mvp && .venv-mvp/bin/pip install -r src/console/backend/requirements.txt
DATABASE_URL=sqlite:///./.mvp-data/civilpdf-mvp.db \
UPLOAD_DIR=./.mvp-data/uploads \
PYTHONPATH=src/console/backend \
.venv-mvp/bin/python scripts/seed_demo_data.py
# backend: uvicorn main:app --port 8181 / frontend: npm run build && npm run preview -- --port 5183
```

MVP 用の secret は `docker-compose.mvp.yml` に明示したダミー値のみを使います
（`mvp-demo-...`）。本番の `~/.config/civilpdf/civilpdf.env` を流用しないでください。

## 5. 検証

```bash
BASE_URL=https://civilpdf-mvp.mirai-dx-platform.com python scripts/mvp-smoke.py
# 期待: [PASS] 16 項目・0 failure（2026-09-26 に「アプリ配布は Windows のみ」を追加）
```

スモークは認証 → 統計 → 一覧/検索 → ワークフロー → 通知 → 監査チェーン →
CSV 出力 → 権限棚卸し → DX 同期 → アプリ配布（Windows のみ・macOS は後日対応）→ RBAC 拒否を実 HTTP で確認します。

## 6. Cloudflare Tunnel（MVP 用サブドメイン）の構成

- トンネル名: `civilpdf-mvp`（本番 `civilpdf` とは別）
- DNS: `civilpdf-mvp.mirai-dx-platform.com` → `<tunnel-id>.cfargotunnel.com`（proxied）
- 設定例: `deploy/civilpdf-mvp-cloudflared-config.yml.example`
- systemd (user): `deploy/civilpdf-mvp-cloudflared.service`（ingress → `http://localhost:5183`）

新規作成時は `cloudflared tunnel create civilpdf-mvp` で生成される
`~/.cloudflared/<tunnel-id>.json` を 0600 のまま使用し、リポジトリへ含めないこと。

## 7. 既知の制約（MVP スコープ）

- データは SQLite（本番は**ローカル PostgreSQL 16**）。検索は FTS5 で動作します。
- OIDC SSO は IdP 未接続のためボタンは 503 になります（`docs/deployment/oidc-sso-setup.md`）。
- AI 分類/要約は API キー未設定のため 503（設定画面から有効化可能）。
- レート制限はプロセス内メモリ（単一ワーカー前提）。水平スケール時は Redis へ移行。
- 2026-09-18 時点: `https://civilpdf-mvp.mirai-dx-platform.com/` は外形監視で 502
  （到達不可）を確認。本番 `civilpdf.mirai-dx-platform.com` は影響なし（200）。
  MVP 側の cloudflared/systemd 状態を運用担当が確認するまで、外部共有を控えること。
