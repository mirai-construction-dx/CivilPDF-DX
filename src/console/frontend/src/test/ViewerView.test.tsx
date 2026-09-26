// @vitest-environment jsdom
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { ViewerView } from "../components/enterprise/views/ViewerView";

vi.mock("../api/documents", () => ({
  listDocuments: vi.fn(),
}));
vi.mock("../api/ai", () => ({
  extractDocumentData: vi.fn(),
  classifyDocument: vi.fn(),
}));

import { listDocuments } from "../api/documents";
import { extractDocumentData } from "../api/ai";

const mockDoc = {
  id: "doc-1",
  title: "橋梁設計図",
  document_type: "drawing",
  status: "approved",
  filename: "bridge-design.pdf",
  file_size: 2048000,
  page_count: 12,
  is_pdfa: true,
  tags: ["構造", "橋梁"],
  project_id: "proj-1",
  owner_id: "user-1",
  created_at: "2026-05-01T10:00:00Z",
  updated_at: "2026-05-15T09:30:00Z",
};

function makeProps() {
  return {
    onNavigate: vi.fn(),
    onShowModal: vi.fn(),
    onShowToast: vi.fn(),
  };
}

describe("ViewerView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches document list on mount", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      expect(listDocuments).toHaveBeenCalledWith({ per_page: 50 });
    });
  });

  it("shows document selector when documents are loaded", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      const select = screen.getByRole("combobox");
      expect(select).toBeInTheDocument();
    });
  });

  it("displays static demo mode when API returns empty list", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      expect(listDocuments).toHaveBeenCalled();
    });
    // デモモードでは静的チェック項目が表示される
    expect(screen.getByText("チェック")).toBeInTheDocument();
  });

  it("shows document metadata in meta tab when doc is selected", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    // メタ情報タブをクリック
    fireEvent.click(screen.getByText("メタ情報"));

    await waitFor(() => {
      expect(screen.getByText("bridge-design.pdf")).toBeInTheDocument();
      expect(screen.getByText("準拠")).toBeInTheDocument();
      expect(screen.getByText("12")).toBeInTheDocument();
    });
  });

  it("shows extract button in extracted tab", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("抽出データ"));

    expect(await screen.findByTestId("extract-btn")).toBeInTheDocument();
  });

  it("calls extractDocumentData and shows result on extract", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);
    vi.mocked(extractDocumentData).mockResolvedValueOnce({
      document_id: "doc-1",
      extracted_at: "2026-06-14T00:00:00Z",
      model: "gpt-4",
      data: {
        construction_name: "県道改良工事",
        contractor: "○○建設株式会社",
      },
    });

    const props = makeProps();
    render(<ViewerView {...props} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("抽出データ"));
    fireEvent.click(await screen.findByTestId("extract-btn"));

    await waitFor(() => {
      expect(extractDocumentData).toHaveBeenCalledWith("doc-1");
      expect(props.onShowToast).toHaveBeenCalledWith(
        "AI抽出が完了しました",
        "ok",
      );
    });

    expect(screen.getByText("県道改良工事")).toBeInTheDocument();
  });

  it("shows error toast when extract API fails", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);
    vi.mocked(extractDocumentData).mockRejectedValueOnce(
      new Error("API error"),
    );

    const props = makeProps();
    render(<ViewerView {...props} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("抽出データ"));
    fireEvent.click(await screen.findByTestId("extract-btn"));

    await waitFor(() => {
      expect(props.onShowToast).toHaveBeenCalledWith(
        "AI抽出に失敗しました",
        "error",
      );
    });
  });

  it("shows check items in check tab", async () => {
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc]);

    render(<ViewerView {...makeProps()} />);

    // チェックタブはデフォルトでアクティブ
    expect(screen.getByText("チェック")).toBeInTheDocument();

    await waitFor(() => {
      // 静的チェック項目が表示される
      expect(screen.getByText("縮尺表記の不一致")).toBeInTheDocument();
    });
    // Sample items must be labelled so they are not read as real results.
    expect(screen.getByTestId("check-demo-notice")).toHaveTextContent(
      "選択中の文書の検査結果ではありません",
    );
    expect(screen.getByText("チェック結果（サンプル）")).toBeInTheDocument();
  });

  it("gracefully falls back to demo mode when API call fails", async () => {
    vi.mocked(listDocuments).mockRejectedValueOnce(new Error("Network error"));

    render(<ViewerView {...makeProps()} />);

    // エラー時も静的UIが表示される（クラッシュしない）
    await waitFor(() => {
      expect(screen.getByText("チェック")).toBeInTheDocument();
    });
  });

  it("resets page and extract result on document change", async () => {
    const doc2 = {
      ...mockDoc,
      id: "doc-2",
      title: "道路設計図",
      filename: "road.pdf",
    };
    vi.mocked(listDocuments).mockResolvedValueOnce([mockDoc, doc2]);
    vi.mocked(extractDocumentData).mockResolvedValueOnce({
      document_id: "doc-1",
      extracted_at: "2026-06-14T00:00:00Z",
      model: "gpt-4",
      data: { construction_name: "橋梁工事" },
    });

    render(<ViewerView {...makeProps()} />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    // AI抽出実行
    fireEvent.click(screen.getByText("抽出データ"));
    fireEvent.click(await screen.findByTestId("extract-btn"));

    await waitFor(() => {
      expect(screen.getByText("橋梁工事")).toBeInTheDocument();
    });

    // 別の文書に切り替え → 抽出結果がリセットされる
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "doc-2" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("extract-btn")).toBeInTheDocument();
    });
  });

  it("does not show fabricated document metadata when nothing is selected", async () => {
    // Regression: the empty state used to render a made-up document
    // (県道○○号_詳細図_Rev04.dwg / 218 MB / AutoCAD 2024 / OCR 処理: 完了 (日本語))
    // as if it were real properties.
    vi.mocked(listDocuments).mockResolvedValue([]);
    render(<ViewerView {...makeProps()} />);

    // Metadata lives behind the メタ情報 tab.
    fireEvent.click(await screen.findByRole("tab", { name: /メタ情報/ }));
    await waitFor(() => {
      expect(
        screen.getByText("選択された文書はありません"),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/県道○○号_詳細図/)).not.toBeInTheDocument();
    expect(screen.queryByText(/AutoCAD 2024/)).not.toBeInTheDocument();
    expect(screen.queryByText(/完了 \(日本語\)/)).not.toBeInTheDocument();
    expect(screen.queryByText("218 MB")).not.toBeInTheDocument();
  });
});
