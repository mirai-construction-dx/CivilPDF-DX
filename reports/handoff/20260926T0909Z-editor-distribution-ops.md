# CivilPDF-DX — PDF Editor 配布の Windows 化・配布元移行・運用安全化（2026-09-26）

## 📊 Rubric（完了条件の自己採点）

| 項目                                       | 判定 | 根拠                                                                      |
| ------------------------------------------ | ---- | ------------------------------------------------------------------------- |
| Editor 配布を Windows のみ・macOS 後日対応 | ✅   | #141・#143 マージ済み。macOS は Issue #147 で追跡                         |
| 配布元を正本（public の本リポジトリ）へ    | ✅   | Release `editor-v1.12.6` 公開済み。minisign 署名と SHA-256 を検証         |
| テスト・CI                                 | ✅   | backend+integration 508 passed / 4 skipped、vitest 284、各 PR で CI 13/13 |
| 独立レビュー                               | ✅   | 各 PR で Critical/High の未対応 0 件                                      |
| 本番反映                                   | ⚠️   | 人間作業として未実施。チェックリストと反映前チェックを用意済み            |
| リリースタグ                               | ⚠️   | 計画案のみ（`reports/release/20260926-release-plan.md`）。承認待ち        |

## ✅ マージした PR

| PR   | 内容                                                                                                                       |
| ---- | -------------------------------------------------------------------------------------------------------------------------- |
| #141 | Editor の配布を Windows のみに、`pending_platforms` を追加、配信文書と実装の契約テスト                                     |
| #142 | Claude Code の hook をプロジェクトのルートで実行する                                                                       |
| #143 | v1.12.6 へ更新、配布元を本リポジトリの Release へ、`check-editor-assets.py`                                                |
| #144 | 配布リンクの日次監視、テスト DB のプロセスごとの分離、作り話の数値の撤去、vitest 4.1.11、配布設定トグルの撤去（案 A）      |
| #145 | unit テンプレートと runbook を本番 checkout の新しいパスに修正、ビューアに「デモ」表示、反映チェックリスト、ブランチ棚卸し |
| #146 | CI の ruff の検査対象に `tests/` と `scripts/` を追加                                                                      |
| #148 | 反映前の読み取り専用チェック `pre-deploy-check.sh`、MVP バックアップの gitignore                                           |

このほか、Issue #62・#94 を close、#147 を起票、リモートブランチ 33 件とローカルブランチを整理（残りは main だけ）

## 🔍 重要な発見

- 📁 本番 checkout は `~/Projects/Mirai-Construction-DX/CivilPDF-DX`（旧 `Mirai-DX-Project` のパスは消滅）。**systemd の monitor・MVP、本番 compose のビルドはこの作業ツリーから動く** → 作業中も main を checkout したままにし、変更は `git worktree` で行う
- 🔐 本番 `.env` はこの checkout にある（Git 管理外・600）
- 🧪 以前ローカルのテストが遅かったり失敗したりしたのは、共有の SQLite DB を複数のテストが取り合っていたため → #144 で分離した
- 🐍 ローカル Python のバージョンずれ（fastapi / httpx）が警告と遅さの原因 → 固定バージョンの venv の手順を setup ガイドに書いた

## ⏭️ 再開ポイント

1. 本番反映（人間）: `reports/deploy/20260926-editor-distribution-rollout.md`（タグ付け → `pre-deploy-check.sh` → `.env` → `--build`）
2. MVP 環境の再起動（#141 以降を反映するため。承認待ち）→ `scripts/mvp-smoke.py` で `apps distribution (windows only)` が PASS になることを確認
3. リリース方針の決定（`reports/release/20260926-release-plan.md`・推奨は案 A）
4. 整形だけの PR（frontend の prettier・tests/scripts の ruff format）は別に出す
