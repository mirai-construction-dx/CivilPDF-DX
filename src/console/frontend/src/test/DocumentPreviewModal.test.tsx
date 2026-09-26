// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { DocumentPreviewModal } from "../components/DocumentPreviewModal";

vi.mock("../api/documents", () => ({
  fetchDocumentBlob: vi.fn(),
}));

import { fetchDocumentBlob } from "../api/documents";

describe("DocumentPreviewModal", () => {
  let createUrl: ReturnType<typeof vi.fn>;
  let revokeUrl: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    createUrl = vi.fn(() => "blob:mock-url");
    revokeUrl = vi.fn();
    (URL as unknown as { createObjectURL: typeof createUrl }).createObjectURL =
      createUrl;
    (URL as unknown as { revokeObjectURL: typeof revokeUrl }).revokeObjectURL =
      revokeUrl;
    vi.mocked(fetchDocumentBlob).mockResolvedValue(
      new Blob(["pdf"], { type: "application/pdf" }),
    );
  });

  it("renders nothing when documentId is null", () => {
    const { container } = render(
      <DocumentPreviewModal
        documentId={null}
        filename="x.pdf"
        onClose={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows unsupported message for non-PDF files", () => {
    render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="image.png"
        onClose={() => {}}
      />,
    );
    expect(
      screen.getByText("プレビュー非対応のファイル形式です"),
    ).toBeInTheDocument();
  });

  it("fetches blob and renders iframe for PDF", async () => {
    render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="report.pdf"
        title="月次レポート"
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      const iframe = screen.getByTitle("月次レポート") as HTMLIFrameElement;
      expect(iframe).toBeInTheDocument();
      expect(iframe.src).toContain("blob:mock-url");
      expect(iframe.getAttribute("sandbox")).toBe(
        "allow-scripts allow-same-origin",
      );
    });
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(fetchDocumentBlob).toHaveBeenCalledWith("d-1");
  });

  it("shows error message when fetch fails", async () => {
    vi.mocked(fetchDocumentBlob).mockRejectedValueOnce(
      new Error("ネットワーク失敗"),
    );

    render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="x.pdf"
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("ネットワーク失敗")).toBeInTheDocument();
    });
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="x.pdf"
        onClose={onClose}
      />,
    );

    await user.click(screen.getByRole("button", { name: "閉じる" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key pressed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="x.pdf"
        onClose={onClose}
      />,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("revokes object URL on unmount", async () => {
    const { unmount } = render(
      <DocumentPreviewModal
        documentId="d-1"
        filename="x.pdf"
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(createUrl).toHaveBeenCalled();
    });

    unmount();
    expect(revokeUrl).toHaveBeenCalledWith("blob:mock-url");
  });
});
