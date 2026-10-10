// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { EditorSyncView } from "../components/enterprise/views/EditorSyncView";

vi.mock("../api/documents", () => ({ listDocuments: vi.fn() }));
vi.mock("../api/editor", () => ({
  getReviewSidecar: vi.fn(),
  getWorkflowStatus: vi.fn(),
  listRevisions: vi.fn(),
  flattenCheck: vi.fn(),
}));
vi.mock("../api/auditLogs", () => ({ listAuditLogs: vi.fn() }));
// EditorSyncView also mounts a DX-sync stats query. Without this mock the file
// issued a real HTTP request per test, which made these tests non-hermetic and
// pushed "loads the document list into the selector" to 865ms against the 1000ms
// waitFor budget when the whole suite ran in parallel — the source of its flaky
// failures.
vi.mock("../api/stats", () => ({ getDxSyncStats: vi.fn() }));

import { listDocuments } from "../api/documents";
import {
  getReviewSidecar,
  getWorkflowStatus,
  listRevisions,
  flattenCheck,
} from "../api/editor";
import { listAuditLogs } from "../api/auditLogs";
import { getDxSyncStats } from "../api/stats";

const dxStats = {
  total: 12,
  success: 12,
  error: 0,
  success_rate_total: 100,
  success_rate_30d: 100,
  recent_30d: { total: 3, success: 3, error: 0 },
  by_error_kind_30d: {},
  monthly: [],
};

const docs = [
  {
    id: "doc-1",
    title: "橋梁設計図",
    document_type: "drawing",
    status: "editor_reviewed",
    filename: "bridge.pdf",
    file_size: 2048,
    page_count: 5,
    is_pdfa: true,
    tags: [],
    project_id: "proj-1",
    owner_id: "user-1",
    created_at: "2026-06-22T00:00:00Z",
    updated_at: null,
  },
];

const sidecar = {
  review_sidecar: {
    schema: "civilpdf.review/v1",
    generator: "CivilPDF-Editor",
    stamps: [{ id: "s1" }, { id: "s2" }],
    annotations: [],
  },
  review_sidecar_imported_at: "2026-06-22T01:00:00Z",
};

const workflow = {
  status: "approved",
  updated_at: "2026-06-22T02:00:00Z",
  steps: [
    {
      approver_id: "user-2",
      order: 1,
      status: "approved",
      comment: null,
      decided_at: "2026-06-22T02:00:00Z",
    },
  ],
  editor_sync: { workflow_status: "approved" },
};

const revisions = [
  {
    id: "rev-1",
    document_id: "doc-1",
    version_number: 1,
    filename: "bridge_A.pdf",
    file_size: 2048,
    revision: "A",
    revision_note: "初版",
    is_from_editor: true,
    editor_session_id: "sess-1",
    created_at: "2026-06-22T03:00:00Z",
  },
];

const audit = {
  items: [
    {
      id: "audit-1",
      user_id: "user-1",
      action: "review_sidecar.imported",
      resource_type: "document",
      resource_id: "doc-1",
      detail: null,
      ip_address: null,
      created_at: "2026-06-22T01:00:00Z",
      user: {
        id: "user-1",
        email: "y@example.com",
        username: "yamada",
        full_name: "山田 直人",
        role: "manager",
      },
    },
  ],
  total: 1,
  page: 1,
  per_page: 100,
  pages: 1,
};

function makeProps(overrides = {}) {
  return {
    onNavigate: vi.fn(),
    onShowModal: vi.fn(),
    onShowToast: vi.fn(),
    ...overrides,
  };
}

function renderView(props = makeProps()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <EditorSyncView {...props} />
    </QueryClientProvider>,
  );
  return props;
}

describe("EditorSyncView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listDocuments).mockResolvedValue(docs as never);
    vi.mocked(getReviewSidecar).mockResolvedValue(sidecar as never);
    vi.mocked(getWorkflowStatus).mockResolvedValue(workflow as never);
    vi.mocked(listRevisions).mockResolvedValue(revisions as never);
    vi.mocked(listAuditLogs).mockResolvedValue(audit as never);
    vi.mocked(getDxSyncStats).mockResolvedValue(dxStats as never);
  });

  it("shows a placeholder until a document is selected", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByText(/ドキュメントを選択すると/)).toBeInTheDocument();
    });
    // Editor APIs are not called before a document is chosen.
    expect(getReviewSidecar).not.toHaveBeenCalled();
  });

  it("loads the document list into the selector", async () => {
    renderView();
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /橋梁設計図/ }),
      ).toBeInTheDocument();
    });
  });

  it("renders all editor panels after selecting a document", async () => {
    const user = userEvent.setup();
    renderView();
    await waitFor(() => screen.getByRole("option", { name: /橋梁設計図/ }));
    await user.selectOptions(screen.getByRole("combobox"), "doc-1");

    await waitFor(() => {
      expect(screen.getByText(/押印レビュー/)).toBeInTheDocument();
    });
    expect(screen.getByText(/改訂履歴/)).toBeInTheDocument();
    expect(screen.getByText(/監査タイムライン/)).toBeInTheDocument();
    // ReviewSidecar stamp count (2) is surfaced.
    expect(getReviewSidecar).toHaveBeenCalledWith("doc-1");
    // Editor-derived revision is shown.
    expect(screen.getByText("bridge_A.pdf")).toBeInTheDocument();
    // Audit event for the document is listed.
    expect(screen.getByText("review_sidecar.imported")).toBeInTheDocument();
  });

  it("triggers flatten-check when the finalize button is clicked", async () => {
    vi.mocked(flattenCheck).mockResolvedValue({
      is_flattened: true,
      flattened_hash: "deadbeef",
      status: "finalized",
    } as never);
    const user = userEvent.setup();
    const props = renderView();
    await waitFor(() => screen.getByRole("option", { name: /橋梁設計図/ }));
    await user.selectOptions(screen.getByRole("combobox"), "doc-1");
    await waitFor(() => screen.getByRole("button", { name: /確定保存/ }));
    await user.click(screen.getByRole("button", { name: /確定保存/ }));
    await waitFor(() => {
      expect(flattenCheck).toHaveBeenCalledWith("doc-1");
      expect(props.onShowToast).toHaveBeenCalled();
    });
  });
});
