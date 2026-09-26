# AGENTS.md — CivilPDF-DX

AI エージェント（Claude Code / Codex / OpenCode など）向けの、このリポジトリ専用の短い入口。
全体の運用方針は `CLAUDE.md` と中央 GitHub Policy（`GITHUB_POLICY.md`）に従う。

## 構成

| パス | 内容 |
| --- | --- |
| `src/console/backend/` | FastAPI（Python 3.12）・SQLAlchemy 2・Alembic |
| `src/console/frontend/` | React 19 + Vite + TypeScript（vitest / Playwright） |
| `tests/console/`, `tests/integration/` | backend のテスト（pytest） |
| `scripts/` | 運用スクリプト（監視・バックアップ・反映前チェック） |
| `deploy/` | systemd unit テンプレート |
| `docs/` | 設計・運用文書（`docs/operations/runbook.md` が運用の正本） |

## 検証コマンド（CI とほぼ同じ範囲）

```bash
# backend（固定バージョンの venv 推奨: docs/guides/setup.md）
ruff check src/console/backend/ tests/ scripts/
ruff format --check src/console/backend/ tests/ scripts/
python -m pytest -q tests   # CI は tests/console を --cov-fail-under=80 付きで、tests/integration を別に実行
# frontend
cd src/console/frontend && npm ci && npm run lint && npm run format:check && npm test && npm run build
```

## 守ること

- 🚫 `main` への直接 push・force push・履歴の書き換えは禁止。変更はブランチ → PR → 必須 CI → squash merge
- 🔐 `.env` や資格情報・会社データをコミットしない。本番の `.env` の値を表示しない
- 🖥️ **本番の checkout（`~/Projects/Mirai-Construction-DX/CivilPDF-DX`）は main のまま保つ**。systemd の監視・MVP・本番 compose のビルドがこの作業ツリーから動くため、作業は `git worktree` で行う
- 🚀 本番デプロイは人間が行う（`reports/deploy/` のチェックリストと `scripts/pre-deploy-check.sh`）
- 📄 `docs/deployment/app-distribution.md` は契約テストで API と照合される。配布パッケージを変えたら文書も更新する
- 🤖 AI 呼び出しは `services/ai_settings` の停止スイッチ・キー・モデル設定を必ず通す（#151 で全経路を統一）
- 📚 ポートフォリオ設計文書（V3.x）の正本はこのリポジトリの外にある。複製してコミットしない
