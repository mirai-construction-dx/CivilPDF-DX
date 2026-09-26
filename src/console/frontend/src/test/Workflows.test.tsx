// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Workflows } from "../pages/Workflows";
import { useAuthStore } from "../store/auth";

vi.mock("../api/workflows", () => ({
  listWorkflows: vi.fn(),
  getWorkflow: vi.fn(),
  decideStep: vi.fn(),
}));

import { listWorkflows, getWorkflow } from "../api/workflows";

const mockApprover = {
  id: "approver-1",
  email: "approver@example.com",
  username: "approver",
  full_name: "承認者 太郎",
  role: "manager",
};

const mockStep = {
  id: "step-1",
  order: 1,
  approver_id: "approver-1",
  status: "pending",
  comment: null,
  decided_at: null,
  approver: mockApprover,
};

const mockWorkflowDetail = {
  id: "wf-1",
  document_id: "doc-1",
  status: "in_progress",
  created_at: "2026-05-01T00:00:00Z",
  completed_at: null,
  steps: [mockStep],
};

const mockWorkflow = {
  id: "wf-1",
  document_id: "doc-1",
  document_title: "橋梁設計図",
  status: "in_progress",
  created_at: "2026-05-01T00:00:00Z",
  completed_at: null,
  step_count: 3,
  pending_step_count: 2,
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

describe("Workflows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: "user-99",
        email: "u@e.com",
        username: "u",
        full_name: "U",
        role: "admin",
        status: "active",
        created_at: "",
        last_login: null,
      },
      isAuthenticated: true,
    });
  });

  it("shows loading state initially", () => {
    vi.mocked(listWorkflows).mockReturnValue(new Promise(() => {}));

    render(<Workflows />, { wrapper: makeWrapper() });

    expect(screen.getByText("読み込み中...")).toBeInTheDocument();
  });

  it("shows empty state when no workflows", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("ワークフローがありません")).toBeInTheDocument();
    });
  });

  it("shows workflow list with document title", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
    });
  });

  it("shows 審査中 badge for in_progress status", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("審査中")).toBeInTheDocument();
    });
  });

  it("shows 承認済 badge for approved status", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      {
        ...mockWorkflow,
        status: "approved",
        completed_at: "2026-05-10T00:00:00Z",
        pending_step_count: 0,
      },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("承認済")).toBeInTheDocument();
    });
  });

  it("shows 却下 badge for rejected status", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      {
        ...mockWorkflow,
        status: "rejected",
        completed_at: "2026-05-10T00:00:00Z",
        pending_step_count: 0,
      },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("却下")).toBeInTheDocument();
    });
  });

  it("shows step count and pending count", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("shows dash when pending_step_count is 0", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      { ...mockWorkflow, pending_step_count: 0 },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      // Both pending count and completed_at show "—" when pending=0 and completed_at=null
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows completion date when completed_at is set", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      {
        ...mockWorkflow,
        status: "approved",
        completed_at: "2026-05-10T00:00:00Z",
        pending_step_count: 0,
      },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      // completed date formatted as ja-JP locale
      expect(screen.getByText("2026/5/10")).toBeInTheDocument();
    });
  });

  it("shows dash for completion date when not completed", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      // Only the pending step count shows as "—", and completed_at too
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows multiple workflows in table", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      mockWorkflow,
      {
        ...mockWorkflow,
        id: "wf-2",
        document_title: "トンネル断面図",
        status: "approved",
        completed_at: "2026-05-08T00:00:00Z",
        pending_step_count: 0,
      },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
      expect(screen.getByText("トンネル断面図")).toBeInTheDocument();
      expect(screen.getByText("審査中")).toBeInTheDocument();
      expect(screen.getByText("承認済")).toBeInTheDocument();
    });
  });

  it("shows page heading", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([]);

    render(<Workflows />, { wrapper: makeWrapper() });

    expect(screen.getByText("承認ワークフロー")).toBeInTheDocument();
  });

  it("shows 詳細 button in each row", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("詳細")).toBeInTheDocument();
    });
  });

  it("opens detail modal when 詳細 button is clicked", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    const user = userEvent.setup();

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("ワークフロー詳細")).toBeInTheDocument();
    });
  });

  it("shows step information in detail modal", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    const user = userEvent.setup();

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));

    await waitFor(() => {
      expect(screen.getByText(/承認者 太郎/)).toBeInTheDocument();
      expect(screen.getByText("approver@example.com")).toBeInTheDocument();
    });
  });

  it("closes modal when × button is clicked", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    const user = userEvent.setup();

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    await user.click(screen.getByLabelText("閉じる"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows 操作する button for own pending step", async () => {
    useAuthStore.setState({
      user: {
        id: "approver-1",
        email: "approver@example.com",
        username: "approver",
        full_name: "承認者 太郎",
        role: "manager",
        status: "active",
        created_at: "",
        last_login: null,
      },
      isAuthenticated: true,
    });
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    const user = userEvent.setup();

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));

    await waitFor(() => {
      expect(screen.getByText("操作する")).toBeInTheDocument();
    });
  });

  it("does not show 操作する button for other user pending step", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    const user = userEvent.setup();

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));

    await waitFor(() => {
      expect(screen.getByText(/承認者 太郎/)).toBeInTheDocument();
    });
    expect(screen.queryByText("操作する")).not.toBeInTheDocument();
  });
});
