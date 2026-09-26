// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import App from "../App";
import { useAuthStore } from "../store/auth";

// EnterpriseLayout's default view (LandingView) makes no API calls, so only
// the auth bootstrap (getMe) needs mocking for these routing/rehydration tests.
vi.mock("../api/auth", () => ({
  getMe: vi.fn(),
}));
vi.mock("../api/notifications", () => ({
  listNotifications: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    per_page: 20,
    pages: 0,
  }),
  unreadCount: vi.fn().mockResolvedValue(0),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
}));
// The shell renders the workflow badge from stats pending_approvals.
vi.mock("../api/stats", () => ({
  getStats: vi.fn().mockResolvedValue({ pending_approvals: 0 }),
}));

import { getMe } from "../api/auth";

const mockAdmin = {
  id: "admin-1",
  email: "admin@example.com",
  username: "admin",
  full_name: "管理者",
  role: "admin" as const,
  status: "active" as const,
  created_at: "2026-01-01T00:00:00Z",
  last_login: null,
};

describe("App routing & auth rehydration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAuthStore.setState({ user: null, isAuthenticated: false });
    window.history.pushState({}, "", "/");
  });

  it("redirects to /login when no token is present", async () => {
    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "ログイン" }),
      ).toBeInTheDocument();
    });
    expect(getMe).not.toHaveBeenCalled();
  });

  it("rehydrates the user via getMe on reload when a token exists", async () => {
    localStorage.setItem("access_token", "persisted-token");
    useAuthStore.setState({ user: null, isAuthenticated: true });
    vi.mocked(getMe).mockResolvedValueOnce(mockAdmin);

    render(<App />);

    await waitFor(() => {
      expect(getMe).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(useAuthStore.getState().user?.role).toBe("admin");
    });
    // The enterprise shell is rendered for an authenticated user
    expect(screen.getByText("CivilPDF·DX")).toBeInTheDocument();
  });

  it("does not call getMe when the user is already in the store", async () => {
    localStorage.setItem("access_token", "persisted-token");
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("CivilPDF·DX")).toBeInTheDocument();
    });
    expect(getMe).not.toHaveBeenCalled();
  });

  it("keeps the session usable if rehydration fails (no crash)", async () => {
    localStorage.setItem("access_token", "persisted-token");
    useAuthStore.setState({ user: null, isAuthenticated: true });
    vi.mocked(getMe).mockRejectedValueOnce(new Error("network"));

    render(<App />);

    await waitFor(() => {
      expect(getMe).toHaveBeenCalledTimes(1);
    });
    // Shell still renders (EnterpriseLayout falls back to demo profile data)
    expect(screen.getByText("CivilPDF·DX")).toBeInTheDocument();
  });
});
