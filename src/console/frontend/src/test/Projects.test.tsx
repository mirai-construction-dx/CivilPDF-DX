// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Projects } from "../pages/Projects";
import { useAuthStore } from "../store/auth";

vi.mock("../api/projects", () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
}));

vi.mock("../api/electronicDelivery", () => ({
  deliveryErrorMessage: vi.fn().mockResolvedValue("ZIP 生成に失敗しました。"),
  checkDeliveryReadiness: vi.fn().mockResolvedValue({
    ready: true,
    document_count: 2,
    pdfa_compliant_count: 2,
    non_pdfa_documents: [],
    warnings: [],
  }),
  downloadDeliveryZip: vi.fn().mockResolvedValue(undefined),
}));

import { listProjects, deleteProject } from "../api/projects";

const mockAdmin = {
  id: "admin-1",
  email: "admin@example.com",
  username: "admin",
  full_name: "管理者",
  role: "admin" as const,
  status: "active" as const,
  created_at: "2026-01-01T00:00:00Z",
  last_login: null,
};

const mockViewer = {
  ...mockAdmin,
  id: "viewer-1",
  role: "viewer" as const,
  email: "viewer@example.com",
  full_name: "閲覧ユーザー",
};

const mockProjectA = {
  id: "proj-1",
  name: "道路改良工事",
  code: "RD-001",
  description: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const mockProjectB = {
  id: "proj-2",
  name: "橋梁設計",
  code: "BR-002",
  description: "橋梁の詳細設計",
  is_active: false,
  created_at: "2026-02-01T00:00:00Z",
};

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Projects", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
  });

  it("shows loading state initially", () => {
    vi.mocked(listProjects).mockReturnValue(new Promise(() => {}));

    render(<Projects />, { wrapper: makeWrapper() });

    expect(screen.getByText("読み込み中...")).toBeInTheDocument();
  });

  it("shows empty state when no projects exist", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("プロジェクトがありません")).toBeInTheDocument();
    });
  });

  it("displays project list with name, code and active/inactive badges", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA, mockProjectB]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
      expect(screen.getByText("橋梁設計")).toBeInTheDocument();
    });
    expect(screen.getByText("RD-001")).toBeInTheDocument();
    expect(screen.getByText("BR-002")).toBeInTheDocument();
    expect(screen.getByText("有効")).toBeInTheDocument();
    expect(screen.getByText("無効")).toBeInTheDocument();
  });

  it("search filter shows only matching projects", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA, mockProjectB]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("プロジェクト名で検索"), "道路");

    expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    expect(screen.queryByText("橋梁設計")).not.toBeInTheDocument();
  });

  it("search filter with no match shows no-match message", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() =>
      expect(screen.getByText("道路改良工事")).toBeInTheDocument(),
    );
    await user.type(
      screen.getByLabelText("プロジェクト名で検索"),
      "zzznomatch",
    );

    expect(
      screen.getByText("条件に一致するプロジェクトがありません"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("プロジェクトがありません"),
    ).not.toBeInTheDocument();
  });

  it('admin sees "+ 新規作成" button', async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.queryByText("読み込み中...")).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: "+ 新規作成" }),
    ).toBeInTheDocument();
  });

  it('viewer does not see "+ 新規作成" button', async () => {
    useAuthStore.setState({ user: mockViewer, isAuthenticated: true });
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.queryByText("読み込み中...")).not.toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "+ 新規作成" }),
    ).not.toBeInTheDocument();
  });

  it("admin sees delete buttons for each project", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA, mockProjectB]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    });
    const deleteButtons = screen.getAllByRole("button", { name: "削除" });
    expect(deleteButtons).toHaveLength(2);
  });

  it("viewer does not see delete buttons", async () => {
    useAuthStore.setState({ user: mockViewer, isAuthenticated: true });
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "削除" }),
    ).not.toBeInTheDocument();
  });

  it("calls deleteProject after confirmation is clicked", async () => {
    vi.mocked(listProjects).mockResolvedValue([mockProjectA]);
    vi.mocked(deleteProject).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    const deleteBtn = await screen.findByRole("button", { name: "削除" });
    await user.click(deleteBtn);
    await user.click(screen.getByRole("button", { name: "削除する" }));

    await waitFor(() => {
      expect(vi.mocked(deleteProject).mock.calls[0]?.[0]).toBe("proj-1");
    });
  });

  it("does not delete when confirmation is cancelled", async () => {
    vi.mocked(listProjects).mockResolvedValue([mockProjectA]);
    vi.mocked(deleteProject).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    const deleteBtn = await screen.findByRole("button", { name: "削除" });
    await user.click(deleteBtn);
    expect(screen.getByText("削除しますか?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(deleteProject).not.toHaveBeenCalled();
  });

  it('shows creation form when "+ 新規作成" is clicked', async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "+ 新規作成" }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "+ 新規作成" }));

    expect(screen.getByText("プロジェクト作成")).toBeInTheDocument();
    expect(screen.getByLabelText("プロジェクト名")).toBeInTheDocument();
    expect(screen.getByLabelText("コード")).toBeInTheDocument();
  });

  it("hides creation form on cancel", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "+ 新規作成" }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "+ 新規作成" }));
    expect(screen.getByText("プロジェクト作成")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(screen.queryByText("プロジェクト作成")).not.toBeInTheDocument();
  });

  it("shows search bar always visible", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Projects />, { wrapper: makeWrapper() });

    expect(screen.getByLabelText("プロジェクト名で検索")).toBeInTheDocument();
  });

  it('admin sees "📦 電子納品" button for each project', async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA, mockProjectB]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    });
    const deliveryButtons = screen.getAllByRole("button", { name: /電子納品/ });
    expect(deliveryButtons).toHaveLength(2);
  });

  it('viewer does not see "📦 電子納品" button', async () => {
    useAuthStore.setState({ user: mockViewer, isAuthenticated: true });
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);

    render(<Projects />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("道路改良工事")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /電子納品/ }),
    ).not.toBeInTheDocument();
  });

  it('clicking "📦 電子納品" opens ElectronicDeliveryModal with project info', async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    const deliveryBtn = await screen.findByRole("button", { name: /電子納品/ });
    await user.click(deliveryBtn);

    await waitFor(() => {
      expect(screen.getByText("📦 電子納品パッケージ生成")).toBeInTheDocument();
    });
    // projectName appears both in table and modal — getAllByText is correct here
    expect(screen.getAllByText("道路改良工事").length).toBeGreaterThanOrEqual(
      2,
    );
  });

  it("ElectronicDeliveryModal shows readiness info", async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    const deliveryBtn = await screen.findByRole("button", { name: /電子納品/ });
    await user.click(deliveryBtn);

    await waitFor(() => {
      expect(
        screen.getByText("納品可能", { exact: false }),
      ).toBeInTheDocument();
    });
  });

  it('ElectronicDeliveryModal closes on "閉じる" click', async () => {
    vi.mocked(listProjects).mockResolvedValueOnce([mockProjectA]);
    const user = userEvent.setup();

    render(<Projects />, { wrapper: makeWrapper() });

    const deliveryBtn = await screen.findByRole("button", { name: /電子納品/ });
    await user.click(deliveryBtn);
    await waitFor(() => {
      expect(screen.getByText("📦 電子納品パッケージ生成")).toBeInTheDocument();
    });

    // modal has two "閉じる" buttons (× aria-label + text button) — click the text button
    const closeButtons = screen.getAllByRole("button", { name: "閉じる" });
    await user.click(closeButtons[closeButtons.length - 1]);
    expect(
      screen.queryByText("📦 電子納品パッケージ生成"),
    ).not.toBeInTheDocument();
  });
});
