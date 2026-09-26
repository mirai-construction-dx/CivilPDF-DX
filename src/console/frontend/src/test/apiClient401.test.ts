// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import type { AxiosAdapter } from "axios";
import axios from "axios";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

// jsdom は location.href 代入によるナビゲーション未実装のため、書換え可能なスタブへ差し替える
function stubLocation(pathname: string) {
  const loc = { pathname, href: `https://example.com${pathname}` };
  Object.defineProperty(window, "location", {
    value: loc,
    writable: true,
    configurable: true,
  });
  return loc;
}

// 指定 URL への全リクエストを 401 で失敗させるアダプタ
function reject401(url: string) {
  api.defaults.adapter = (async (config) =>
    Promise.reject({
      response: { status: 401 },
      config: { ...config, url },
    })) as AxiosAdapter;
}

describe("api client 401 interceptor", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ user: null, isAuthenticated: false });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ログインエンドポイント自身の 401 ではリダイレクトしない (フォームが消えない)", async () => {
    const loc = stubLocation("/login");
    reject401("/auth/token");
    await expect(api.post("/auth/token")).rejects.toBeTruthy();
    expect(loc.href).toBe("https://example.com/login");
  });

  it("/login 上で失効 token の 401 が来たら token を破棄しリロードしない (無限ループ防止)", async () => {
    const loc = stubLocation("/login");
    localStorage.setItem("access_token", "stale");
    reject401("/auth/me");
    await expect(api.get("/auth/me")).rejects.toBeTruthy();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(loc.href).toBe("https://example.com/login");
  });

  it("他ページでの 401 (refresh なし) は token 破棄のうえ /login へ遷移する", async () => {
    const loc = stubLocation("/dashboard");
    localStorage.setItem("access_token", "stale");
    reject401("/documents");
    await expect(api.get("/documents")).rejects.toBeTruthy();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(loc.href).toBe("/login");
  });

  it("複数リクエスト同時 401 でも refresh は 1 回だけ実行され、両方再試行される", async () => {
    const loc = stubLocation("/dashboard");
    localStorage.setItem("access_token", "stale");
    localStorage.setItem("refresh_token", "rt");
    const postSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "new-token", refresh_token: "new-refresh" },
    });

    let docCalls = 0;
    api.defaults.adapter = (async (config) => {
      if ((config.url ?? "").includes("/documents")) {
        docCalls += 1;
        if (docCalls <= 2) {
          return Promise.reject({
            response: { status: 401 },
            config: { ...config },
          });
        }
        return Promise.resolve({
          data: [{ id: "x" }],
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        });
      }
      return Promise.reject(new Error(`unexpected url: ${config.url}`));
    }) as AxiosAdapter;

    const results = await Promise.all([
      api.get("/documents"),
      api.get("/documents"),
    ]);
    expect(results.map((r) => r.data)).toEqual([[{ id: "x" }], [{ id: "x" }]]);

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("access_token")).toBe("new-token");
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
    expect(loc.href).toBe("https://example.com/dashboard");
  });

  it("refresh 失敗時は認証ストアをクリアし /login へ遷移する", async () => {
    const loc = stubLocation("/dashboard");
    localStorage.setItem("access_token", "stale");
    localStorage.setItem("refresh_token", "rt");
    useAuthStore.setState({
      user: {
        id: "u-1",
        email: "a@example.com",
        username: "a",
        full_name: "A",
        role: "admin",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
        last_login: null,
      },
      isAuthenticated: true,
    });
    vi.spyOn(axios, "post").mockRejectedValue(new Error("refresh failed"));
    api.defaults.adapter = (async (config) =>
      Promise.reject({
        response: { status: 401 },
        config: { ...config },
      })) as AxiosAdapter;

    await expect(api.get("/documents")).rejects.toBeTruthy();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
    expect(loc.href).toBe("/login");
  });
});
