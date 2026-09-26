import { type FC, useState, useEffect, useRef, useCallback } from "react";
import "../../styles/enterprise.css";
import { LandingView } from "./views/LandingView";
import { DashboardView } from "./views/DashboardView";
import { UploadView } from "./views/UploadView";
import { ViewerView } from "./views/ViewerView";
import { AppsView } from "./views/AppsView";
import { EditorSyncView } from "./views/EditorSyncView";
import { SecurityView } from "./views/SecurityView";
import { M365View } from "./views/M365View";
import { PrivacyView } from "./views/PrivacyView";
// ── Functional, API-connected pages integrated into the enterprise shell ──
// These replace the former static-mockup views so Phase 5–8 features
// (timestamp / electronic delivery / RBAC / workflow / audit) are reachable.
import { Documents } from "../../pages/Documents";
import { Projects } from "../../pages/Projects";
import { Workflows } from "../../pages/Workflows";
import { AuditLogs } from "../../pages/AuditLogs";
import { Settings as SettingsPage } from "../../pages/Settings";
import { Users } from "../../pages/Users";
import { useAuthStore } from "../../store/auth";
import { getStats } from "../../api/stats";
import type { UserResponse } from "../../api/auth";
import {
  listNotifications,
  markAllRead as apiMarkAllRead,
  markRead as apiMarkRead,
  type NotificationItem,
} from "../../api/notifications";

type ViewId =
  | "lp"
  | "dashboard"
  | "documents"
  | "projects"
  | "upload"
  | "viewer"
  | "workflow"
  | "apps"
  | "editor"
  | "security"
  | "audit"
  | "m365"
  | "settings"
  | "privacy"
  | "users";
type DashSubView = "overview" | "stats" | "dist" | "users";
type Role = "op" | "rev" | "adm";
type ToastType = "ok" | "warn" | "error";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ModalContent {
  title: string;
  body: string;
}

const NAV_GROUPS = [
  {
    label: "Workspace",
    items: [
      { id: "lp", label: "概要" },
      { id: "dashboard", label: "ダッシュボード" },
    ],
  },
  {
    label: "Docs",
    items: [
      { id: "documents", label: "図書管理" },
      { id: "projects", label: "プロジェクト" },
      { id: "upload", label: "取込/解析" },
      { id: "viewer", label: "ビューア" },
      { id: "workflow", label: "ワークフロー" },
    ],
  },
  {
    label: "Platform",
    items: [
      { id: "apps", label: "アプリ配布" },
      { id: "editor", label: "Editor連携" },
      { id: "security", label: "セキュリティ" },
      { id: "audit", label: "監査" },
      { id: "m365", label: "Microsoft365" },
      { id: "privacy", label: "プライバシー" },
      { id: "users", label: "ユーザー管理" },
      { id: "settings", label: "システム設定" },
    ],
  },
];

const ROLE_LABELS: Record<Role, string> = {
  op: "操作担当",
  rev: "回覧担当",
  adm: "管理者",
};

/** Map system user role → display role */
const SYSTEM_ROLE_MAP: Record<UserResponse["role"], Role> = {
  admin: "adm",
  manager: "rev",
  engineer: "op",
  viewer: "op",
};

const ROLE_BADGE_LABELS: Record<UserResponse["role"], string> = {
  admin: "管理者",
  manager: "マネージャー",
  engineer: "エンジニア",
  viewer: "閲覧者",
};

