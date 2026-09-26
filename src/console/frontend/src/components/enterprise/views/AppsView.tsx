import { type FC, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getAppsReleases,
  getDownloadUrl,
  getReleaseNotes,
  getBuildInfo,
  type ReleasePackage,
  type ChannelInfo,
  type PendingPlatform,
} from "../../../api/apps";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

interface ToggleItem {
  id: string;
  label: string;
  sub: string;
}

interface DeployTarget {
  id: string;
  name: string;
  meta: string;
  progress: number;
  count: string;
  status: string;
  modalBody: string;
}

const CHANNEL_STATIC_INFO: Record<string, string> = {
  stable: "対象: 全ユーザー（デフォルト）\n更新頻度: 随時",
};

const buildChannelModalBody = (ch: ChannelInfo): string => {
  const staticInfo = CHANNEL_STATIC_INFO[ch.id];
  return [
    `${ch.label} チャンネル`,
    `バージョン: ${ch.version}\nリリース日: ${ch.release_date}`,
    ...(staticInfo ? [staticInfo] : []),
    ch.description,
    `参加ユーザー数: ${ch.user_count}`,
  ].join("\n\n");
};

const CHANNEL_PILL: Record<string, string> = {
  stable: "ep-pill ep-pill-stable",
};

// リリースごとに変わらない静的補足（対応 OS・要件・導入手順の型）。
// バージョン・ファイル名・サイズは API (ReleasePackage) から動的に組み立てる。
// 配布は Windows のみ（macOS は API の pending_platforms で「後日対応」表示）。
const DL_STATIC_BODY: Record<string, (filename: string) => string> = {
  "win-exe": () =>
    "対応OS: Windows 10 / 11 (64bit)\n必要要件: WebView2（Windows 11 は標準搭載）\n\n用途: 個人 PC への対話型インストール\n注意: 未署名ビルドのため SmartScreen 警告が表示される場合があります",
  "win-msi": (filename) =>
    `対応OS: Windows 10 / 11 (64bit)\n必要要件: WebView2（Windows 11 は標準搭載）\n\n用途: グループポリシー (GPO) / SCCM / Intune によるサイレント一括展開向け\nサイレントインストール例:\n  msiexec /i ${filename} /qn /norestart`,
};

const buildDownloadModalBody = (pkg: ReleasePackage): string => {
  const staticBody = DL_STATIC_BODY[pkg.id];
  return [
    `PDF Editor Client — ${pkg.label}`,
    `バージョン: v${pkg.version} (Stable)\nファイル: ${pkg.filename}\nサイズ: ${pkg.size_label}`,
    ...(staticBody ? [staticBody(pkg.filename)] : []),
  ].join("\n\n");
};

const buildPendingModalBody = (p: PendingPlatform): string =>
  `${p.label} 版 PDF Editor Client\n\nステータス: 後日対応（ペンディング）\n${p.note}`;

const PLATFORM_LABEL: Record<string, string> = {
  windows: "Windows",
};

const TOGGLES: ToggleItem[] = [
  {
    id: "autoUpdate",
    label: "自動アップデート",
    sub: "バックグラウンドで最新版を自動適用",
  },
  {
    id: "forceMin",
    label: "最低バージョン強制",
    sub: "最低サポート版（ビルド情報で確認）未満をブロック（表示のみ・未実装）",
  },
  {
    id: "telemetry",
    label: "テレメトリー収集",
    sub: "クラッシュレポート・使用状況を収集（匿名）",
  },
];

