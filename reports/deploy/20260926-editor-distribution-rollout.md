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
  git status --short
  #   M state.json               → hook の実行ログ。次の行で退避してから pull する
  #   ?? .mvp-data.bak-20260923/  → 無視してよい（Git 管理外）
  #   それ以外の追跡ファイルに変更がある場合は中止して確認する
  git stash push -m "pre-deploy-state" state.json 2>/dev/null || true
  git switch main && git pull --ff-only origin main && git log --oneline -1
  ```
- [ ] バックアップを取る: `./scripts/backup-production.sh`
- [ ] **ロールバック用に、今のイメージへタグを付けておく**（今のイメージは 2026-09-18 ビルドで、コードは `cf84389` 相当）:
  ```bash
  docker tag civilpdf-dx-backend:latest  civilpdf-dx-backend:pre-20260926
  docker tag civilpdf-dx-frontend:latest civilpdf-dx-frontend:pre-20260926
  ```
- [ ] 配布アセットが公開済みであることを確認する（2026-09-26 時点で PASS 確認済み）:
  ```bash
  APPS_SHA256_WIN_EXE=e9ba1a2625b7c2479cd25993fa510fcd2eb34b81a265bdf0a5cd349b7772e094 \
  APPS_SHA256_WIN_MSI=ed3ef5d76d48be0d696e9642a1ed15f1eeef5c0b432bd438f64cdb7b4795db04 \
  python3 scripts/check-editor-assets.py --verify-sha256 \
    --base-url https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
  ```

- [ ] **まとめて確認する**（読み取りのみ）: `./scripts/pre-deploy-check.sh` を実行し、`0 fail` を確認する
  - タグ付け前なら「ロールバック用タグなし」の WARN が出る。上のタグ付けを済ませてから再実行する
  - env の更新後にもう一度実行すると、配布リンクと SHA-256 まで確認できる

## 🔧 1. env の更新（`.env`・Git 管理外）

`.env` の `APPS_RELEASE_BASE_URL=`（現在は空）を次の値にし、SHA-256 の 2 行を追加する:

```dotenv
APPS_RELEASE_BASE_URL=https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6
APPS_SHA256_WIN_EXE=e9ba1a2625b7c2479cd25993fa510fcd2eb34b81a265bdf0a5cd349b7772e094
APPS_SHA256_WIN_MSI=ed3ef5d76d48be0d696e9642a1ed15f1eeef5c0b432bd438f64cdb7b4795db04
```

⚠️ `.env` を編集しただけでは稼働中のコンテナには反映されない（`env_file` はコンテナを作り直したときに読み込まれる）。
env を変えたら、**必ず次の手順 2 の `--build` 付きで作り直す**。`docker compose up -d`（`--build` なし）や `restart` で作り直すと、新しい env と旧イメージ（v1.2.4 のファイル名）が組み合わさり、配信ページが 404 リンクを出して、日次監視も「リンク異常」を通知する。

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
  ./scripts/editor-asset-watch.sh --force && grep editor-assets ~/.local/state/civildx-monitor/monitor.log | tail -1
  ```
- [ ] ブラウザで `/apps` を開き、次を確認する:
  - Windows の 2 形式が「ダウンロード可能」になっている
  - macOS が「後日対応」表示になっている
  - 配布ポリシーが表示されている
  - ダウンロードした `.msi` の SHA-256 が上記と一致する
- [ ] `docker compose -f docker-compose.prod.yml logs --tail 100 backend` にエラーがない

## ↩️ ロールバック

**A. 表示だけを「近日公開予定」に戻す**（コードは新しいまま）

1. `.env` の `APPS_RELEASE_BASE_URL` を空に戻す
2. `docker compose -f docker-compose.prod.yml up -d` でコンテナを作り直す（**これをしないと env の変更は反映されない**）

**B. 反映前のイメージに戻す**（推奨。事前確認で付けたタグを使う）

```bash
docker tag civilpdf-dx-backend:pre-20260926  civilpdf-dx-backend:latest
docker tag civilpdf-dx-frontend:pre-20260926 civilpdf-dx-frontend:latest
# .env の APPS_* を反映前の値（APPS_RELEASE_BASE_URL は空）に戻してから:
docker compose -f docker-compose.prod.yml up -d --no-build
```

- 作業ツリーは main のままにする（systemd の monitor などもこのツリーから動くため、checkout を切り替えない）
- ソースから再ビルドして戻す必要がある場合、反映前の本番に相当する commit は **`cf84389`**。`763fb2c` などには #141 以降の変更が入っているので使わない。その場合は `git worktree` で別ディレクトリに展開してビルドし、作業ツリーは main のまま保つ

DB の変更はないので、どちらの場合もデータの復旧は不要。

## 🧩 任意（反映後）

- インストール済み unit の `Documentation=` はまだ旧 URL（`Kensan196948G/...`）。動作には影響しないが、`./deploy/install-systemd.sh` を実行し直すと揃う（テンプレートは #145 で現行パスに修正済み）

## 🧾 記録

- 実施日時 / 実施者 / 反映 commit:
- 事後検証の結果:
