// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { AppsView } from "../components/enterprise/views/AppsView";

vi.mock("../api/apps", () => ({
  getAppsReleases: vi.fn(),
  getReleaseNotes: vi.fn(),
  getBuildInfo: vi.fn(),
  getDownloadUrl: vi.fn(),
}));

import {
  getAppsReleases,
  getReleaseNotes,
  getBuildInfo,
  getDownloadUrl,
} from "../api/apps";

// Fixtures mirror the real CivilPDF-Editor v1.2.0 GitHub Release (Tauri v2,
// unsigned stable, only the "stable" channel exists). Distribution is
// Windows-only; macOS arrives via pending_platforms (後日対応).
const releases = {
  stable_version: "v1.2.0",
  packages: [
    {
      id: "win-exe",
      platform: "windows",
      format: "exe",
      label: "インストーラー (.exe / NSIS)",
      filename: "CivilPDF.Editor_1.2.0_x64-setup.exe",
      version: "1.2.0",
      size_label: "約 1.9 MB",
      sha256: null,
      download_path: "/api/v1/apps/download/win-exe",
      available: false,
    },
    {
      id: "win-msi",
      platform: "windows",
      format: "msi",
      label: "インストーラー (.msi)",
      filename: "CivilPDF.Editor_1.2.0_x64_en-US.msi",
      version: "1.2.0",
      size_label: "約 2.4 MB",
      sha256: null,
      download_path: "/api/v1/apps/download/win-msi",
      available: true,
    },
  ],
  pending_platforms: [
    {
      platform: "macos",
      label: "macOS",
      status: "pending" as const,
      note: "後日対応（ペンディング）。現在は Windows 版のみ提供しています",
    },
  ],
  channels: [
    {
      id: "stable",
      label: "Stable",
      version: "v1.2.0",
      release_date: "2026-06-22",
      description: "安定版",
      user_count: 0,
    },
  ],
};

const notes = {
  notes: [
    {
      version: "1.2.0",
      channel: "stable" as const,
      release_date: "2026-06-22",
      summary: "v1.2.0 安定版 — テキスト編集モードを追加",
      items: [
        { type: "FEAT" as const, text: "テキスト編集モード" },
        { type: "NOTE" as const, text: "未署名ビルド" },
      ],
      highlights: "v1.2.0 highlights",
    },
  ],
};

const buildInfo = {
  product: "CivilPDF Editor Client",
  stable_version: "v1.2.0",
  build_number: "1.2.0+build.1",
  git_commit: "abc1234",
  build_date: "2026-06-22",
  channel: "stable",
  runtime: "Tauri v2（システムの WebView を利用）",
  supported_os: ["Windows 10 / 11 (64bit)"],
  min_supported_version: "1.2.0",
};

function makeProps() {
  return {
    onNavigate: vi.fn(),
    onShowModal: vi.fn(),
    onShowToast: vi.fn(),
  };
}

function renderView(props = makeProps()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AppsView {...props} />
    </QueryClientProvider>,
  );
  return props;
}