const DEPLOY_TARGETS: DeployTarget[] = [
  {
    id: "DT-001",
    name: "本社ビル (東京)",
    meta: "Windows 11 · 98台",
    progress: 100,
    count: "98 / 98",
    status: "完了",
    modalBody:
      "本社ビル (東京)\n\n対象台数: 98台\nOS: Windows 11\nインストール方式: Intune\nステータス: 全台展開済み\n最終更新: 2026-04-29",
  },
  {
    id: "DT-002",
    name: "大阪支店",
    meta: "Windows 10/11 · 54台",
    progress: 96,
    count: "52 / 54",
    status: "展開中",
    modalBody:
      "大阪支店\n\n対象台数: 54台\nOS: Windows 10 / 11\nインストール方式: Intune\nステータス: 展開中 (52/54)\n残り2台: オフライン端末",
  },
  {
    id: "DT-003",
    name: "名古屋支店",
    meta: "Windows 10 · 31台",
    progress: 87,
    count: "27 / 31",
    status: "展開中",
    modalBody:
      "名古屋支店\n\n対象台数: 31台\nOS: Windows 10\nインストール方式: グループポリシー\nステータス: 展開中 (27/31)",
  },
  {
    id: "DT-004",
    name: "第3工区現場事務所",
    meta: "Windows 10 · 8台",
    progress: 75,
    count: "6 / 8",
    status: "展開中",
    modalBody:
      "第3工区現場事務所\n\n対象台数: 8台\nOS: Windows 10\nインストール方式: 手動（USB）\nステータス: 展開中 (6/8)\n残り2台: 次回訪問時に対応予定",
  },
  {
    id: "DT-005",
    name: "協力会社A (外部)",
    meta: "Windows 11 · 12台",
    progress: 100,
    count: "12 / 12",
    status: "完了",
    modalBody:
      "協力会社A (外部)\n\n対象台数: 12台\nOS: Windows 11\nインストール方式: 手動（インストーラー配布）\nステータス: 全台展開済み\n有効期限: 2026-08-31",
  },
  {
    id: "DT-006",
    name: "福岡支店",
    meta: "Windows 10/11 · 22台",
    progress: 0,
    count: "0 / 22",
    status: "未開始",
    modalBody:
      "福岡支店\n\n対象台数: 22台\nOS: Windows 10 / 11\nインストール方式: Intune（予定）\nステータス: 未開始\n予定日: 2026-05-20",
  },
];

