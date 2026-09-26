// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { ElectronicDeliveryModal } from "../components/ElectronicDeliveryModal";

vi.mock("../api/electronicDelivery", () => ({
  checkDeliveryReadiness: vi.fn(),
  downloadDeliveryZip: vi.fn(),
  deliveryErrorMessage: vi.fn().mockResolvedValue("ZIP 生成に失敗しました。"),
}));

import {
  checkDeliveryReadiness,
  deliveryErrorMessage,
  downloadDeliveryZip,
} from "../api/electronicDelivery";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const defaultProps = {
  projectId: "proj-1",
  projectName: "国道7号改良工事",
  projectCode: "RD-007",
  onClose: vi.fn(),
};

const readyData = {
  ready: true,
  document_count: 3,
  pdfa_compliant_count: 3,
  non_pdfa_documents: [],
  warnings: [],
};

const notReadyData = {
  ready: false,
  document_count: 2,
  pdfa_compliant_count: 1,
  non_pdfa_documents: [{ id: "d-1", title: "設計図", filename: "design.pdf" }],
  unreadable_documents: [],
  warnings: ["PDF/A 非準拠のファイルが含まれています"],
};

const unreadableData = {
  ready: false,
  document_count: 2,
  pdfa_compliant_count: 2,
  non_pdfa_documents: [],
  unreadable_documents: [
    {
      id: "d-9",
      title: "欠損図面",
      filename: "missing.pdf",
      reason: "ファイルが存在しません",
    },
  ],
  warnings: [
    "ファイルを読み取れない文書が 1 件あります（納品パッケージ内で 0 バイトになります）",
  ],
};

describe("ElectronicDeliveryModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state while fetching readiness", () => {
    vi.mocked(checkDeliveryReadiness).mockReturnValue(new Promise(() => {}));
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByText("確認中...")).toBeInTheDocument();
  });

  it("shows modal title and project name", () => {
    vi.mocked(checkDeliveryReadiness).mockReturnValue(new Promise(() => {}));
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    expect(screen.getByText("📦 電子納品パッケージ生成")).toBeInTheDocument();
    expect(screen.getByText("国道7号改良工事")).toBeInTheDocument();
  });

  it("is an accessible dialog that closes on Escape", async () => {
    vi.mocked(checkDeliveryReadiness).mockReturnValue(new Promise(() => {}));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <ElectronicDeliveryModal
        projectId="proj-1"
        projectName="テスト工事"
        projectCode="TST001"
        onClose={onClose}
      />,
      { wrapper: makeWrapper() },
    );

    expect(
      screen.getByRole("dialog", { name: /電子納品パッケージ生成/ }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows ready status with document counts", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(readyData);
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(screen.getByText("✅ 納品可能")).toBeInTheDocument();
    });
    expect(screen.getAllByText("3")).toHaveLength(2);
  });

  it("shows not-ready status with warning", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(notReadyData);
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(screen.getByText("⚠️ 要確認")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/PDF\/A 非準拠のファイルが含まれています/),
    ).toBeInTheDocument();
  });

  it("shows non-pdfa document list", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(notReadyData);
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(screen.getByText("設計図")).toBeInTheDocument();
    });
    expect(screen.getByText("PDF/A 非準拠ファイル:")).toBeInTheDocument();
  });

  it("shows success message after download", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(readyData);
    vi.mocked(downloadDeliveryZip).mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /ZIP ダウンロード/ }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /ZIP ダウンロード/ }));
    await waitFor(() => {
      expect(
        screen.getByText("✅ ZIP ファイルをダウンロードしました。"),
      ).toBeInTheDocument();
    });
  });

  it("shows error message when download fails", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(readyData);
    vi.mocked(downloadDeliveryZip).mockRejectedValue(
      new Error("サーバーエラー"),
    );
    const user = userEvent.setup();
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /ZIP ダウンロード/ }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /ZIP ダウンロード/ }));
    await waitFor(() => {
      expect(
        screen.getByText("❌ ZIP 生成に失敗しました。"),
      ).toBeInTheDocument();
    });
  });

  it("lists documents whose file cannot be read", async () => {
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(unreadableData);
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(
        screen.getByText("読み取れないファイル（納品パッケージにできません）:"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/欠損図面 — ファイルが存在しません/),
    ).toBeInTheDocument();
  });

  it("surfaces the server's reason when packaging is refused", async () => {
    const detail =
      "ファイルを読み取れない文書が 1 件あるため、電子納品パッケージを生成できません: 欠損図面（ファイルが存在しません）。";
    vi.mocked(checkDeliveryReadiness).mockResolvedValue(unreadableData);
    vi.mocked(downloadDeliveryZip).mockRejectedValue(new Error("409"));
    vi.mocked(deliveryErrorMessage).mockResolvedValue(detail);

    const user = userEvent.setup();
    render(<ElectronicDeliveryModal {...defaultProps} />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /ZIP ダウンロード/ }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /ZIP ダウンロード/ }));
    await waitFor(() => {
      expect(
        screen.getByText(
          new RegExp("ファイルを読み取れない文書が 1 件あるため"),
        ),
      ).toBeInTheDocument();
    });
  });

  it("calls onClose when footer close button clicked", async () => {
    vi.mocked(checkDeliveryReadiness).mockReturnValue(new Promise(() => {}));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <ElectronicDeliveryModal
        projectId="proj-1"
        projectName="テスト工事"
        projectCode="TST001"
        onClose={onClose}
      />,
      { wrapper: makeWrapper() },
    );
    await user.click(screen.getByText("閉じる"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
