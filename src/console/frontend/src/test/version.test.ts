// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchServerVersion } from "../api/version";

function mockFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

describe("fetchServerVersion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the version reported by /health", async () => {
    mockFetch(async () => ({
      ok: true,
      json: async () => ({ status: "ok", version: "0.10.0" }),
    }));
    await expect(fetchServerVersion()).resolves.toBe("0.10.0");
    expect(fetch).toHaveBeenCalledWith("/health", expect.anything());
  });

  it("returns null on HTTP errors, bad payloads and network failures", async () => {
    mockFetch(async () => ({ ok: false, json: async () => ({}) }));
    await expect(fetchServerVersion()).resolves.toBeNull();

    mockFetch(async () => ({ ok: true, json: async () => ({ version: 1 }) }));
    await expect(fetchServerVersion()).resolves.toBeNull();

    mockFetch(async () => {
      throw new TypeError("network");
    });
    await expect(fetchServerVersion()).resolves.toBeNull();
  });
});
