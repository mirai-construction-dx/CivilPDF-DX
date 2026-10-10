// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
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
  resubmitWorkflow: vi.fn(),
}));

vi.mock("../api/documents", () => ({
  getDocument: vi.fn(),
}));

import {
  listWorkflows,
  getWorkflow,
  decideStep,
  resubmitWorkflow,
} from "../api/workflows";
import { getDocument, type DocumentResponse } from "../api/documents";
import type { UserResponse } from "../api/auth";

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

const mockReturnedDetail = {
  ...mockWorkflowDetail,
  status: "returned",
  completed_at: null,
  steps: [
    {
      ...mockStep,
      status: "returned",
      comment: "寸法不整合のため差戻します。",
      decided_at: "2026-05-02T00:00:00Z",
    },
  ],
};

/** 差戻し中でも後続ステップが pending のまま残っているケース。 */
const mockReturnedDetailWithPendingStep = {
  ...mockWorkflowDetail,
  status: "returned",
  completed_at: null,
  steps: [
    {
      ...mockStep,
      id: "step-1",
      order: 1,
      status: "returned",
      comment: "寸法不整合のため差戻します。",
      decided_at: "2026-05-02T00:00:00Z",
    },
    {
      ...mockStep,
      id: "step-2",
      order: 2,
      approver_id: "approver-1",
      status: "pending",
    },
  ],
};

function mockDocument(ownerId: string): DocumentResponse {
  return {
    id: "doc-1",
    title: "橋梁設計図",
    document_type: "drawing",
    status: "draft",
    filename: "DOC_PRJ-2026-001_001.pdf",
    file_size: 1024,
    page_count: 1,
    is_pdfa: false,
    tags: [],
    project_id: "p-001",
    owner_id: ownerId,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: null,
  };
}

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

function setCurrentUser(id: string, role: UserResponse["role"]) {
  useAuthStore.setState({
    user: {
      id,
      email: `${id}@example.com`,
      username: id,
      full_name: id,
      role,
      status: "active",
      created_at: "",
      last_login: null,
    },
    isAuthenticated: true,
  });
}