const SEARCH_INDEX = [
  {
    label: "概要ページ",
    desc: "ランディング / ビューへ移動",
    view: "lp",
    icon: "🏠",
  },
  {
    label: "ダッシュボード",
    desc: "KPI・ジョブ概要",
    view: "dashboard",
    icon: "📊",
  },
  {
    label: "図書管理",
    desc: "文書一覧・フィルタ・電子タイムスタンプ",
    view: "documents",
    icon: "📁",
  },
  {
    label: "プロジェクト",
    desc: "プロジェクト管理・電子納品パッケージ生成",
    view: "projects",
    icon: "🏗️",
  },
  {
    label: "取込/解析",
    desc: "PDFアップロード・OCR解析",
    view: "upload",
    icon: "⬆️",
  },
  {
    label: "ビューア",
    desc: "PDFプレビュー・チェック",
    view: "viewer",
    icon: "👁",
  },
  {
    label: "ワークフロー",
    desc: "承認フロー・電子印鑑",
    view: "workflow",
    icon: "✅",
  },
  {
    label: "アプリ配布",
    desc: "Desktop Client配布管理",
    view: "apps",
    icon: "📱",
  },
  {
    label: "セキュリティ",
    desc: "SSO・MFA・ポリシー",
    view: "security",
    icon: "🔒",
  },
  { label: "監査ログ", desc: "操作履歴・証跡管理", view: "audit", icon: "📋" },
  {
    label: "Microsoft365",
    desc: "SharePoint・Teams連携",
    view: "m365",
    icon: "☁️",
  },
  {
    label: "プライバシー管理",
    desc: "同意管理・データエクスポート・削除権 (GDPR/CCPA)",
    view: "privacy",
    icon: "🔐",
  },
  {
    label: "ユーザー管理",
    desc: "ユーザー一覧・RBAC・権限管理",
    view: "users",
    icon: "👥",
  },
  {
    label: "システム設定",
    desc: "一般・ユーザー・セキュリティ設定",
    view: "settings",
    icon: "⚙️",
  },
];

let _toastSeq = 0;

/** Render modal body text safely — newlines become line breaks, no HTML eval */
function ModalBody({ text }: { text: string }) {
  return (
    <div className="ep-modal-body">
      {text.split("\n").map((line, i) => (
        <span key={i}>
          {line}
          {i < text.split("\n").length - 1 && <br />}
        </span>
      ))}
    </div>
  );
}

