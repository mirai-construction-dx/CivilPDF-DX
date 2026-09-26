# 🧹 ブランチ棚卸しレポート（2026-09-26）

> 📌 提案のみ。**削除は実施していません**（削除する場合はユーザー承認後に実施）。
> 基準: `origin/main` = `763fb2c`〜以降（#142 マージ後）。中央 GitHub Policy の「merge 後 branch 削除」に照らして整理した。

## 📊 サマリー

| 区分                               | 件数 | 提案                                                     |
| ---------------------------------- | ---: | -------------------------------------------------------- |
| ✅ PR マージ済み・リモートにも残存 |   14 | ローカルとリモートの両方を削除してよい                   |
| ✅ PR マージ済み・リモートなし     |    1 | ローカルを削除してよい                                   |
| ⚠️ PR なし・未 push                |    1 | 中身は #136 に取り込み済みと推定。**目視確認のうえ**削除 |

## 📋 明細

| ブランチ                                          | 最終 commit | リモート | main 祖先 | main より先行 | PR                    | 提案      |
| ------------------------------------------------- | ----------- | -------- | --------- | ------------: | --------------------- | --------- |
| chore/state-sync-20260806                         | 2026-08-06  | あり     | ✅        |             0 | #114 MERGED           | 削除      |
| docs/changelog-version-sync-20260806              | 2026-08-06  | あり     | ✅        |             0 | #115 MERGED           | 削除      |
| docs/ops-ci-production-readiness-20260812         | 2026-08-12  | あり     | –         |             1 | #121 MERGED（squash） | 削除      |
| docs/production-status-20260806                   | 2026-08-06  | あり     | ✅        |             0 | #116 MERGED           | 削除      |
| docs/runbook-shared-checkout-note                 | 2026-08-06  | あり     | ✅        |             0 | #119 MERGED           | 削除      |
| feat/alerting-restore-drill                       | 2026-08-06  | あり     | ✅        |             0 | #117 MERGED           | 削除      |
| feat/mvp-auth-bypass                              | 2026-09-18  | なし     | –         |             7 | #134 MERGED（squash） | 削除      |
| feat/phase1-core-20260812                         | 2026-08-12  | あり     | –         |             2 | #124 MERGED（squash） | 削除      |
| feat/webui-fqdn-cloudflare-tunnel                 | 2026-08-04  | あり     | ✅        |             0 | #110 MERGED           | 削除      |
| fix/autocompact-context-hygiene                   | 2026-08-04  | あり     | –         |             2 | #105 MERGED（squash） | 削除      |
| fix/frontend-security-headers                     | 2026-08-06  | あり     | ✅        |             0 | #113 MERGED           | 削除      |
| fix/issue-93-appsview-api-driven-modal            | 2026-08-04  | あり     | –         |             2 | #108 MERGED（squash） | 削除      |
| fix/login-401-redirect-loop                       | 2026-08-04  | あり     | ✅        |             0 | #111 MERGED           | 削除      |
| fix/phase1-release-ready                          | 2026-08-06  | あり     | ✅        |             0 | #112 MERGED           | 削除      |
| **fix/production-reliability-hardening-20260918** | 2026-09-18  | なし     | –         |             8 | なし                  | ⚠️ 要確認 |
| fix/security-deps-pip-audit-20260804              | 2026-08-04  | あり     | –         |             1 | #107 MERGED（squash） | 削除      |
| fix/security-rbac-authz-20260812                  | 2026-08-12  | あり     | –         |             3 | #122 MERGED（squash） | 削除      |

「main より先行」が 1 以上でも、squash merge のため commit が別 SHA になっているだけのものは「削除」としている。

## ⚠️ 要確認: fix/production-reliability-hardening-20260918

- 8 commit（本番無音障害の検知修正、OCR API の認可欠落修正、WCAG 2.5.8 対応、電子納品の整合性修正 など）
- merge-base からの変更は 58 ファイルだが、**現在の main との差分は 12 ファイルのみ**（CHANGELOG・runbook・retention 系・healthcheck・mockAdapter・state.json・認可テスト）
- 同じ日の #136（`60ff8f3`）にこれらの修正が取り込まれ、残りの差分はその後の main の変更（#137〜#143）と推定される
- 👉 12 ファイルの差分を目視で確認し、main 側が新しいことを確かめてから削除する

## 🔧 削除コマンド（承認後に実行）

```bash
# リモート（14 件）
git push origin --delete chore/state-sync-20260806 docs/changelog-version-sync-20260806 \
  docs/ops-ci-production-readiness-20260812 docs/production-status-20260806 \
  docs/runbook-shared-checkout-note feat/alerting-restore-drill feat/phase1-core-20260812 \
  feat/webui-fqdn-cloudflare-tunnel fix/autocompact-context-hygiene fix/frontend-security-headers \
  fix/issue-93-appsview-api-driven-modal fix/login-401-redirect-loop fix/phase1-release-ready \
  fix/security-deps-pip-audit-20260804 fix/security-rbac-authz-20260812
# ローカル（squash 済みは -D が必要）
git branch -D <上記 + feat/mvp-auth-bypass>
```
