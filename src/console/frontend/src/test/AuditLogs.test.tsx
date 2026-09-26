import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { AuditLogs } from "../pages/AuditLogs";

vi.mock("../api/auditLogs", () => ({
  listAuditLogs: vi.fn(),
}));

import { listAuditLogs } from "../api/auditLogs";

const mockLog = {
  id: "log-1",
  user_id: "user-1",
  action: "document.upload",
  resource_type: "document",
  resource_id: "doc-12345678",
  detail: null,
  ip_address: "192.168.1.1",
  created_at: "2026-05-11T00:00:00Z",
  user: {
    id: "user-1",
    email: "admin@example.com",
    username: "admin",
    full_name: "管理者",
    role: "admin",
  },
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

describe("AuditLogs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    vi.mocked(listAuditLogs).mockImplementation(() => new Promise(() => {}));
    render(<AuditLogs />, { wrapper });
    expect(screen.getByText("読み込み中...")).toBeInTheDocument();
  });

  it("displays audit log entries", async () => {
    vi.mocked(listAuditLogs).mockResolvedValueOnce({
      items: [mockLog],
      total: 1,
      page: 1,
      per_page: 50,
      pages: 1,
    });

    render(<AuditLogs />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("管理者")).toBeInTheDocument();
    });
    // action badge and option elements share text, use getAllByText
    expect(screen.getAllByText("アップロード").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getAllByText("文書").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("192.168.1.1")).toBeInTheDocument();
  });

  it("shows empty state when no logs", async () => {
    vi.mocked(listAuditLogs).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      per_page: 50,
      pages: 0,
    });

    render(<AuditLogs />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("ログがありません")).toBeInTheDocument();
    });
  });

  it("shows total count", async () => {
    vi.mocked(listAuditLogs).mockResolvedValueOnce({
      items: [mockLog],
      total: 42,
      page: 1,
      per_page: 50,
      pages: 1,
    });

    render(<AuditLogs />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("合計 42 件")).toBeInTheDocument();
    });
  });

  it("filters by action", async () => {
    vi.mocked(listAuditLogs).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 50,
      pages: 0,
    });
    const user = userEvent.setup();

    render(<AuditLogs />, { wrapper });

    const select = screen.getByDisplayValue("すべてのアクション");
    await user.selectOptions(select, "document.upload");

    await waitFor(() => {
      expect(vi.mocked(listAuditLogs)).toHaveBeenCalledWith(
        expect.objectContaining({ action: "document.upload", page: 1 }),
      );
    });
  });

  it("shows pagination controls for multiple pages", async () => {
    vi.mocked(listAuditLogs).mockResolvedValueOnce({
      items: [mockLog],
      total: 100,
      page: 1,
      per_page: 50,
      pages: 2,
    });

    render(<AuditLogs />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("前へ")).toBeInTheDocument();
      expect(screen.getByText("次へ")).toBeInTheDocument();
      expect(screen.getByText("1 / 2")).toBeInTheDocument();
    });
  });
});