export const EnterpriseLayout: FC = () => {
  const { user, logout } = useAuthStore();

  const [currentView, setCurrentView] = useState<ViewId>("lp");
  const [dashSubView, setDashSubView] = useState<DashSubView>("overview");
  const [period, setPeriod] = useState<number>(30);
  const [filter, setFilter] = useState<string>("all");
  const [role, setRole] = useState<Role>("adm");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [modal, setModal] = useState<ModalContent | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<number | null>(null);
  const [showNotif, setShowNotif] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showPalette, setShowPalette] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteCursor, setPaletteCursor] = useState(0);
  const [showTweaks, setShowTweaks] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [accentHue, setAccentHue] = useState(255);
  const [density, setDensity] = useState<"compact" | "default" | "spacious">(
    "default",
  );
  const [sidebarWidth, setSidebarWidth] = useState(220);

  const notifRef = useRef<HTMLDivElement>(null);
  const tweaksRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const paletteInputRef = useRef<HTMLInputElement>(null);

  // ── Notification + counter polling (30s) ─────────────────────────────
  // The workflow badge used to be a hardcoded "7", so every user saw a fake
  // pending-approval count. It now comes from the same stats endpoint the
  // dashboard uses. Both requests share one interval so a phone on a site
  // network does not open two polling timers.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    async function refresh() {
      try {
        const page = await listNotifications(1, 20);
        if (!cancelled) setNotifications(page.items);
      } catch {
        // keep current list on transient errors
      }
      try {
        const stats = await getStats();
        if (!cancelled) setPendingApprovals(stats.pending_approvals ?? 0);
      } catch {
        // keep the previous count; the badge simply stays as it was
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user]);

  // ── Idle session timeout (30 minutes) ────────────────────────────────
  useEffect(() => {
    if (!user) return;
    const IDLE_MS = 30 * 60 * 1000;
    const expire = () => {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    };
    let timer = window.setTimeout(expire, IDLE_MS);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(expire, IDLE_MS);
    };
    const events = [
      "mousemove",
      "mousedown",
      "keydown",
      "touchstart",
      "scroll",
    ];
    events.forEach((ev) =>
      document.addEventListener(ev, reset, { passive: true }),
    );
    return () => {
      window.clearTimeout(timer);
      events.forEach((ev) => document.removeEventListener(ev, reset));
    };
  }, [user]);

  // ── Auto-select role from logged-in user ────────────────────────────
  useEffect(() => {
    if (!user) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRole(SYSTEM_ROLE_MAP[user.role]);
  }, [user]);

  // ── Dark mode / density / accent apply ──────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute(
      "data-theme",
      darkMode ? "dark" : "light",
    );
  }, [darkMode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--accent-hue",
      String(accentHue),
    );
  }, [accentHue]);

  // ── Close dropdowns on outside click ────────────────────────────────
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotif(false);
      }
      if (tweaksRef.current && !tweaksRef.current.contains(e.target as Node)) {
        setShowTweaks(false);
      }
      if (
        profileRef.current &&
        !profileRef.current.contains(e.target as Node)
      ) {
        setShowProfile(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Command palette keyboard shortcut ───────────────────────────────
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowPalette((prev) => !prev);
        setPaletteQuery("");
        setPaletteCursor(0);
      }
      if (e.key === "Escape") {
        setShowPalette(false);
        setModal(null);
        setShowProfile(false);
      }
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (showPalette) {
      setTimeout(() => paletteInputRef.current?.focus(), 50);
    }
  }, [showPalette]);

  // ── Toast management ────────────────────────────────────────────────
  const showToast = useCallback((message: string, type: ToastType = "ok") => {
    const id = ++_toastSeq;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      3500,
    );
  }, []);

  const showModal = useCallback((content: ModalContent) => {
    setModal(content);
  }, []);

  const navigate = useCallback(
    (view: string) => {
      if (view === "dashboard") {
        setCurrentView("dashboard");
        setDashSubView("overview");
      } else {
        setCurrentView(view as ViewId);
      }
      showToast(`${view} に移動しました`, "ok");
    },
    [showToast],
  );

  // ── Notification helpers ─────────────────────────────────────────────
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function markAllRead() {
    await apiMarkAllRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  }

  async function clearAll() {
    await apiMarkAllRead();
    setNotifications([]);
  }

  async function handleNotifClick(n: NotificationItem) {
    await apiMarkRead(n.id);
    setNotifications((prev) =>
      prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)),
    );
    const targetView =
      n.resource_type === "workflow"
        ? "workflow"
        : n.resource_type === "document"
          ? "documents"
          : null;
    if (targetView) {
      setShowNotif(false);
      navigate(targetView);
    }
  }

  // ── Palette results ──────────────────────────────────────────────────
  const paletteResults = paletteQuery
    ? SEARCH_INDEX.filter(
        (item) =>
          item.label.includes(paletteQuery) || item.desc.includes(paletteQuery),
      )
    : SEARCH_INDEX;

  function handlePaletteKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setPaletteCursor((c) => Math.min(c + 1, paletteResults.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setPaletteCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      const item = paletteResults[paletteCursor];
      if (item) {
        setShowPalette(false);
        navigate(item.view);
      }
    }
  }

  // ── Dashboard sidebar click (period/filter/sub-view) ─────────────────
  function handleDashSidebarClick(id: string) {
    if (
      id === "overview" ||
      id === "stats" ||
      id === "dist" ||
      id === "users"
    ) {
      setDashSubView(id as DashSubView);
    } else if (id === "p7") setPeriod(7);
    else if (id === "p30") setPeriod(30);
    else if (id === "p90") setPeriod(90);
    else if (id === "fall") setFilter("all");
    else if (id === "fok") setFilter("ok");
    else if (id === "fng") setFilter("ng");
  }

  // ── Logout ───────────────────────────────────────────────────────────
  function handleLogout() {
    logout();
    setShowProfile(false);
    showToast("ログアウトしました", "ok");
  }

  // ── Profile display data ─────────────────────────────────────────────
  const profileData = user ?? {
    full_name: "管理者ユーザー",
    email: "admin@civilpdf.local",
    role: "admin" as const,
    status: "active" as const,
    created_at: "",
    last_login: null,
    id: "demo",
    username: "admin",
  };
  const avatarInitial = profileData.full_name?.[0]?.toUpperCase() ?? "管";

  // ── View renderer ────────────────────────────────────────────────────
  const viewProps = {
    onNavigate: navigate,
    onShowModal: showModal,
    onShowToast: showToast,
  };

  function renderView() {
    switch (currentView) {
      case "lp":
        return <LandingView {...viewProps} />;
      case "dashboard":
        return (
          <div style={{ display: "flex", minHeight: "100%" }}>
            {/* Dashboard sub-sidebar */}
            <aside
              className="ep-dash-sub-sidebar"
              style={{ width: sidebarWidth, minWidth: 160 }}
            >
              <div className="ep-sub-sidebar-group">
                <p className="ep-sub-sidebar-label">ビュー</p>
                {[
                  { id: "overview", label: "概観" },
                  { id: "stats", label: "処理統計" },
                  { id: "dist", label: "アプリ配布" },
                  { id: "users", label: "ユーザー" },
                ].map((item) => (
                  <button
                    key={item.id}
                    className={`ep-sub-sidebar-item${dashSubView === item.id ? " active" : ""}`}
                    onClick={() => handleDashSidebarClick(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="ep-sub-sidebar-group">
                <p className="ep-sub-sidebar-label">期間</p>
                {[
                  { id: "p7", label: "過去7日", val: 7 },
                  { id: "p30", label: "過去30日", val: 30 },
                  { id: "p90", label: "過去90日", val: 90 },
                ].map((item) => (
                  <button
                    key={item.id}
                    className={`ep-sub-sidebar-item${period === item.val ? " active" : ""}`}
                    onClick={() => handleDashSidebarClick(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="ep-sub-sidebar-group">
                <p className="ep-sub-sidebar-label">フィルタ</p>
                {[
                  { id: "fall", label: "全プロジェクト", val: "all" },
                  { id: "fok", label: "完了のみ", val: "ok" },
                  { id: "fng", label: "NGあり", val: "ng" },
                ].map((item) => (
                  <button
                    key={item.id}
                    className={`ep-sub-sidebar-item${filter === item.val ? " active" : ""}`}
                    onClick={() => handleDashSidebarClick(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </aside>
            <div style={{ flex: 1, overflow: "auto" }}>
              <DashboardView
                {...viewProps}
                subView={dashSubView}
                period={period}
                filter={filter}
              />
            </div>
          </div>
        );
      case "documents":
        return <Documents />;
      case "projects":
        return <Projects />;
      case "upload":
        return <UploadView {...viewProps} />;
      case "viewer":
        return <ViewerView {...viewProps} />;
      case "workflow":
        return <Workflows />;
      case "apps":
        return <AppsView {...viewProps} />;
      case "editor":
        return <EditorSyncView {...viewProps} />;
      case "security":
        return <SecurityView {...viewProps} />;
      case "audit":
        return <AuditLogs />;
      case "m365":
        return <M365View {...viewProps} />;
      case "privacy":
        return <PrivacyView {...viewProps} />;
      case "users":
        return <Users />;
      case "settings":
        return <SettingsPage />;
      default:
        return null;
    }
  }

  return (
    <div className="ep-root" data-density={density}>
      {/* ── Topbar ── */}
      <header className="ep-topbar">
        {/* Row 1: brand + nav groups */}
        <div className="ep-topbar-row ep-topbar-primary">
          <div
            className="ep-brand"
            onClick={() => setCurrentView("lp")}
            style={{ cursor: "pointer" }}
          >
            <span className="ep-brand-icon">⬡</span>
            <span className="ep-brand-name">CivilPDF·DX</span>
            <span className="ep-brand-badge">v0.4.2 · Enterprise</span>
          </div>
          <nav className="ep-nav-groups">
            {NAV_GROUPS.map((group) => (
              <div key={group.label} className="ep-nav-group">
                <span className="ep-nav-group-label">{group.label}</span>
                {group.items.map((item) => {
                  const badgeCount =
                    item.id === "workflow" ? (pendingApprovals ?? 0) : 0;
                  return (
                    <button
                      key={item.id}
                      className={`ep-nav-item${currentView === item.id ? " active" : ""}`}
                      onClick={() => navigate(item.id)}
                      // The badge would otherwise join the accessible name as
                      // "ワークフロー7"; expose the count as words instead.
                      aria-label={
                        badgeCount > 0
                          ? `${item.label}（承認待ち ${badgeCount} 件）`
                          : undefined
                      }
                    >
                      {item.label}
                      {badgeCount > 0 && (
                        <span className="ep-nav-badge" aria-hidden="true">
                          {badgeCount}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
        </div>

        {/* Row 2: util bar */}
        <div className="ep-topbar-row ep-topbar-util">
          <button
            className="ep-search-trigger"
            onClick={() => {
              setShowPalette(true);
              setPaletteQuery("");
            }}
          >
            <span className="ep-search-icon">⌕</span>
            <span className="ep-search-placeholder">検索… ⌘K</span>
          </button>

          {/* Role selector — auto-selected from logged-in user */}
          <select
            className="ep-role-select"
            value={role}
            onChange={(e) => {
              setRole(e.target.value as Role);
              showToast(
                `表示ロール: ${ROLE_LABELS[e.target.value as Role]}`,
                "ok",
              );
            }}
          >
            {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>

          {/* Notification bell */}
          <div className="ep-notif-wrapper" ref={notifRef}>
            <button
              className="ep-icon-btn"
              onClick={() => setShowNotif((v) => !v)}
              aria-label="通知"
            >
              🔔
              {unreadCount > 0 && (
                <span className="ep-notif-dot">{unreadCount}</span>
              )}
            </button>
            {showNotif && (
              <div className="ep-notif-dropdown">
                <div className="ep-notif-header">
                  <span>
                    通知{" "}
                    {unreadCount > 0 && (
                      <span className="ep-notif-count-badge">
                        {unreadCount}件未読
                      </span>
                    )}
                  </span>
                  {notifications.length > 0 && (
                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        className="ep-notif-mark-all"
                        onClick={markAllRead}
                      >
                        全既読
                      </button>
                      <button className="ep-notif-mark-all" onClick={clearAll}>
                        クリア
                      </button>
                    </div>
                  )}
                </div>
                {notifications.length === 0 ? (
                  <div
                    style={{
                      padding: "24px 16px",
                      textAlign: "center",
                      color: "var(--muted)",
                      fontSize: "12px",
                    }}
                  >
                    通知はありません
                  </div>
                ) : (
                  notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`ep-notif-item${n.is_read ? " read" : ""}${
                        n.resource_type ? " clickable" : ""
                      }`}
                      onClick={() => handleNotifClick(n)}
                      title={n.resource_type ? "クリックして移動" : undefined}
                    >
                      <span
                        className="ep-notif-dot-inline"
                        style={{ opacity: n.is_read ? 0 : 1 }}
                      />
                      <div style={{ flex: 1 }}>
                        <p className="ep-notif-text">{n.title}</p>
                        {n.body && <p className="ep-notif-time">{n.body}</p>}
                        <p className="ep-notif-time">
                          {n.created_at
                            ? new Date(n.created_at).toLocaleString("ja-JP")
                            : ""}
                        </p>
                      </div>
                      {n.resource_type && !n.is_read && (
                        <span className="ep-notif-arrow">›</span>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          <div className="ep-tweaks-wrapper" ref={tweaksRef}>
            <button
              className="ep-icon-btn"
              onClick={() => setShowTweaks((v) => !v)}
              aria-label="設定"
            >
              ⚙
            </button>
            {showTweaks && (
              <div className="ep-tweaks-panel">
                <p className="ep-tweaks-title">Tweaks</p>

                <div className="ep-tweaks-row">
                  <span>ダークモード</span>
                  <button
                    className={`ep-toggle${darkMode ? " on" : ""}`}
                    onClick={() => setDarkMode((v) => !v)}
                  />
                </div>

                <div className="ep-tweaks-row ep-tweaks-col">
                  <span>アクセントカラー</span>
                  <div className="ep-accent-swatches">
                    {[255, 145, 350, 280].map((hue) => (
                      <button
                        key={hue}
                        className={`ep-swatch${accentHue === hue ? " active" : ""}`}
                        style={{ background: `oklch(58% 0.18 ${hue})` }}
                        onClick={() => setAccentHue(hue)}
                      />
                    ))}
                  </div>
                </div>

                <div className="ep-tweaks-row ep-tweaks-col">
                  <span>密度</span>
                  <div className="ep-density-btns">
                    {(["compact", "default", "spacious"] as const).map((d) => (
                      <button
                        key={d}
                        className={`ep-density-btn${density === d ? " active" : ""}`}
                        onClick={() => setDensity(d)}
                      >
                        {d === "compact"
                          ? "狭"
                          : d === "default"
                            ? "標準"
                            : "広"}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="ep-tweaks-row ep-tweaks-col">
                  <span>サイドバー幅 {sidebarWidth}px</span>
                  <input
                    type="range"
                    min={160}
                    max={320}
                    value={sidebarWidth}
                    onChange={(e) => setSidebarWidth(Number(e.target.value))}
                    className="ep-slider"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Profile avatar + dropdown */}
          <div className="ep-profile-wrapper" ref={profileRef}>
            <button
              className="ep-avatar"
              onClick={() => setShowProfile((v) => !v)}
              aria-label="プロフィール"
              title={profileData.full_name}
            >
              {avatarInitial}
            </button>
            {showProfile && (
              <div className="ep-profile-dropdown">
                {/* Header: avatar + name + email */}
                <div className="ep-profile-header">
                  <div className="ep-profile-avatar-lg">{avatarInitial}</div>
                  <div className="ep-profile-header-text">
                    <p className="ep-profile-name">{profileData.full_name}</p>
                    <p className="ep-profile-email">{profileData.email}</p>
                  </div>
                </div>

                <div className="ep-profile-divider" />

                {/* Info rows */}
                <div className="ep-profile-info-section">
                  <div className="ep-profile-info-row">
                    <span className="ep-profile-info-key">ロール</span>
                    <span
                      className="ep-profile-role-badge"
                      data-role={profileData.role}
                    >
                      {ROLE_BADGE_LABELS[profileData.role]}
                    </span>
                  </div>
                  <div className="ep-profile-info-row">
                    <span className="ep-profile-info-key">ステータス</span>
                    <span
                      className={`ep-user-status ep-user-status-${profileData.status}`}
                    >
                      {profileData.status === "active"
                        ? "有効"
                        : profileData.status === "inactive"
                          ? "無効"
                          : "停止中"}
                    </span>
                  </div>
                  <div className="ep-profile-info-row">
                    <span className="ep-profile-info-key">最終ログイン</span>
                    <span className="ep-profile-info-val">
                      {profileData.last_login
                        ? new Date(profileData.last_login).toLocaleDateString(
                            "ja-JP",
                          )
                        : "—"}
                    </span>
                  </div>
                  {profileData.created_at && (
                    <div className="ep-profile-info-row">
                      <span className="ep-profile-info-key">登録日</span>
                      <span className="ep-profile-info-val">
                        {new Date(profileData.created_at).toLocaleDateString(
                          "ja-JP",
                        )}
                      </span>
                    </div>
                  )}
                </div>

                <div className="ep-profile-divider" />

                {/* Note about editing */}
                <p className="ep-profile-edit-note">
                  プロフィールの編集はユーザー管理から行えます
                </p>

                {/* Action buttons */}
                <div className="ep-profile-actions">
                  <button
                    className="ep-profile-action-btn"
                    onClick={() => {
                      setShowProfile(false);
                      navigate("settings");
                    }}
                  >
                    ✏️ ユーザー管理で編集
                  </button>
                  <button
                    className="ep-profile-action-btn ep-profile-action-logout"
                    onClick={handleLogout}
                  >
                    🚪 ログアウト
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── Main content area ── */}
      <main className="ep-main">{renderView()}</main>

      {/* ── Command palette ── */}
      {showPalette && (
        <div
          className="ep-palette-backdrop"
          onClick={() => setShowPalette(false)}
        >
          <div className="ep-palette" onClick={(e) => e.stopPropagation()}>
            <input
              ref={paletteInputRef}
              className="ep-palette-input"
              placeholder="ビュー・機能を検索…"
              value={paletteQuery}
              onChange={(e) => {
                setPaletteQuery(e.target.value);
                setPaletteCursor(0);
              }}
              onKeyDown={handlePaletteKeyDown}
            />
            <ul className="ep-palette-list">
              {paletteResults.map((item, idx) => (
                <li
                  key={item.view}
                  className={`ep-palette-item${idx === paletteCursor ? " active" : ""}`}
                  onMouseEnter={() => setPaletteCursor(idx)}
                  onClick={() => {
                    setShowPalette(false);
                    navigate(item.view);
                  }}
                >
                  <span className="ep-palette-icon">{item.icon}</span>
                  <div>
                    <p className="ep-palette-label">{item.label}</p>
                    <p className="ep-palette-desc">{item.desc}</p>
                  </div>
                </li>
              ))}
              {paletteResults.length === 0 && (
                <li className="ep-palette-empty">結果なし</li>
              )}
            </ul>
          </div>
        </div>
      )}

      {/* ── Detail modal ── */}
      {modal && (
        <div className="ep-modal-backdrop" onClick={() => setModal(null)}>
          <div className="ep-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ep-modal-header">
              <h2 className="ep-modal-title">{modal.title}</h2>
              <button className="ep-modal-close" onClick={() => setModal(null)}>
                ✕
              </button>
            </div>
            <ModalBody text={modal.body} />
            <div className="ep-modal-footer">
              <button
                className="ep-btn ep-btn-primary"
                onClick={() => setModal(null)}
              >
                閉じる
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast stack ── */}
      <div className="ep-toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`ep-toast ep-toast-${t.type}`}>
            <span>{t.type === "ok" ? "✓" : t.type === "warn" ? "⚠" : "✕"}</span>
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
};
