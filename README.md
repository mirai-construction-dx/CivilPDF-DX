# 📄 CivilPDF-DX — 建設・土木業務 PDF プラットフォーム

> **現場の書類管理を、もっとシンプルに。もっと安全に。**

[![CI](https://github.com/mirai-construction-dx/CivilPDF-DX/actions/workflows/ci.yml/badge.svg)](https://github.com/mirai-construction-dx/CivilPDF-DX/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📌 このシステムでできること

**CivilPDF-DX** は、建設・土木業の現場で日々発生する PDF 書類を **安全に・確実に・法令に沿って** 管理するためのシステムです。

紙や個別のファイルサーバーに散在しがちな工事図面・仕様書・承認書類を一か所に集め、チーム全員が適切な権限でアクセスできる環境を提供します。

---

## 👥 こんな方に向けています

| 対象                      | 活用シーン                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------ |
| 🏗️ **現場施工管理者**     | 図面・施工計画書をスマートフォン・タブレットで即確認。承認待ち状況をリアルタイム把握 |
| 📐 **土木・建設技術者**   | 書類の検索・比較・バージョン管理。AI が図面種別（平面図・断面図など）を自動判定      |
| 👔 **経営役員・管理職**   | 工事進捗・承認状況のダッシュボードで一目把握。組織全体の書類状況を可視化             |
| 🔍 **監査法人・内部監査** | 全操作の改ざん検知付き証跡ログ。電子帳簿保存法 7 年保持・法令準拠レポートを即時出力  |
| 🏢 **本社・支店管理部門** | 本社 → 支店 → 現場事務所の階層別アクセス制御。組織を横断した文書管理                 |

---

## 🎯 解決する課題

### ❌ これまでの問題

- 📂 図面がメール添付・USB メモリ・個人 PC に散在していた
- 🔄 「最新版」「旧版」の混乱で誰が正しい図面を持っているか不明
- ✏️ 承認プロセスが口頭・判子・メールで管理が属人化
- 📋 監査・提出時に証跡を集めるのに数日かかっていた
- 📦 国交省への電子納品 ZIP 作成に手作業で数時間

### ✅ CivilPDF-DX で解決

- 🗂️ **一か所に集約** — 全ての PDF 書類を安全なサーバーで統合管理
- 🔢 **バージョン自動管理** — 最新版が常に明確。旧版との差分も追跡
- ✅ **電子承認ワークフロー** — 多段階承認をシステムで管理。承認状況をリアルタイム通知
- 🔍 **完全な証跡** — 誰が・いつ・何を見たかを全自動で記録・改ざん検知
- 📦 **電子納品ワンクリック** — 国交省 CALS/EC 準拠の ZIP を自動生成

---

## ✨ 主な機能

### 📄 文書管理

- PDF のアップロード・閲覧・ダウンロード
- 書類種別・プロジェクトごとの整理
- AI による図面種別の自動判定（平面図・立面図・断面図・構造図など）
- セマンティック検索（「橋梁補修」で関連書類をまとめて発見）

### ✅ 承認ワークフロー

- 多段階承認（担当者 → 主任 → 管理者）
- 承認・却下・コメントをシステムで完結
- 承認者向け AI 自動要約（長文書類を 3〜5 行で把握）

### 🔍 監査・コンプライアンス

- 全操作の自動記録（閲覧・ダウンロード・承認・削除すべて）
- SHA-256 ハッシュチェーンによる改ざん検知
- 電子帳簿保存法 7 年保持ポリシーの自動管理

### 📦 電子納品

- 国交省 CALS/EC 準拠の電子納品 ZIP をワンクリック生成
- INDEX.XML・フォルダ構成を自動作成

### 🏢 組織管理

- 本社 → 支店 → 現場事務所 → 現場の階層構造
- 組織ごとにアクセス範囲を制御（他組織の書類は見えない）

### 🤖 AI アシスト

- **図面種別の自動分類** — 図面を読み込むだけで種別を自動判定
- **構造化データ抽出** — 工事名・施工会社・金額・工期を自動抽出
- **承認者向け要約** — 長大な仕様書も AI が要点を整理

### 📥 アプリ配信（PDF Editor Client）

- デスクトップ版 **PDF Editor Client**（電子印鑑・OCR・大判図面）の配布窓口。本体は別リポジトリ [CivilPDF-Editor](https://github.com/Kensan196948G/CivilPDF-Editor)（Tauri v2・現行 v1.2.4）
- 🪟 **Windows のみ提供**: インストーラー (.exe / NSIS・.msi 選択式、Windows 10 / 11 64bit)
- ⏸️ macOS: **後日対応（ペンディング）** — 配信ページに「後日対応」と表示
- 🐧 Linux: 提供対象外
- リリースノート・ビルド情報・SHA-256 チェックサムを配信ページで提供
- Stable チャンネルのみ提供（未署名ビルド）
- 運用手順: [docs/deployment/app-distribution.md](docs/deployment/app-distribution.md)

---

## 🛡️ 法令・規格への対応状況

| 法令・規格                           | 対応内容                                                       | 状態        |
| ------------------------------------ | -------------------------------------------------------------- | ----------- |
| ⚖️ **e-文書法**                      | RFC 3161 電子タイムスタンプによる電子文書の真正性証明          | ✅ 対応済み |
| 📦 **国交省 CALS/EC 電子納品**       | 電子納品要領準拠 ZIP 生成（INDEX.XML・フォルダ構成）           | ✅ 対応済み |
| 📋 **電子帳簿保存法**                | 書類種別別 7 年保持ポリシーの自動管理                          | ✅ 対応済み |
| 🌍 **GDPR（EU 一般データ保護規則）** | Art.17 削除権・同意管理・物理削除バッチ                        | ✅ 対応済み |
| 🏗️ **ISO 19650**                     | 建設情報管理メタデータ（文書種別・改訂番号・プロジェクト情報） | ✅ 対応済み |
| 📄 **PDF/A（ISO 14289）**            | 長期保存用 PDF 形式の検証（arXiv 提出・公文書保管用途）        | ✅ 対応済み |

---

## 🔐 セキュリティと権限管理

書類へのアクセスは **4 段階のロール** で厳密に制御します。

| ロール              | 対象者の例                   | できること                     |
| ------------------- | ---------------------------- | ------------------------------ |
| 👤 **管理者**       | システム担当者・IT 部門      | 全機能・ユーザー管理・設定変更 |
| 👔 **マネージャー** | 現場所長・部長・主任         | 承認・監査ログ閲覧・電子納品   |
| 🔧 **エンジニア**   | 施工管理者・担当技術者       | 書類アップロード・承認申請     |
| 👁️ **閲覧者**       | 経営役員・協力会社・監査法人 | 書類・ダッシュボードの閲覧のみ |

全操作は **改ざん検知付きログ** として自動記録され、監査時に即座に提出できます。

---

## 🌐 アクセス方法

コンピューター・タブレット・スマートフォンから  
以下の URL でブラウザ（Chrome / Edge 推奨）でアクセスできます。

```
https://civilpdf.mirai-dx-platform.com/
```

> 🔒 通信は Cloudflare Tunnel 経由の HTTPS で保護され、利用にはアカウントでのログインが必要です。  
> 💻 インストール不要。ブラウザがあればすぐに使えます。  
> 🔧 構成の詳細・運用手順: `docs/deployment/webui-cloudflare-tunnel.md`

---

### 🧪 MVP / Prototype（評価・デモ用）

本番と完全分離した MVP 環境を公開しています。架空のダミーデータが投入済みで、
アカウントがあれば主要ユースケースを直ちに操作・評価できます。

```
https://civilpdf-mvp.mirai-dx-platform.com/
```

- ログイン例: `admin@demo.civilpdf.example` / `CivilPDF-Demo-2026!`（全ロール共通・架空データ）
- 手順・データ構成: [docs/deployment/mvp-preview-environment.md](docs/deployment/mvp-preview-environment.md)
- ローカル起動: `docker compose -f docker-compose.mvp.yml up -d --build` → http://localhost:5183/

## 📊 システム稼働状況

| 項目                        | 状態                                                                                                                                                                                                  |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🟢 **本番稼働**             | 2026-08-06 本番デプロイ済み（Cloudflare Tunnel・systemd 稼働中）。外形監視 200 OK（2026-09-18 確認）                                                                                                  |
| 🟠 **MVPデモ環境**          | https://civilpdf-mvp.mirai-dx-platform.com/ は 502（到達不可、2026-09-18 確認）。復旧作業中。本番への影響なし                                                                                         |
| 🧪 **テスト網羅率**         | 691 件（backend 394 + integration 20 + frontend vitest 271 + Playwright 6）。frontend vitest 271/271 実測一致（2026-09-18）                                                                           |
| ⚠️ **CI/CD 直近状態**       | main 直近実行（2026-08-15）は 11/12（`Frontend Dependency Audit (npm audit)` が nanoid 等の依存脆弱性で失敗）。以後 1 か月 CI 未実行。「12/12 success」の表記は撤回し実態に合わせて修正（2026-09-18） |
| 🔒 **セキュリティスキャン** | CI で自動脆弱性チェックを構成（gitleaks・pip-audit・npm audit）。直近 CI 実行時点で npm audit 検出分は未解消（上記）                                                                                  |
| 🔔 **監視**                 | 5 分毎ヘルスチェック＋障害/復旧メール通知、四半期毎バックアップ復元訓練（初回 2026-08-06 PASS。継続実施は今後の実績を要蓄積）                                                                         |

---

## 📚 詳細資料（関係部門向け）

| 資料                       | 対象                         | リンク                                                                                             |
| -------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------- |
| 🖥️ **IT 部門向けガイド**   | システム担当者・インフラ担当 | [docs/for-it-staff.md](docs/for-it-staff.md)                                                       |
| 🔧 **技術スタック詳細**    | エンジニア・開発者           | [docs/tech-stack.md](docs/tech-stack.md)                                                           |
| 📋 **要件定義書**          | PM・管理職                   | [docs/requirements.md](docs/requirements.md)                                                       |
| 🏗️ **システム構成図**      | アーキテクト・IT担当         | [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md)               |
| ⚙️ **運用 Runbook**        | 運用管理者・IT担当           | [docs/operations/runbook.md](docs/operations/runbook.md)                                           |
| 🚀 **本番デプロイ手順**    | IT担当・インフラ             | [docs/deployment/docker-production-deployment.md](docs/deployment/docker-production-deployment.md) |
| 📦 **アプリ配信運用**      | IT担当・配布管理             | [docs/deployment/app-distribution.md](docs/deployment/app-distribution.md)                         |
| 📋 **WebUI 画面一覧**      | PM・現場担当                 | [docs/webui-screens.md](docs/webui-screens.md)                                                     |
| 🧪 **MVP プレビュー環境**  | 評価者・関係者               | [docs/deployment/mvp-preview-environment.md](docs/deployment/mvp-preview-environment.md)           |
| 🪟 **Windows 11 展開手順** | IT部門                       | [docs/windows-deployment.md](docs/windows-deployment.md)                                           |
| 📋 **コンプライアンス**    | 法務・監査                   | [docs/compliance.md](docs/compliance.md)                                                           |

---

## 🆘 問い合わせ・サポート

- 🐛 **不具合報告・改善要望** → [GitHub Issues](https://github.com/mirai-construction-dx/CivilPDF-DX/issues)
- 🔒 **セキュリティ脆弱性** → [SECURITY.md](SECURITY.md) の手順で報告
- 📄 **ライセンス** → [MIT License](LICENSE)

---

## 🤖 開発体制

このシステムは [Claude Code](https://claude.ai/claude-code)（Anthropic 社の AI 開発ツール）を活用し、
[CodeRabbit](https://coderabbit.ai) による AI コードレビューと GitHub Actions による自動テストで品質を維持しています。

---

_最終更新: 2026-08-13 | MVP/Prototype 公開（v0.9.0）— LICENSE 修復・PyJWT 移行・認証レート制限・CSV 出力・架空ダミーデータ・MVP 用公開 URL_
