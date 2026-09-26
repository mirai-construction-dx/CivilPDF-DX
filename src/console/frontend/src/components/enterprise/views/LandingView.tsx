import { type FC } from "react";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

const pillars = [
  {
    id: "pdf",
    title: "PDF業務基盤",
    icon: "📄",
    desc: "電子納品対応のPDF処理エンジン。PDF/A変換・結合・分割・注釈・OCRを一元管理。",
    feats: ["PDF/A-1b", "OCR", "結合/分割", "変換"],
    view: "documents",
  },
  {
    id: "drawings",
    title: "図面帳票管理",
    icon: "🗂️",
    desc: "A0/A1大判図面の遅延レンダリング対応。版管理・改訂履歴・現場配布を効率化。",
    feats: ["大判対応", "版管理", "改訂履歴", "配布"],
    view: "documents",
  },
  {
    id: "security",
    title: "セキュリティ統制",
    icon: "🔒",
    desc: "Entra ID SSO・DLP・透かし・IP制限・暗号化で企業レベルのセキュリティを実現。",
    feats: ["SSO", "DLP", "透かし", "IP制限"],
    view: "security",
  },
  {
    id: "audit",
    title: "操作監査",
    icon: "📋",
    desc: "ハッシュチェーン改ざん防止付き監査ログ。全操作を追記専用ログで完全記録。",
    feats: ["改ざん防止", "全操作記録", "エクスポート", "SIEM連携"],
    view: "audit",
  },
  {
    id: "m365",
    title: "Microsoft365連携",
    icon: "🔗",
    desc: "SharePoint・OneDrive・Teams・Exchange・Entra IDとシームレスに統合。",
    feats: ["SharePoint", "Teams", "OneDrive", "Exchange"],
    view: "m365",
  },
  {
    id: "workflow",
    title: "配布承認WF",
    icon: "✅",
    desc: "担当者→現場代理人→監理技術者→支店長→本社の多段承認フローを自動化。",
    feats: ["多段承認", "電子印鑑", "リマインダー", "期限管理"],
    view: "workflows",
  },
];

const techPanels = [
  {
    id: "sp",
    label: "Microsoft 365",
    sub: "SharePoint / OneDrive / Teams",
    logo: "M365",
  },
  {
    id: "sharepointsync",
    label: "SharePoint Sync",
    sub: "双方向リアルタイム同期",
    logo: "SP",
  },
  { id: "entra", label: "Entra ID", sub: "OIDC/SAML 2.0 + MSAL", logo: "EID" },
  { id: "forti", label: "FortiGate", sub: "ゼロトラスト・IP制限", logo: "FG" },
  {
    id: "hennge",
    label: "HENNGE ONE",
    sub: "MFA・デバイス制御・SSO",
    logo: "HO",
  },
  {
    id: "winserver",
    label: "Windows Server",
    sub: "AD連携・グループポリシー",
    logo: "WS",
  },
];

const footerLinks: { label: string; view: string }[] = [
  { label: "ダッシュボード", view: "dashboard" },
  { label: "ドキュメント", view: "documents" },
  { label: "セキュリティ", view: "security" },
  { label: "監査ログ", view: "audit" },
  { label: "アプリ配布", view: "apps" },
  { label: "Microsoft365", view: "m365" },
  { label: "システム設定", view: "settings" },
];

