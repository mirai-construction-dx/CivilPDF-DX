// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Dashboard } from "../pages/Dashboard";
import { useAuthStore } from "../store/auth";

vi.mock("../api/stats", () => ({ getStats: vi.fn() }));
vi.mock("../api/documents", () => ({ listDocuments: vi.fn() }));

import { getStats } from "../api/stats";
import { listDocuments } from "../api/documents";

const mockUser = {
  id: "user-1",
  email: "admin@example.com",
  username: "admin",
  full_name: "管理者",
  role: "admin" as const,
  status: "active" as const,
  created_at: "2026-01-01T00:00:00Z",
  last_login: null,
};

const mockStats = {
  total_documents: 42,
  pending_approvals: 5,
  active_users: 10,
  approved_this_month: 8,
  uploaded_this_week: 3,
  total_file_size_bytes: 1048576,
  by_type: { drawing: 20, specification: 15, report: 7 },
  by_status: { approved: 30, pending_review: 5, draft: 7 },
};

const mockDoc = {
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

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockUser, isAuthenticated: true });
  });

  it("shows user greeting", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText(/ようこそ、管理者 さん/)).toBeInTheDocument();
    });
  });

  it("shows KPI stat cards with values from stats API", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });
    expect(screen.getByText("ドキュメント")).toBeInTheDocument();
    expect(screen.getByText("承認待ち")).toBeInTheDocument();
    expect(screen.getByText("今月承認済")).toBeInTheDocument();
    expect(screen.getByText("アクティブユーザー")).toBeInTheDocument();
    expect(screen.getAllByText("5").length).toBeGreaterThanOrEqual(1);
  });

  it("shows type distribution panel", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("種別分布")).toBeInTheDocument();
      expect(screen.getByText("図面")).toBeInTheDocument();
    });
  });

  it("shows status distribution panel", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("ステータス分布")).toBeInTheDocument();
    });
  });

  it("shows empty state when no documents", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("ドキュメントがありません")).toBeInTheDocument();
    });
  });

  it("shows recent documents list (up to 5)", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    const docs = Array.from({ length: 7 }, (_, i) => ({
      ...mockDoc,
      id: `doc-${i}`,
      title: `図面 ${i}`,
    }));
    vi.mocked(listDocuments).mockResolvedValueOnce(docs);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("図面 0")).toBeInTheDocument();
      expect(screen.getByText("図面 4")).toBeInTheDocument();
      expect(screen.queryByText("図面 5")).not.toBeInTheDocument();
    });
  });

  it("falls back to email when full_name is absent", async () => {
    useAuthStore.setState({
      user: { ...mockUser, full_name: "" },
      isAuthenticated: true,
    });
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText(/admin@example\.com さん/)).toBeInTheDocument();
    });
  });

  it("shows file size sub-label under active users card", async () => {
    vi.mocked(getStats).mockResolvedValueOnce(mockStats);
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
    });
  });
});
