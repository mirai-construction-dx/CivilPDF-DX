// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Documents } from "../pages/Documents";

vi.mock("../api/documents", () => ({
  listDocumentsPaginated: vi.fn(),
  listTrash: vi.fn().mockResolvedValue([]),
  restoreDocument: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  fetchDocumentBlob: vi.fn(),
}));
vi.mock("../api/projects", () => ({ listProjects: vi.fn() }));

import {
  listDocumentsPaginated,
  listTrash,
  restoreDocument,
  deleteDocument,
  fetchDocumentBlob,
  type DocumentResponse,
} from "../api/documents";
import { listProjects } from "../api/projects";

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

const mockProject = {
  id: "proj-1",
  name: "道路改良工事",
  code: "RD-001",
  description: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

function pageOf(docs: DocumentResponse[]) {
  return {
    items: docs,
    total: docs.length,
    page: 1,
    per_page: 20,
    pages: Math.max(1, Math.ceil(docs.length / 20)),
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

describe("Documents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    vi.mocked(listDocumentsPaginated).mockReturnValue(new Promise(() => {}));
    vi.mocked(listProjects).mockReturnValue(new Promise(() => {}));

    render(<Documents />, { wrapper: makeWrapper() });

    expect(screen.getByText("読み込み中...")).toBeInTheDocument();
  });

  it("shows empty state when no documents", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("ドキュメントがありません")).toBeInTheDocument();
    });
  });

  it("shows trash and restores a document", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    vi.mocked(listTrash).mockResolvedValueOnce([
      {
        ...mockDoc,
        id: "doc-trash",
        title: "削除済み図面",
        deletion_requested_at: "2026-08-01T00:00:00Z",
      },
    ]);
    vi.mocked(restoreDocument).mockResolvedValueOnce({
      ...mockDoc,
      id: "doc-trash",
      title: "削除済み図面",
    });
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });
    await user.click(screen.getByRole("button", { name: "ごみ箱" }));

    await waitFor(() => {
      expect(screen.getByText("削除済み図面")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "復元" }));
    await waitFor(() => {
      expect(restoreDocument).toHaveBeenCalled();
      expect(vi.mocked(restoreDocument).mock.calls[0][0]).toBe("doc-trash");
    });
  });

  it("shows document list", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
      // "図面" appears in both filter options and table cell — check at least one table cell
      expect(
        screen.getAllByText("図面").some((el) => el.tagName === "TD"),
      ).toBe(true);
      // "承認済" appears in both filter options and table cell span
      expect(screen.getAllByText("承認済").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("100 KB")).toBeInTheDocument();
    });
  });

  it("shows upload form when button clicked", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([mockProject]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await user.click(screen.getByRole("button", { name: "+ アップロード" }));

    expect(screen.getByText("ドキュメントのアップロード")).toBeInTheDocument();
    expect(screen.getByLabelText("タイトル")).toBeInTheDocument();
    expect(screen.getByLabelText("プロジェクト")).toBeInTheDocument();
    expect(screen.getByLabelText("種別")).toBeInTheDocument();
    expect(screen.getByLabelText("PDFファイル")).toBeInTheDocument();
  });

  it("hides upload form when cancel clicked", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await user.click(screen.getByRole("button", { name: "+ アップロード" }));
    expect(screen.getByText("ドキュメントのアップロード")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(
      screen.queryByText("ドキュメントのアップロード"),
    ).not.toBeInTheDocument();
  });

  it("shows project options in upload form", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([mockProject]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await user.click(screen.getByRole("button", { name: "+ アップロード" }));

    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "道路改良工事" }),
      ).toBeInTheDocument();
    });
  });

  it("shows document type options in upload form", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await user.click(screen.getByRole("button", { name: "+ アップロード" }));

    // scope to the upload-form type select to avoid duplicates with the filter bar
    const uploadTypeSelect = screen.getByLabelText("種別");
    expect(
      within(uploadTypeSelect).getByRole("option", { name: "図面" }),
    ).toBeInTheDocument();
    expect(
      within(uploadTypeSelect).getByRole("option", { name: "仕様書" }),
    ).toBeInTheDocument();
    expect(
      within(uploadTypeSelect).getByRole("option", { name: "報告書" }),
    ).toBeInTheDocument();
    expect(
      within(uploadTypeSelect).getByRole("option", { name: "契約書" }),
    ).toBeInTheDocument();
    expect(
      within(uploadTypeSelect).getByRole("option", { name: "その他" }),
    ).toBeInTheDocument();
  });

  it("upload button is enabled by default in upload form", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await user.click(screen.getByRole("button", { name: "+ アップロード" }));

    const uploadBtn = screen.getByRole("button", { name: "アップロード" });
    expect(uploadBtn).not.toBeDisabled();
  });

  it("calls deleteDocument after confirmation is clicked", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(deleteDocument).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    const deleteBtn = await screen.findByRole("button", { name: "削除" });
    await user.click(deleteBtn);
    await user.click(screen.getByRole("button", { name: "削除する" }));

    await waitFor(
      () => {
        expect(vi.mocked(deleteDocument).mock.calls[0]?.[0]).toBe("doc-1");
      },
      { timeout: 3000 },
    );
  });

  it("does not delete when confirmation is cancelled", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(deleteDocument).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    const deleteBtn = await screen.findByRole("button", { name: "削除" });
    await user.click(deleteBtn);
    expect(screen.getByText("削除しますか?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(deleteDocument).not.toHaveBeenCalled();
  });

  it("opens preview modal when preview button clicked", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValue(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(fetchDocumentBlob).mockResolvedValue(
      new Blob(["pdf"], { type: "application/pdf" }),
    );
    const createUrl = vi.fn(() => "blob:mock-url");
    const revokeUrl = vi.fn();
    (URL as unknown as { createObjectURL: typeof createUrl }).createObjectURL =
      createUrl;
    (URL as unknown as { revokeObjectURL: typeof revokeUrl }).revokeObjectURL =
      revokeUrl;
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    const previewBtn = await screen.findByRole("button", {
      name: "プレビュー",
    });
    await user.click(previewBtn);

    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: "ドキュメントプレビュー" }),
      ).toBeInTheDocument();
    });
  });

  it("shows multiple documents in table", async () => {
    const docs = [
      mockDoc,
      {
        ...mockDoc,
        id: "doc-2",
        title: "トンネル断面図",
        status: "pending",
        document_type: "specification",
      },
    ];
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf(docs));
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
      expect(screen.getByText("トンネル断面図")).toBeInTheDocument();
    });
  });

  it("shows search input and filter selects", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<Documents />, { wrapper: makeWrapper() });

    expect(screen.getByLabelText("タイトルで検索")).toBeInTheDocument();
    expect(screen.getByLabelText("種別フィルター")).toBeInTheDocument();
    expect(screen.getByLabelText("ステータスフィルター")).toBeInTheDocument();
  });

  it("filters documents by search query", async () => {
    const docs = [
      mockDoc,
      {
        ...mockDoc,
        id: "doc-2",
        title: "トンネル断面図",
        status: "draft",
        document_type: "specification",
      },
    ];
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf(docs));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
      expect(screen.getByText("トンネル断面図")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("タイトルで検索"), "橋梁");

    expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
    expect(screen.queryByText("トンネル断面図")).not.toBeInTheDocument();
  });

  it("filters documents by document type", async () => {
    const docs = [
      mockDoc,
      {
        ...mockDoc,
        id: "doc-2",
        title: "トンネル断面図",
        status: "draft",
        document_type: "specification",
      },
    ];
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf(docs));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument();
    });

    await user.selectOptions(
      screen.getByLabelText("種別フィルター"),
      "specification",
    );

    expect(screen.getByText("トンネル断面図")).toBeInTheDocument();
    expect(screen.queryByText("橋梁設計図")).not.toBeInTheDocument();
  });

  it("shows no-match message when filter has no results", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    await waitFor(() =>
      expect(screen.getByText("橋梁設計図")).toBeInTheDocument(),
    );
    await user.type(screen.getByLabelText("タイトルで検索"), "zzznomatch");

    expect(
      screen.getByText("条件に一致するドキュメントがありません"),
    ).toBeInTheDocument();
  });

  it("shows clear button when filters are active", async () => {
    vi.mocked(listDocumentsPaginated).mockResolvedValueOnce(pageOf([mockDoc]));
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    const user = userEvent.setup();

    render(<Documents />, { wrapper: makeWrapper() });

    expect(screen.queryByText("クリア")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("タイトルで検索"), "test");
    expect(screen.getByText("クリア")).toBeInTheDocument();
  });
});
