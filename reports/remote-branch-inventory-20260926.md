# 🧹 リモートブランチ棚卸しレポート（2026-09-26・第 2 弾）

> 📌 提案のみ。削除はユーザー承認後に実施する。基準: `origin/main` = `b7a555c`（#144 マージ後）。

## 📊 サマリー

| 区分                                                             | 件数 | 提案                                                                                                               |
| ---------------------------------------------------------------- | ---: | ------------------------------------------------------------------------------------------------------------------ |
| ✅ PR マージ済み                                                 |   27 | 削除                                                                                                               |
| ✅ PR close（後継 PR がマージ済み）/ PR なし（同内容マージ済み） |    6 | 削除                                                                                                               |
| ✅ ローカル `fix/production-reliability-hardening-20260918`      |    1 | 削除（8 commit すべて #136 の squash 本文に列挙・取り込み済み。branch だけにある行は main 側で後に更新された旧版） |

## ⚠️ PR マージ以外の 6 件（根拠）

| ブランチ                                       | 最終 commit | 根拠                                                                               |
| ---------------------------------------------- | ----------- | ---------------------------------------------------------------------------------- |
| cleanup/remove-dead-views                      | 2026-06-21  | #74 CLOSED → v2 ブランチで再作成しマージ済み（PR コメント）                        |
| docs/win11-precheck-m365-v2                    | 2026-06-06  | PR なし → 同内容は #37（docs/win11-precheck-m365）でマージ済み。文書は main に存在 |
| feat/m365-auth-integration                     | 2026-05-15  | #16 CLOSED → Phase 5.1（#18）に全て取り込み済み（PR コメント）                     |
| feat/upload-clear-demo-initial-files           | 2026-06-21  | #76 CLOSED → fix/upload-empty-initial-files で再作成（PR コメント）                |
| feature/editor-dx-integration                  | 2026-06-21  | #84 CLOSED → リグレッションのため close、後続 PR で再実装（PR コメント）           |
| fix/migration-boolean-and-duplicate-audit-logs | 2026-06-21  | #86 CLOSED → #87（fix/migration-boolean-clean）に差し替え                          |

## ✅ PR マージ済み 27 件

| ブランチ                               | 最終 commit | PR        |
| -------------------------------------- | ----------- | --------- |
| feat/phase2-alembic-docker-enhanced-ui | 2026-05-11  | 5 MERGED  |
| feat/phase-6-projects-settings         | 2026-05-19  | 20 MERGED |
| fix/security-and-conftest-final        | 2026-05-26  | 23 MERGED |
| docs/release-ready-v0.7                | 2026-06-01  | 28 MERGED |
| feature/phase7-semantic-search         | 2026-06-01  | 26 MERGED |
| feature/phase8-p2-multitenancy         | 2026-06-03  | 31 MERGED |
| docs/win11-precheck-m365               | 2026-06-06  | 37 MERGED |
| feat/prod-docker-deploy                | 2026-06-06  | 36 MERGED |
| feat/phase9-quality-improvements       | 2026-06-07  | 40 MERGED |
| feat/phase10-readme-redesign           | 2026-06-14  | 45 MERGED |
| feat/viewer-api-integration            | 2026-06-17  | 46 MERGED |
| feat/security-real-api                 | 2026-06-20  | 58 MERGED |
| fix/preview-port-4173                  | 2026-06-20  | 52 MERGED |
| fix/preview-proxy                      | 2026-06-20  | 54 MERGED |
| fix/ruff-format-apps                   | 2026-06-20  | 53 MERGED |
| fix/skip-auth-flag                     | 2026-06-20  | 55 MERGED |
| chore/improvement-cycle11              | 2026-06-21  | 81 MERGED |
| chore/state-cleanup-warnings-cycle11   | 2026-06-21  | 78 MERGED |
| chore/state-phase-done-cycle11         | 2026-06-21  | 82 MERGED |
| chore/state-verify-cycle11             | 2026-06-21  | 80 MERGED |
| feat/ai-settings-ui                    | 2026-06-21  | 83 MERGED |
| feat/dashboard-real-data               | 2026-06-21  | 72 MERGED |
| feat/m365-real-api                     | 2026-06-21  | 70 MERGED |
| feat/security-real-data                | 2026-06-21  | 71 MERGED |
| feat/v1.1.0-distribution               | 2026-06-21  | 85 MERGED |
| fix/apps-real-release                  | 2026-06-21  | 73 MERGED |
| fix/appsview-v110-cleanup              | 2026-06-22  | 90 MERGED |

## 🔧 削除コマンド（承認後に実行）

```bash
git push origin --delete \
  chore/improvement-cycle11 \
  chore/state-cleanup-warnings-cycle11 \
  chore/state-phase-done-cycle11 \
  chore/state-verify-cycle11 \
  cleanup/remove-dead-views \
  docs/release-ready-v0.7 \
  docs/win11-precheck-m365 \
  docs/win11-precheck-m365-v2 \
  feat/ai-settings-ui \
  feat/dashboard-real-data \
  feat/m365-auth-integration \
  feat/m365-real-api \
  feat/phase-6-projects-settings \
  feat/phase10-readme-redesign \
  feat/phase2-alembic-docker-enhanced-ui \
  feat/phase9-quality-improvements \
  feat/prod-docker-deploy \
  feat/security-real-api \
  feat/security-real-data \
  feat/upload-clear-demo-initial-files \
  feat/v1.1.0-distribution \
  feat/viewer-api-integration \
  feature/editor-dx-integration \
  feature/phase7-semantic-search \
  feature/phase8-p2-multitenancy \
  fix/apps-real-release \
  fix/appsview-v110-cleanup \
  fix/migration-boolean-and-duplicate-audit-logs \
  fix/preview-port-4173 \
  fix/preview-proxy \
  fix/ruff-format-apps \
  fix/security-and-conftest-final \
  fix/skip-auth-flag
git branch -D fix/production-reliability-hardening-20260918
```
