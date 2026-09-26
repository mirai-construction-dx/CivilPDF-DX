// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { Users } from "../pages/Users";
import { useAuthStore } from "../store/auth";

vi.mock("../api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import { api } from "../api/client";

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

const mockManager = {
  ...mockAdmin,
  id: "manager-1",
  role: "manager" as const,
  email: "manager@example.com",
  full_name: "マネージャー",
};

const mockViewer = {
  ...mockAdmin,
  id: "viewer-1",
  role: "viewer" as const,
  email: "viewer@example.com",
  full_name: "閲覧ユーザー",
};

const mockUserList = [
  {
    id: "u1",
    email: "alice@example.com",
    username: "alice",
    full_name: "Alice Tanaka",
    role: "engineer",
    status: "active",
    last_login: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "u2",
    email: "bob@example.com",
    username: "bob",
    full_name: "Bob Yamada",
    role: "viewer",
    status: "inactive",
    last_login: "2026-05-01T00:00:00Z",
    created_at: "2026-01-02T00:00:00Z",
  },
];

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

describe("Users", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("denies access for viewer role", () => {
    useAuthStore.setState({ user: mockViewer, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValue({ data: [] });

    render(<Users />, { wrapper: makeWrapper() });

    expect(
      screen.getByText("この画面へのアクセス権限がありません"),
    ).toBeInTheDocument();
  });

  it("shows loading state initially for admin", () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));

    render(<Users />, { wrapper: makeWrapper() });

    expect(screen.getByText("読み込み中...")).toBeInTheDocument();
  });

  it("displays user list for admin", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: mockUserList });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("Alice Tanaka")).toBeInTheDocument();
      expect(screen.getByText("Bob Yamada")).toBeInTheDocument();
    });
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("有効")).toBeInTheDocument();
    expect(screen.getByText("無効")).toBeInTheDocument();
  });

  it("shows role labels correctly", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: mockUserList });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("エンジニア")).toBeInTheDocument();
      expect(screen.getByText("閲覧者")).toBeInTheDocument();
    });
  });

  it("admin sees add-user button", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: [] });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.queryByText("読み込み中...")).not.toBeInTheDocument();
    });
    expect(screen.getByText("+ ユーザー追加")).toBeInTheDocument();
  });

  it("manager sees list but no add-user button", async () => {
    useAuthStore.setState({ user: mockManager, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: mockUserList });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("Alice Tanaka")).toBeInTheDocument();
    });
    expect(screen.queryByText("+ ユーザー追加")).not.toBeInTheDocument();
  });

  it("manager does not see disable/enable buttons", async () => {
    useAuthStore.setState({ user: mockManager, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: mockUserList });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("Alice Tanaka")).toBeInTheDocument();
    });
    expect(screen.queryByText("無効化")).not.toBeInTheDocument();
    expect(screen.queryByText("有効化")).not.toBeInTheDocument();
  });

  it("admin sees disable button for other active users", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: mockUserList });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("無効化")).toBeInTheDocument();
    });
    expect(screen.getByText("有効化")).toBeInTheDocument();
  });

  it("admin does not see toggle button for themselves", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    const usersIncludingAdmin = [
      {
        id: "admin-1",
        email: "admin@example.com",
        username: "admin",
        full_name: "Self Admin",
        role: "admin",
        status: "active",
        last_login: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    vi.mocked(api.get).mockResolvedValueOnce({ data: usersIncludingAdmin });

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("Self Admin")).toBeInTheDocument();
    });
    expect(screen.queryByText("無効化")).not.toBeInTheDocument();
  });

  it("shows user creation form when button clicked", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: [] });
    const user = userEvent.setup();

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("+ ユーザー追加")).toBeInTheDocument();
    });
    await user.click(screen.getByText("+ ユーザー追加"));

    expect(screen.getByText("新規ユーザー作成")).toBeInTheDocument();
    expect(screen.getAllByText("メールアドレス").length).toBeGreaterThan(0);
  });

  it("hides form on cancel", async () => {
    useAuthStore.setState({ user: mockAdmin, isAuthenticated: true });
    vi.mocked(api.get).mockResolvedValueOnce({ data: [] });
    const user = userEvent.setup();

    render(<Users />, { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(screen.getByText("+ ユーザー追加")).toBeInTheDocument();
    });
    await user.click(screen.getByText("+ ユーザー追加"));
    expect(screen.getByText("新規ユーザー作成")).toBeInTheDocument();

    await user.click(screen.getByText("キャンセル"));
    expect(screen.queryByText("新規ユーザー作成")).not.toBeInTheDocument();
  });
});
