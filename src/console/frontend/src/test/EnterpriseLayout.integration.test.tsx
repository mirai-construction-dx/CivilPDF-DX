// @vitest-environment jsdom
//
// Integration test: verifies the functional, API-connected pages are reachable
// through the EnterpriseLayout shell. This guards against the regression where
// the shell rendered static-mockup views and Phase 8 features (electronic
// timestamp / electronic delivery) were unreachable in the running app.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { EnterpriseLayout } from "../components/enterprise/EnterpriseLayout";
import { useAuthStore } from "../store/auth";

vi.mock("../api/documents", () => ({
  listDocumentsPaginated: vi.fn(),
  listTrash: vi.fn().mockResolvedValue([]),
  restoreDocument: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  fetchDocumentBlob: vi.fn(),
  applyTimestamp: vi.fn().mockResolvedValue({ valid: true }),
  verifyTimestamp: vi.fn().mockResolvedValue({
    valid: true,
    message: "OK",
    file_hash: "abc123",
    verified_at: "2026-06-01T00:00:00Z",
  }),
}));
vi.mock("../api/projects", () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock("../api/electronicDelivery", () => ({
  deliveryErrorMessage: vi.fn().mockResolvedValue("ZIP 生成に失敗しました。"),
  checkDeliveryReadiness: vi.fn().mockResolvedValue({
    ready: true,
    document_count: 3,
    pdfa_compliant_count: 3,
    non_pdfa_documents: [],
    warnings: [],
  }),
  downloadDeliveryZip: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("../api/stats", () => ({
  getStats: vi.fn().mockResolvedValue({ pending_approvals: 4 }),
}));
vi.mock("../api/ai", () => ({ classifyDocument: vi.fn() }));
vi.mock("../api/search", () => ({ searchDocuments: vi.fn() }));
vi.mock("../api/notifications", () => ({
  listNotifications: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    per_page: 20,
    pages: 0,
  }),
  unreadCount: vi.fn().mockResolvedValue(0),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
}));

import {
  listDocumentsPaginated,
  type DocumentResponse,
} from "../api/documents";
import { listProjects } from "../api/projects";

function pageOf(docs: DocumentResponse[]) {
  return {
    items: docs,
    total: docs.length,
    page: 1,
    per_page: 20,
    pages: Math.max(1, Math.ceil(docs.length / 20)),
  };
}

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

const mockDocDrawing = {
  id: "doc-1",
  title: "橋梁設計図",
  document_type: "drawing",
  status: "approved",
  filename: "bridge.pdf",
  file_size: 102400,
  page_count: 10,
  is_pdfa: true,
  tags: [],
  project_id: "proj-1",
  owner_id: "user-1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: null,
};

const mockDocReport = {
  ...mockDocDrawing,
  id: "doc-2",
  title: "工事報告書",
  document_type: "report",
};

const mockProject = {
  id: "proj-1",
  name: "道路改良工事",
  code: "RD-001",
  description: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

function renderShell() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <EnterpriseLayout />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EnterpriseLayout — functional page integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
  });

  it("navigates to 図書管理 and renders the real Documents page", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(
      pageOf([mockDocDrawing]),
    );
    vi.mocked(listProjects).mockResolvedValue([mockProject]);
    const user = userEvent.setup();

    renderShell();
    await user.click(screen.getByRole("button", { name: "図書管理" }));

    // Real (API-connected) Documents page — has the upload action and the row
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "+ アップロード" }),
      ).toBeInTheDocument();
    });
    expect(await screen.findByText("橋梁設計図")).toBeInTheDocument();
  });

  it("opens the electronic timestamp modal (Phase 8) from the documents view", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(
      pageOf([mockDocDrawing]),
    );
    vi.mocked(listProjects).mockResolvedValue([mockProject]);
    const user = userEvent.setup();

    renderShell();
    await user.click(screen.getByRole("button", { name: "図書管理" }));
    await screen.findByText("橋梁設計図");

    await user.click(screen.getByTitle(/電子タイムスタンプ/));

    expect(
      await screen.findByText("🔏 電子タイムスタンプ"),
    ).toBeInTheDocument();
  });

  it("filters documents by title from the documents view", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(
      pageOf([mockDocDrawing, mockDocReport]),
    );
    vi.mocked(listProjects).mockResolvedValue([mockProject]);
    const user = userEvent.setup();

    renderShell();
    await user.click(screen.getByRole("button", { name: "図書管理" }));
    await screen.findByText("橋梁設計図");
    expect(screen.getByText("工事報告書")).toBeInTheDocument();

    await user.type(screen.getByLabelText("タイトルで検索"), "橋梁");

    expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
    expect(screen.queryByText("工事報告書")).not.toBeInTheDocument();
  });

  it("navigates to プロジェクト and opens the electronic delivery modal (Phase 8)", async () => {
    vi.mocked(listProjects).mockResolvedValue([mockProject]);
    const user = userEvent.setup();

    renderShell();
    await user.click(screen.getByRole("button", { name: "プロジェクト" }));

    // Real Projects page with admin RBAC → 電子納品 button reachable
    const deliveryBtn = await screen.findByRole("button", { name: /電子納品/ });
    await user.click(deliveryBtn);

    expect(
      await screen.findByText("📦 電子納品パッケージ生成"),
    ).toBeInTheDocument();
  });

  it("renders the documents table within the shell main region", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(
      pageOf([mockDocDrawing]),
    );
    vi.mocked(listProjects).mockResolvedValue([mockProject]);
    const user = userEvent.setup();

    renderShell();
    await user.click(screen.getByRole("button", { name: "図書管理" }));

    const main = document.querySelector(".ep-main") as HTMLElement;
    expect(main).toBeTruthy();
    await waitFor(() => {
      expect(within(main).getByText("橋梁設計図")).toBeInTheDocument();
    });
  });

  it("shows the real pending-approval count, not a hardcoded badge", async () => {
    // Regression: the workflow nav badge used to be a literal "7", so every user
    // saw a fake pending-approval count regardless of the underlying data.
    vi.mocked(listDocumentsPaginated).mockResolvedValue(pageOf([]));
    vi.mocked(listProjects).mockResolvedValue([]);

    renderShell();

    const workflow = await screen.findByRole("button", {
      name: /ワークフロー/,
    });
    await waitFor(() => {
      expect(within(workflow).getByText("4")).toBeInTheDocument();
    });
    // The count is announced as words instead of being glued to the label.
    expect(workflow).toHaveAttribute(
      "aria-label",
      expect.stringContaining("承認待ち 4 件"),
    );
  });
});