export const LandingView: FC<ViewProps> = ({ onNavigate }) => {
  return (
    <div className="ep ep-lp">
      {/* ===== HERO ===== */}
      <section className="ep-hero">
        <div>
          <span className="ep-eyebrow">
            建設・土木業向け PDF 業務管理プラットフォーム
          </span>
          <h1>
            現場の<em>PDF業務</em>を<br />
            デジタルで完結する
          </h1>
          <p className="lead">
            GUIデスクトップアプリ +
            Webコンソールの2層構成。電子納品・承認フロー・
            セキュリティ統制・M365連携をオールインワンで提供します。
          </p>
          <div className="ep-hero-cta">
            <button
              className="ep-btn ep-btn-primary"
              onClick={() => onNavigate("apps")}
            >
              <span aria-hidden="true">⬇</span>
              アプリをDL
            </button>
            <button
              className="ep-btn ep-btn-secondary"
              onClick={() => onNavigate("dashboard")}
            >
              <span aria-hidden="true">🖥️</span>
              管理コンソールへ
            </button>
            <button
              className="ep-btn ep-btn-secondary"
              onClick={() => onNavigate("upload")}
            >
              <span aria-hidden="true">🔍</span>
              PDFを解析する
            </button>
          </div>
          {/* Static page: show capabilities, not unmeasured usage numbers. */}
          <div className="ep-hero-meta">
            <div>
              <strong>PDF/A</strong>
              <span>電子納品向け変換</span>
            </div>
            <div>
              <strong>SHA-256</strong>
              <span>改ざん検知付き監査ログ</span>
            </div>
            <div>
              <strong>7年</strong>
              <span>電子帳簿保存法の保持管理</span>
            </div>
            <div>
              <strong>Windows</strong>
              <span>PDF Editor 配布</span>
            </div>
          </div>
        </div>

        {/* Architecture diagram */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            userSelect: "none",
          }}
        >
          {/* Top layer: apps */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px",
            }}
          >
            <div
              className="ep-panel"
              style={{
                padding: "10px 12px",
                textAlign: "center",
                cursor: "pointer",
              }}
              onClick={() => onNavigate("apps")}
            >
              <div style={{ fontSize: "11px", fontWeight: 600 }}>GUI App</div>
              <div
                style={{
                  fontSize: "10px",
                  color: "var(--muted)",
                  marginTop: "2px",
                }}
              >
                Windows EXE
              </div>
            </div>
            <div
              className="ep-panel"
              style={{
                padding: "10px 12px",
                textAlign: "center",
                cursor: "pointer",
              }}
              onClick={() => onNavigate("dashboard")}
            >
              <div style={{ fontSize: "11px", fontWeight: 600 }}>
                Web Console
              </div>
              <div
                style={{
                  fontSize: "10px",
                  color: "var(--muted)",
                  marginTop: "2px",
                }}
              >
                React + FastAPI
              </div>
            </div>
          </div>
          {/* Arrow */}
          <div
            style={{
              textAlign: "center",
              color: "var(--muted)",
              fontSize: "11px",
            }}
          >
            ↕ API / OIDC
          </div>
          {/* Middle layer: core services */}
          <div
            className="ep-panel"
            style={{ padding: "10px 14px", cursor: "pointer" }}
            onClick={() => onNavigate("documents")}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: "4px",
                textAlign: "center",
              }}
            >
              {["PDF Engine", "OCR", "電子印鑑", "同期Agent"].map((s) => (
                <div key={s}>
                  <div style={{ fontSize: "10px", fontWeight: 600 }}>{s}</div>
                </div>
              ))}
            </div>
          </div>
          {/* Arrow */}
          <div
            style={{
              textAlign: "center",
              color: "var(--muted)",
              fontSize: "11px",
            }}
          >
            ↕ Auth / Data
          </div>
          {/* Bottom layer: infra */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "6px",
            }}
          >
            {[
              { label: "PostgreSQL", sub: "DB" },
              { label: "Entra ID", sub: "IdP" },
              { label: "SQLite", sub: "Local" },
            ].map((item) => (
              <div
                key={item.label}
                className="ep-panel"
                style={{ padding: "7px 10px", textAlign: "center" }}
              >
                <div style={{ fontSize: "10px", fontWeight: 600 }}>
                  {item.label}
                </div>
                <div
                  style={{
                    fontSize: "9px",
                    color: "var(--muted)",
                    marginTop: "1px",
                  }}
                >
                  {item.sub}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 6つの柱 ===== */}
      <section className="ep-lp-section">
        <div style={{ marginBottom: "20px" }}>
          <span className="ep-eyebrow">プラットフォームの柱</span>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "22px",
              fontWeight: 600,
              letterSpacing: "-0.02em",
              marginTop: "8px",
            }}
          >
            6つの柱で現場DXを支える
          </h2>
        </div>
        <div className="ep-pillars">
          {pillars.map((p) => (
            <div
              key={p.id}
              className="ep-pillar"
              style={{ cursor: "pointer" }}
              onClick={() => onNavigate(p.view)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onNavigate(p.view);
              }}
            >
              <div className="icn">{p.icon}</div>
              <h3>{p.title}</h3>
              <p>{p.desc}</p>
              <div className="feats">
                {p.feats.map((f) => (
                  <span key={f}>{f}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== 環境親和性 ===== */}
      <section className="ep-lp-section">
        <div style={{ marginBottom: "20px" }}>
          <span className="ep-eyebrow">エコシステム連携</span>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "22px",
              fontWeight: 600,
              letterSpacing: "-0.02em",
              marginTop: "8px",
            }}
          >
            既存インフラと親和する
          </h2>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "10px",
          }}
        >
          {techPanels.map((tp) => (
            <div
              key={tp.id}
              className="ep-panel"
              style={{ padding: "14px 16px", cursor: "pointer" }}
              onClick={() => onNavigate("m365")}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onNavigate("m365");
              }}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: "10px" }}
              >
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "8px",
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    display: "grid",
                    placeItems: "center",
                    fontFamily: "var(--font-mono)",
                    fontSize: "9px",
                    fontWeight: 700,
                    color: "var(--accent)",
                    flexShrink: 0,
                  }}
                >
                  {tp.logo}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "13px" }}>
                    {tp.label}
                  </div>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "var(--muted)",
                      marginTop: "2px",
                    }}
                  >
                    {tp.sub}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer>
        <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
          <div className="ep-brand-mark" />
          <span style={{ fontWeight: 600, fontSize: "12px" }}>CivilPDF-DX</span>
          <span style={{ color: "var(--muted)", fontSize: "11px" }}>
            建設・土木業向けPDF業務管理プラットフォーム
          </span>
        </div>
        <nav style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          {footerLinks.map((link) => (
            <button
              key={link.view}
              className="ep-nav-btn"
              onClick={() => onNavigate(link.view)}
            >
              {link.label}
            </button>
          ))}
        </nav>
      </footer>
    </div>
  );
};
