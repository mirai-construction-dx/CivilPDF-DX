// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useAuthStore } from "../store/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ user: null, isAuthenticated: false });
  });

  it("initializes as unauthenticated when no token in localStorage", () => {
    const { isAuthenticated, user } = useAuthStore.getState();
    expect(isAuthenticated).toBe(false);
    expect(user).toBeNull();
  });

  it("setUser marks store as authenticated", () => {
    const mockUser = {
      id: "1",
      email: "admin@test.com",
      username: "admin",
      full_name: "Admin",
      role: "admin" as const,
      status: "active" as const,
      created_at: "2026-01-01T00:00:00Z",
      last_login: null,
    };
    useAuthStore.getState().setUser(mockUser);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });

  it("setUser(null) marks store as unauthenticated", () => {
    useAuthStore.setState({ isAuthenticated: true });
    useAuthStore.getState().setUser(null);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("logout clears localStorage and resets state", () => {
    localStorage.setItem("access_token", "abc");
    localStorage.setItem("refresh_token", "xyz");
    useAuthStore.setState({ isAuthenticated: true });

    useAuthStore.getState().logout();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("clearAuth removes only auth tokens and keeps other app keys", () => {
    localStorage.setItem("access_token", "abc");
    localStorage.setItem("refresh_token", "xyz");
    localStorage.setItem("theme", "dark");
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: "1" } as never,
    });

    useAuthStore.getState().clearAuth();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });
});

describe("getInitialAuthState (build-mode auth gate, Issue #59)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    localStorage.clear();
  });

  it("DEV build treats every visitor as authenticated (dev bypass)", async () => {
    vi.stubEnv("DEV", true);
    localStorage.clear();
    vi.resetModules();
    const { useAuthStore: store } = await import("../store/auth");
    expect(store.getState().isAuthenticated).toBe(true);
  });

  it("PROD build without a token starts unauthenticated (gate enforced)", async () => {
    vi.stubEnv("DEV", false);
    localStorage.clear();
    vi.resetModules();
    const { useAuthStore: store } = await import("../store/auth");
    expect(store.getState().isAuthenticated).toBe(false);
  });

  it("PROD build with a stored token is authenticated", async () => {
    vi.stubEnv("DEV", false);
    localStorage.setItem("access_token", "token123");
    vi.resetModules();
    const { useAuthStore: store } = await import("../store/auth");
    expect(store.getState().isAuthenticated).toBe(true);
  });

  it("PROD build with VITE_AUTH_BYPASS=true skips the login screen without a token", async () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_AUTH_BYPASS", "true");
    localStorage.clear();
    vi.resetModules();
    const { useAuthStore: store } = await import("../store/auth");
    expect(store.getState().isAuthenticated).toBe(true);
    expect(localStorage.getItem("access_token")).toBeNull();
  });
});