/** 一覧を描画して「詳細」を開き、操作に使う user を返す。 */
async function openDetailModal() {
  const user = userEvent.setup();
  render(<Workflows />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
  await user.click(screen.getByText("詳細"));
  await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
  return user;
}

describe("Workflows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // invalidateQueries 後の再取得で undefined を返さないための既定値。
    vi.mocked(listWorkflows).mockResolvedValue([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValue(mockWorkflowDetail);
    // 再申請の権限判定で使う文書取得の既定値（既定は他人所有）。
    vi.mocked(getDocument).mockResolvedValue(mockDocument("owner-1"));
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

  /* ---------- 差戻し（return） ---------- */

  it("shows 差戻し badge for returned workflow status", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([
      { ...mockWorkflow, status: "returned", pending_step_count: 0 },
    ]);

    render(<Workflows />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("差戻し")).toBeInTheDocument();
    });
  });

  it("shows 差戻し badge for returned step status in detail modal", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockReturnedDetail);

    await openDetailModal();

    await waitFor(() => {
      // workflow のバッジと step のバッジの 2 箇所
      expect(screen.getAllByText("差戻し").length).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows 差戻し button for own pending step without prior approval", async () => {
    setCurrentUser("approver-1", "manager");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);

    const user = await openDetailModal();
    await waitFor(() =>
      expect(screen.getByText("操作する")).toBeInTheDocument(),
    );
    await user.click(screen.getByText("操作する"));

    await waitFor(() => {
      expect(screen.getByText("承認")).toBeInTheDocument();
      expect(screen.getByText("却下")).toBeInTheDocument();
      expect(screen.getByText("差戻し")).toBeInTheDocument();
    });
  });

  it("sends return decision when 差戻し button is clicked", async () => {
    setCurrentUser("approver-1", "manager");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockWorkflowDetail);
    vi.mocked(decideStep).mockResolvedValueOnce(mockReturnedDetail);

    const user = await openDetailModal();
    await waitFor(() =>
      expect(screen.getByText("操作する")).toBeInTheDocument(),
    );
    await user.click(screen.getByText("操作する"));
    await waitFor(() => expect(screen.getByText("差戻し")).toBeInTheDocument());
    await user.click(screen.getByText("差戻し"));

    await waitFor(() => {
      expect(decideStep).toHaveBeenCalledWith(
        "wf-1",
        "step-1",
        "return",
        undefined,
      );
    });
  });

  it("does not show 差戻し button when a previous step was approved", async () => {
    setCurrentUser("approver-1", "manager");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce({
      ...mockWorkflowDetail,
      steps: [
        {
          ...mockStep,
          id: "step-0",
          order: 1,
          approver_id: "other-1",
          status: "approved",
          decided_at: "2026-05-02T00:00:00Z",
        },
        {
          ...mockStep,
          id: "step-1",
          order: 2,
          approver_id: "approver-1",
          status: "pending",
        },
      ],
    });

    const user = await openDetailModal();
    await waitFor(() =>
      expect(screen.getByText("操作する")).toBeInTheDocument(),
    );
    await user.click(screen.getByText("操作する"));

    await waitFor(() => {
      expect(screen.getByText("却下")).toBeInTheDocument();
    });
    expect(screen.queryByText("差戻し")).not.toBeInTheDocument();
  });

  /* ---------- 再申請（resubmit） ---------- */

  it("shows 再申請 button for admin when workflow is returned", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockReturnedDetail);

    await openDetailModal();

    await waitFor(() => {
      expect(screen.getByText("再申請")).toBeInTheDocument();
    });
  });

  it("shows 再申請 button for the document owner (non-admin)", async () => {
    setCurrentUser("user-99", "engineer");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockReturnedDetail);
    vi.mocked(getDocument).mockResolvedValueOnce(mockDocument("user-99"));

    await openDetailModal();

    await waitFor(() => {
      expect(screen.getByText("再申請")).toBeInTheDocument();
    });
  });

  it("hides 再申請 button for a non-owner non-admin user", async () => {
    setCurrentUser("user-99", "engineer");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockReturnedDetail);
    vi.mocked(getDocument).mockResolvedValueOnce(mockDocument("someone-else"));

    await openDetailModal();

    await waitFor(() => {
      expect(getDocument).toHaveBeenCalledWith("doc-1");
    });
    expect(screen.queryByText("再申請")).not.toBeInTheDocument();
  });

  it("resubmits the workflow when 再申請 button is clicked", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mockReturnedDetail);
    vi.mocked(resubmitWorkflow).mockResolvedValueOnce({
      ...mockReturnedDetail,
      status: "in_progress",
    });

    const user = await openDetailModal();
    await waitFor(() => expect(screen.getByText("再申請")).toBeInTheDocument());
    await user.click(screen.getByText("再申請"));

    await waitFor(() => {
      expect(resubmitWorkflow).toHaveBeenCalledWith("wf-1");
    });
  });

  /* ---------- 差戻し中のステップ操作抑止 ---------- */

  it("hides 操作する and decision buttons while the workflow is returned", async () => {
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(
      mockReturnedDetailWithPendingStep,
    );

    await openDetailModal();

    // admin なので再申請パネルは出る
    await waitFor(() => {
      expect(screen.getByText("再申請")).toBeInTheDocument();
    });
    expect(screen.queryByText("操作する")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "承認" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "却下" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "差戻し" }),
    ).not.toBeInTheDocument();
  });

  it("hides decision buttons while returned even for own pending step", async () => {
    setCurrentUser("approver-1", "manager");
    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(
      mockReturnedDetailWithPendingStep,
    );
    vi.mocked(getDocument).mockResolvedValueOnce(mockDocument("approver-1"));

    await openDetailModal();

    await waitFor(() => {
      expect(screen.getByText("再申請")).toBeInTheDocument();
    });
    // 自分の pending ステップがあっても returned 中は操作不可
    expect(screen.queryByText("操作する")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "承認" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "却下" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "差戻し" }),
    ).not.toBeInTheDocument();
  });

  it("hides decision buttons when the workflow becomes returned while the form is open", async () => {
    // 現在ユーザ（user-99 / admin）自身の pending ステップを持つ詳細
    const mineInProgress = {
      ...mockWorkflowDetail,
      steps: [
        {
          ...mockStep,
          id: "step-1",
          approver_id: "user-99",
          status: "pending",
        },
      ],
    };
    // フォーム展開中に他者が差戻した状態（再取得で返る想定）
    const mineReturned = { ...mineInProgress, status: "returned" };

    vi.mocked(listWorkflows).mockResolvedValueOnce([mockWorkflow]);
    vi.mocked(getWorkflow).mockResolvedValueOnce(mineInProgress);

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const user = userEvent.setup();

    render(<Workflows />, {
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={client}>
          <MemoryRouter>{children}</MemoryRouter>
        </QueryClientProvider>
      ),
    });

    await waitFor(() => expect(screen.getByText("詳細")).toBeInTheDocument());
    await user.click(screen.getByText("詳細"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    // フォームを展開する
    await waitFor(() =>
      expect(screen.getByText("操作する")).toBeInTheDocument(),
    );
    await user.click(screen.getByText("操作する"));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "差戻し" }),
      ).toBeInTheDocument(),
    );

    // 他者の差戻しを再現: 再取得すると returned になる
    vi.mocked(getWorkflow).mockResolvedValue(mineReturned);
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["workflow", "wf-1"] });
    });

    await waitFor(() => expect(screen.getByText("再申請")).toBeInTheDocument());
    // フォームは展開されたままだが、操作ボタンは残らない
    expect(
      screen.queryByRole("button", { name: "承認" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "却下" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "差戻し" }),
    ).not.toBeInTheDocument();
  });
});
