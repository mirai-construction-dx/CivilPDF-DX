// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { PrivacyView } from "../components/enterprise/views/PrivacyView";
import { useAuthStore } from "../store/auth";

// PrivacyView talks to the real GDPR/privacy API surface (consent, export,
// deletion). Mock that module so the tests assert the UI <-> API contract
// without a backend.
vi.mock("../api/privacy", () => ({
  recordConsent: vi.fn(),
  getConsentStatus: vi.fn(),
  exportUserData: vi.fn(),
  requestDeletion: vi.fn(),
}));

import {
  recordConsent,
  getConsentStatus,
  exportUserData,
  requestDeletion,
  type ConsentRecord,
  type DataExportResponse,
} from "../api/privacy";

const mockUser = {
  id: "user-1",
  email: "user@example.com",
  username: "user",
  full_name: "テスト利用者",
  role: "engineer" as const,
  status: "active" as const,
  created_at: "2026-01-01T00:00:00Z",
  last_login: null,
};

function makeConsent(overrides: Partial<ConsentRecord> = {}): ConsentRecord {
  return {
    id: "c1",
    user_id: "user-1",
    consent_type: "analytics",
    version: "1.0",
    granted: true,
    ip_address: null,
    user_agent: null,
    source: "web",
    disclosed_purpose: null,
    disclosed_retention_period: null,
    disclosed_third_parties: null,
    created_at: "2026-06-01T10:00:00Z",
    ...overrides,
  };
}

function makeProps() {
  return {
    onShowModal: vi.fn(),
    onShowToast: vi.fn(),
  };
}

function renderView(props = makeProps()) {
  render(<PrivacyView {...props} />);
  return props;
}

describe("PrivacyView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockUser, isAuthenticated: true });
    vi.mocked(getConsentStatus).mockResolvedValue([]);
  });

  it("loads the user's consent status on mount", async () => {
    renderView();
    await waitFor(() => {
      expect(getConsentStatus).toHaveBeenCalledWith("user-1");
    });
    // With no records, every consent type shows 未同意.
    const notConsented = await screen.findAllByText("未同意");
    expect(notConsented.length).toBeGreaterThanOrEqual(3);
  });

  it("reflects a granted consent record from the API", async () => {
    vi.mocked(getConsentStatus).mockResolvedValue([
      makeConsent({ consent_type: "analytics", granted: true }),
    ]);
    renderView();
    await waitFor(() => {
      expect(screen.getByText("同意済み")).toBeInTheDocument();
    });
    // The consent record count stat reflects the loaded records.
    expect(screen.getByText("同意履歴")).toBeInTheDocument();
  });

  it("records a new consent and refetches when toggled on", async () => {
    const granted = makeConsent({ consent_type: "analytics", granted: true });
    vi.mocked(getConsentStatus)
      .mockResolvedValueOnce([]) // initial mount
      .mockResolvedValueOnce([granted]); // after recordConsent
    vi.mocked(recordConsent).mockResolvedValue(granted);
    const props = renderView();
    const user = userEvent.setup();

    // The analytics row starts as 未同意, button label 同意する.
    const consentButtons = await screen.findAllByRole("button", {
      name: "同意する",
    });
    await user.click(consentButtons[0]);

    await waitFor(() => {
      expect(recordConsent).toHaveBeenCalledWith({
        consent_type: "analytics",
        version: "1.0",
        granted: true,
        source: "web",
      });
    });
    expect(getConsentStatus).toHaveBeenCalledTimes(2);
    expect(props.onShowToast).toHaveBeenCalledWith("同意を記録しました", "ok");
  });

  it("surfaces an error toast when recording consent fails", async () => {
    vi.mocked(recordConsent).mockRejectedValue(new Error("network"));
    const props = renderView();
    const user = userEvent.setup();

    const consentButtons = await screen.findAllByRole("button", {
      name: "同意する",
    });
    await user.click(consentButtons[0]);

    await waitFor(() => {
      expect(props.onShowToast).toHaveBeenCalledWith(
        "操作に失敗しました",
        "error",
      );
    });
  });

  it("exports the user's data (GDPR Art.20) and shows the result", async () => {
    const exportData: DataExportResponse = {
      user_id: "user-1",
      email: "user@example.com",
      username: "user",
      full_name: "テスト利用者",
      role: "engineer",
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      documents: [
        {
          id: "d1",
          title: "図面A",
          document_type: "drawing",
          filename: "a.pdf",
          file_size: 1024,
          created_at: "2026-02-01T00:00:00Z",
          deletion_requested_at: null,
        },
      ],
      consent_records: [makeConsent()],
      exported_at: "2026-06-21T00:00:00Z",
    };
    vi.mocked(exportUserData).mockResolvedValue(exportData);
    const props = renderView();
    const user = userEvent.setup();

    await user.click(
      screen.getByRole("button", { name: "データエクスポート" }),
    );
    await user.click(screen.getByRole("button", { name: "データを取得" }));

    await waitFor(() => {
      expect(exportUserData).toHaveBeenCalledWith("user-1");
    });
    expect(props.onShowToast).toHaveBeenCalledWith(
      "データのエクスポートが完了しました",
      "ok",
    );
    // A JSON download button appears once data is loaded.
    expect(
      screen.getByRole("button", { name: "JSON ダウンロード" }),
    ).toBeInTheDocument();
  });

  it("requests deletion (GDPR Art.17) after confirmation and shows the receipt", async () => {
    vi.mocked(requestDeletion).mockResolvedValue({
      user_id: "user-1",
      documents_marked: 3,
      deletion_requested_at: "2026-06-21T00:00:00Z",
      audit_log_id: "audit-1",
    });
    const props = renderView();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "削除リクエスト" }));
    await user.click(
      screen.getByRole("button", { name: "削除をリクエストする" }),
    );
    // Confirmation step
    await user.click(
      screen.getByRole("button", { name: "削除リクエストを確定する" }),
    );

    await waitFor(() => {
      expect(requestDeletion).toHaveBeenCalledWith("user-1");
    });
    expect(props.onShowModal).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "削除リクエストを受け付けました",
        body: expect.stringContaining("対象文書数: 3 件"),
      }),
    );
  });
});