export const AppsView: FC<ViewProps> = ({ onShowModal, onShowToast }) => {
  const [toggles, setToggles] = useState<Record<string, boolean>>({
    autoUpdate: true,
    forceMin: true,
    telemetry: false,
  });
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [buildInfoLoading, setBuildInfoLoading] = useState(false);
  const releaseNotesRef = useRef<HTMLDivElement | null>(null);

  const { data: releases, isLoading: releasesLoading } = useQuery({
    queryKey: ["apps", "releases"],
    queryFn: getAppsReleases,
  });

  const { data: releaseNotes, isLoading: notesLoading } = useQuery({
    queryKey: ["apps", "release-notes"],
    queryFn: () => getReleaseNotes(),
  });

  const handleDownload = async (pkg: ReleasePackage) => {
    if (!pkg.available) {
      onShowModal({
        title: `${PLATFORM_LABEL[pkg.platform] ?? pkg.platform} — ${pkg.label}`,
        body: `${buildDownloadModalBody(pkg)}\n\nダウンロードリンクは近日公開予定です。`,
      });
      return;
    }
    setDownloadingId(pkg.id);
    try {
      const res = await getDownloadUrl(pkg.id);
      if (!res.url) {
        onShowToast(
          res.message ?? "ダウンロードリンクは近日公開予定です",
          "warn",
        );
        return;
      }
      const a = document.createElement("a");
      a.href = res.url;
      a.download = pkg.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      onShowToast(`${pkg.label} のダウンロードを開始しました`, "ok");
    } catch {
      onShowToast("ダウンロードに失敗しました", "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const toggleSwitch = (id: string) => {
    const next = !toggles[id];
    setToggles((prev) => ({ ...prev, [id]: next }));
    const label = TOGGLES.find((t) => t.id === id)?.label ?? id;
    onShowToast(`${label}: ${next ? "ON" : "OFF"}`, next ? "ok" : "warn");
  };

  const handleShowBuildInfo = async () => {
    setBuildInfoLoading(true);
    try {
      const b = await getBuildInfo();
      const lines = [
        `製品: ${b.product}`,
        `安定版: ${b.stable_version}`,
        `ビルド番号: ${b.build_number}`,
        b.git_commit ? `コミット: ${b.git_commit}` : null,
        b.build_date ? `ビルド日: ${b.build_date}` : null,
        `チャンネル: ${b.channel}`,
        `ランタイム: ${b.runtime}`,
        `対応OS: ${b.supported_os.join(" / ")}`,
        `最低サポート版: v${b.min_supported_version}`,
      ].filter(Boolean);
      onShowModal({ title: "ビルド情報", body: lines.join("\n") });
    } catch {
      onShowToast("ビルド情報の取得に失敗しました", "error");
    } finally {
      setBuildInfoLoading(false);
    }
  };

  const scrollToReleaseNotes = () => {
    releaseNotesRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const notes = releaseNotes?.notes ?? [];

  // Demo targets carry no version of their own; show the distributed version.
  const targetModalBody = (dt: DeployTarget): string =>
    `${dt.modalBody}\n配布中バージョン: ${releases?.stable_version ?? "—"}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* App hero */}
      <div className="ep-app-hero">
        {/* App card */}
        <div className="ep-panel ep-app-card">
          <div className="ep-app-card-top">
            <div className="ep-app-icon">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div>
              <h3>
                PDF Editor Client
                <span className="ep-pill ep-pill-stable">
                  <span className="dot" />
                  Stable
                </span>
              </h3>
              <p>
                建設・土木業向け高機能PDFエディター。電子印鑑・OCR・大判図面対応。
              </p>
              <div className="ep-app-meta">
                <span>バージョン {releases?.stable_version ?? "—"}</span>
                <span>Windows 10 / 11（macOS は後日対応）</span>
              </div>
            </div>
          </div>
          {/* Download grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "7px",
              padding: "11px 16px",
              borderTop: "1px solid var(--border)",
            }}
          >
            {releasesLoading
              ? [0, 1, 2].map((i) => (
                  <div key={i} className="ep-dl-card" style={{ opacity: 0.4 }}>
                    <div className="os">—</div>
                    <div className="fmt">読み込み中...</div>
                    <div className="size">—</div>
                  </div>
                ))
              : (releases?.packages ?? []).map((pkg) => {
                  const isLoading = downloadingId === pkg.id;
                  return (
                    <div
                      key={pkg.id}
                      className="ep-dl-card"
                      onClick={() => handleDownload(pkg)}
                      role="button"
                      tabIndex={0}
                      style={{ opacity: isLoading ? 0.6 : 1 }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleDownload(pkg);
                        }
                      }}
                    >
                      <div className="os">
                        {PLATFORM_LABEL[pkg.platform] ?? pkg.platform}
                      </div>
                      <div className="fmt">{pkg.label}</div>
                      <div className="size">
                        {isLoading
                          ? "取得中..."
                          : pkg.available
                            ? pkg.size_label
                            : "準備中"}
                      </div>
                    </div>
                  );
                })}
            {!releasesLoading &&
              (releases?.pending_platforms ?? []).map((p) => (
                <div
                  key={p.platform}
                  className="ep-dl-card"
                  data-testid={`pending-${p.platform}`}
                  onClick={() =>
                    onShowModal({
                      title: `${p.label} — 後日対応`,
                      body: buildPendingModalBody(p),
                    })
                  }
                  role="button"
                  aria-label={`${p.label} 版は後日対応（詳細を表示）`}
                  tabIndex={0}
                  style={{ opacity: 0.55 }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onShowModal({
                        title: `${p.label} — 後日対応`,
                        body: buildPendingModalBody(p),
                      });
                    }
                  }}
                >
                  <div className="os">{p.label}</div>
                  <div className="fmt">後日対応（ペンディング）</div>
                  <div className="size">—</div>
                </div>
              ))}
          </div>
          <div className="ep-app-card-actions">
            <button
              className="ep-btn ep-btn-secondary ep-btn-sm"
              onClick={scrollToReleaseNotes}
            >
              リリースノート
            </button>
            <button
              className="ep-btn ep-btn-secondary ep-btn-sm"
              onClick={handleShowBuildInfo}
              disabled={buildInfoLoading}
            >
              {buildInfoLoading ? "取得中..." : "ビルド情報"}
            </button>
          </div>
        </div>

        {/* Channel grid + toggles */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div className="ep-channel-grid">
            {(releases?.channels ?? []).map((ch) => (
              <div
                key={ch.id}
                className={`ep-channel${ch.id === "stable" ? " active" : ""}`}
                onClick={() =>
                  onShowModal({
                    title: `${ch.label} チャンネル`,
                    body: buildChannelModalBody(ch),
                  })
                }
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onShowModal({
                      title: `${ch.label} チャンネル`,
                      body: buildChannelModalBody(ch),
                    });
                  }
                }}
              >
                <div className="ep-channel-head">
                  <h4>{ch.label}</h4>
                  <span
                    className={CHANNEL_PILL[ch.id] ?? "ep-pill ep-pill-muted"}
                  >
                    <span className="dot" />
                    {ch.label}
                  </span>
                </div>
                <div className="ver">{ch.version}</div>
                <p>{ch.description}</p>
                <div className="users">{ch.user_count} ユーザー</div>
              </div>
            ))}
          </div>

          {/* Toggles */}
          <div className="ep-panel">
            <div className="ep-panel-head">
              <h3>配布設定</h3>
            </div>
            <div className="ep-panel-body">
              {TOGGLES.map((t) => (
                <div
                  key={t.id}
                  className="ep-opt-row"
                  style={{ cursor: "pointer" }}
                  onClick={() => toggleSwitch(t.id)}
                >
                  <div className="lbl">
                    {t.label}
                    <small>{t.sub}</small>
                  </div>
                  <div
                    className={`ep-toggle${toggles[t.id] ? " on" : ""}`}
                    role="switch"
                    aria-checked={toggles[t.id]}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggleSwitch(t.id);
                      }
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Deployment targets (demo data — real MDM/Intune integration is a follow-up) */}
      <div className="ep-panel">
        <div className="ep-panel-head">
          <h3>
            展開対象
            <span
              className="ep-pill ep-pill-muted"
              style={{ marginLeft: "8px" }}
            >
              デモ
            </span>
          </h3>
          <span className="meta">6 グループ</span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "8px",
            padding: "12px",
          }}
        >
          {DEPLOY_TARGETS.map((dt) => (
            <div
              key={dt.id}
              className="ep-target"
              onClick={() =>
                onShowModal({ title: dt.name, body: targetModalBody(dt) })
              }
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onShowModal({ title: dt.name, body: targetModalBody(dt) });
                }
              }}
            >
              <h5>
                {dt.name}
                <span
                  className={`ep-pill ${
                    dt.status === "完了"
                      ? "ep-pill-ok"
                      : dt.status === "未開始"
                        ? "ep-pill-muted"
                        : "ep-pill-warn"
                  }`}
                >
                  {dt.status}
                </span>
              </h5>
              <div className="meta">{dt.meta}</div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "10.5px",
                  color: "var(--muted)",
                  marginTop: "4px",
                }}
              >
                <span>{dt.count} 台</span>
                <span>{dt.progress}%</span>
              </div>
              <div className="ep-progress-mini">
                <div style={{ width: `${dt.progress}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* KPI stats (demo data — real MDM/Intune integration is a follow-up) */}
      <div
        style={{
          fontSize: "11px",
          color: "var(--muted)",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span className="ep-pill ep-pill-muted">デモ</span>
        展開状況の数値は MDM 連携前のサンプル表示です
      </div>
      <div
        className="ep-stat-grid"
        style={{ gridTemplateColumns: "repeat(4, 1fr)", marginBottom: 0 }}
      >
        <div className="ep-stat">
          <div className="lbl">総展開台数</div>
          <div className="val">195</div>
          <div className="delta">/ 225 対象</div>
        </div>
        <div className="ep-stat">
          <div className="lbl">展開率</div>
          <div className="val">86.7%</div>
          <div className="delta up">+3.2%</div>
        </div>
        <div className="ep-stat">
          <div className="lbl">バージョン統一率</div>
          <div className="val">94.4%</div>
          <div className="delta up">{releases?.stable_version ?? "—"}</div>
        </div>
        <div className="ep-stat">
          <div className="lbl">旧バージョン数</div>
          <div className="val">11</div>
          <div className="delta down">旧版: 11台</div>
        </div>
      </div>

      {/* Release notes */}
      <div className="ep-panel" ref={releaseNotesRef}>
        <div className="ep-panel-head">
          <h3>リリースノート</h3>
        </div>
        <div>
          {notesLoading ? (
            <div className="ep-rn-item" style={{ opacity: 0.5 }}>
              <div className="ep-rn-body">
                <h5>読み込み中...</h5>
              </div>
            </div>
          ) : notes.length === 0 ? (
            <div className="ep-rn-item">
              <div className="ep-rn-body">
                <h5>該当するリリースノートはありません</h5>
              </div>
            </div>
          ) : (
            notes.map((rn) => {
              const body =
                rn.highlights ??
                `v${rn.version} — リリースノート\n\nリリース日: ${rn.release_date}\nチャンネル: Stable\n\n${rn.summary}`;
              return (
                <div
                  key={rn.version}
                  className="ep-rn-item"
                  style={{ cursor: "pointer" }}
                  onClick={() =>
                    onShowModal({
                      title: `リリースノート v${rn.version}`,
                      body,
                    })
                  }
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onShowModal({
                        title: `リリースノート v${rn.version}`,
                        body,
                      });
                    }
                  }}
                >
                  <div className="ep-rn-meta">
                    <div className="v">v{rn.version}</div>
                    <div className="d">{rn.release_date}</div>
                    <div style={{ marginTop: "4px" }}>
                      <span className="ep-pill ep-pill-stable">
                        <span className="dot" />
                        Stable
                      </span>
                    </div>
                  </div>
                  <div className="ep-rn-body">
                    <h5>{rn.summary}</h5>
                    <ul>
                      {rn.items.map((item, i) => (
                        <li key={i}>
                          <span
                            className={`ep-rn-tag ${item.type.toLowerCase()}`}
                          >
                            {item.type}
                          </span>
                          <span>{item.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