describe("AppsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAppsReleases).mockResolvedValue(releases);
    vi.mocked(getReleaseNotes).mockResolvedValue(notes);
    vi.mocked(getBuildInfo).mockResolvedValue(buildInfo);
  });

  it("renders the Windows packages from the releases API", async () => {
    renderView();
    await waitFor(() => {
      expect(
        screen.getByText("インストーラー (.exe / NSIS)"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("インストーラー (.msi)")).toBeInTheDocument();
    // No macOS/Linux installers are offered.
    expect(screen.queryByText(/\.dmg|\.deb|AppImage|\.rpm/)).toBeNull();
  });

  it("shows macOS as pending and opens an explanatory modal", async () => {
    const user = userEvent.setup();
    const props = renderView();
    const card = await screen.findByTestId("pending-macos");
    expect(card).toHaveTextContent("後日対応（ペンディング）");
    await user.click(card);
    expect(props.onShowModal).toHaveBeenCalledWith(
      expect.objectContaining({ title: "macOS — 後日対応" }),
    );
    // Pending platforms have no package, so no download URL is requested.
    expect(getDownloadUrl).not.toHaveBeenCalled();
  });

  it("renders without pending_platforms (older backend)", async () => {
    const { pending_platforms: _omit, ...legacy } = releases;
    void _omit;
    vi.mocked(getAppsReleases).mockResolvedValue(legacy);
    renderView();
    await screen.findByText("インストーラー (.exe / NSIS)");
    expect(screen.queryByTestId("pending-macos")).toBeNull();
  });

  it("renders release notes from the API", async () => {
    renderView();
    await waitFor(() => {
      expect(
        screen.getByText("v1.2.0 安定版 — テキスト編集モードを追加"),
      ).toBeInTheDocument();
    });
  });

  it("loads build info into a modal", async () => {
    const user = userEvent.setup();
    const props = renderView();
    await waitFor(() => {
      expect(screen.getByText("ビルド情報")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "ビルド情報" }));
    await waitFor(() => {
      expect(getBuildInfo).toHaveBeenCalled();
      expect(props.onShowModal).toHaveBeenCalledWith(
        expect.objectContaining({ title: "ビルド情報" }),
      );
    });
  });

  it("shows a coming-soon modal when a package is not yet available", async () => {
    const user = userEvent.setup();
    const props = renderView();
    await waitFor(() => {
      expect(
        screen.getByText("インストーラー (.exe / NSIS)"),
      ).toBeInTheDocument();
    });
    // win-exe is available:false → clicking shows the coming-soon modal and
    // must NOT call the download URL endpoint.
    await user.click(screen.getByText("インストーラー (.exe / NSIS)"));
    expect(props.onShowModal).toHaveBeenCalled();
    expect(getDownloadUrl).not.toHaveBeenCalled();
    // Modal body must be built from API data (v1.2.0 fixtures), not hardcoded text.
    const dlBody = props.onShowModal.mock.calls.at(-1)?.[0]?.body ?? "";
    expect(dlBody).toContain("バージョン: v1.2.0");
    expect(dlBody).toContain("CivilPDF.Editor_1.2.0_x64-setup.exe");
    expect(dlBody).toContain("ダウンロードリンクは近日公開予定です");
  });

  it("builds the channel modal from API data (no hardcoded version)", async () => {
    const user = userEvent.setup();
    const props = renderView();
    await waitFor(() => {
      expect(screen.getByText("安定版")).toBeInTheDocument();
    });
    await user.click(screen.getByText("安定版"));
    expect(props.onShowModal).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Stable チャンネル" }),
    );
    const chBody = props.onShowModal.mock.calls.at(-1)?.[0]?.body ?? "";
    expect(chBody).toContain("バージョン: v1.2.0");
    expect(chBody).toContain("リリース日: 2026-06-22");
    expect(chBody).toContain("参加ユーザー数: 0");
  });

  it("shows no fabricated license count or hardcoded versions", async () => {
    renderView();
    await screen.findByText("インストーラー (.exe / NSIS)");
    expect(screen.queryByText(/ライセンス/)).toBeNull();
    expect(screen.queryByText(/v1\.1\.0/)).toBeNull();
    // KPI version delta follows the API (fixture: v1.2.0), not a literal.
    expect(screen.getAllByText("v1.2.0").length).toBeGreaterThanOrEqual(1);
  });

  it("appends the distributed version from the API to demo target modals", async () => {
    const user = userEvent.setup();
    const props = renderView();
    await screen.findByText("インストーラー (.exe / NSIS)");
    await user.click(screen.getByText("本社ビル (東京)"));
    const body = props.onShowModal.mock.calls.at(-1)?.[0]?.body ?? "";
    expect(body).toContain("配布中バージョン: v1.2.0");
    expect(body).not.toContain("v1.2.4");
  });

  it("marks deploy targets and KPI as demo data", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getAllByText("デモ").length).toBeGreaterThanOrEqual(2);
    });
  });
});
