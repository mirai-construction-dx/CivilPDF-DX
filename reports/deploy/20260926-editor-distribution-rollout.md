# 🚀 本番反映チェックリスト — PDF Editor 配布（#141〜#144）

> 👤 実施者: 人間（本番デプロイは手動。Claude は手順書の作成と事後検証の補助まで）
> 📅 作成: 2026-09-26 ／ 対象 commit: `main`（#144 マージ後 `b7a555c` 以降）

## 📌 反映される内容

| PR   | 本番での変化                                                                                                                                                                    |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #141 | 配信ページが Windows（.exe / .msi）のみになり、macOS は「後日対応」表示になる                                                                                                   |
| #142 | なし（開発ツールの設定だけ）                                                                                                                                                    |
| #143 | 表示版が v1.12.6 になり、配布元が `editor-v1.12.6` の Release になる                                                                                                            |
| #144 | 配布リンクの日次監視が始まる（systemd monitor は作業ツリーから直接動くため、main を checkout した時点で有効）。LandingView・AppsView の表示が変わる。配布設定トグルが撤去される |

migration、DB、認証への変更はありません。

## ✅ 0. 事前確認

- [ ] 本番の checkout は **`~/Projects/Mirai-Construction-DX/CivilPDF-DX`** であること（旧 `~/Projects/Mirai-DX-Project/...` はもう存在しない）
- [ ] その checkout が **`main` の検証済み commit** になっていること。compose のビルド元はこの作業ツリーなので、feature branch のままビルドするとそのコードが本番に入る
  ```bash
  cd ~/Projects/Mirai-Construction-DX/CivilPDF-DX
  git switch main && git pull --ff-only origin main && git log --oneline -1
  git status --short   # 追跡ファイルに変更がないこと（.env は Git 管理外なので表示されない）
  ```
- [ ] バックアップを取る: `./scripts/backup-production.sh`
- [ ] 配布アセットが公開済みであることを確認する（2026-09-26 時点で PASS 確認済み）:
  ```bash
  APPS_SHA256_WIN_EXE=e9ba1a2625b7c2479cd25993fa510fcd2eb34b81a265bdf0a5cd349b7772e094 \
  APPS_SHA256_WIN_MSI=ed3ef5d76d48be0d696e9642a1ed15f1eeef5c0b432bd438f64cdb7b4795db04 \
  python3 scripts/check-editor-assets.py --verify-sha256 \
    --base-url https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
  ```

## 🔧 1. env の更新（`.env`・Git 管理外）

`.env` の `APPS_RELEASE_BASE_URL=`（現在は空）を次の値にし、SHA-256 の 2 行を追加する:

```dotenv
APPS_RELEASE_BASE_URL=https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
APPS_SHA256_WIN_EXE=e9ba1a2625b7c2479cd25993fa510fcd2eb34b81a265bdf0a5cd349b7772e094
APPS_SHA256_WIN_MSI=ed3ef5d76d48be0d696e9642a1ed15f1eeef5c0b432bd438f64cdb7b4795db04
```

⚠️ env の更新とイメージの再ビルドは**続けて**行う。env だけ新しいタグにすると、旧イメージのファイル名（v1.2.4）で判定されて、日次監視が「リンク異常」を通知する。

補足: `.env` のパーミッションは現在 `700`。secret を含むファイルなので `chmod 600 .env` を推奨。

## 🐳 2. 再ビルドと起動

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # 3 サービスとも healthy
```

## 🔍 3. 事後検証

- [ ] `./scripts/healthcheck-civilpdf.sh` がすべて OK
- [ ] 稼働中のイメージが新しい版になっている:
  ```bash
  docker exec civilpdf-dx-backend-1 python -c "import api.apps as a; print(a._VERSION)"   # 1.12.6
  ```
- [ ] 配布リンク監視を手動で実行し、`ok` が出る:
  ```bash
  ./scripts/editor-asset-watch.sh --force && tail -1 ~/.local/state/civildx-monitor/monitor.log
  ```
- [ ] ブラウザで `/apps` を開き、次を確認する:
  - Windows の 2 形式が「ダウンロード可能」になっている
  - macOS が「後日対応」表示になっている
  - 配布ポリシーが表示されている
  - ダウンロードした `.msi` の SHA-256 が上記と一致する
- [ ] `docker compose -f docker-compose.prod.yml logs --tail 100 backend` にエラーがない

## ↩️ ロールバック

1. `.env` の `APPS_RELEASE_BASE_URL` を空に戻す（「近日公開予定」表示に戻る）
2. コードも戻す場合は、直前の commit（例 `763fb2c`）を checkout して `docker compose -f docker-compose.prod.yml up -d --build`
3. DB の変更はないので、データの復旧は不要

## 🧾 記録

- 実施日時 / 実施者 / 反映 commit:
- 事後検証の結果:
