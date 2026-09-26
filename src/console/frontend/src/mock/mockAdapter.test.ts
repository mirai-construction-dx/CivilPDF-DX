import { describe, it, expect } from "vitest";
import type { InternalAxiosRequestConfig } from "axios";
import { mockAdapter } from "./mockAdapter";
import {
  mockDocuments,
  mockProjects,
  mockUsers,
  mockWorkflows,
} from "./mockData";

function req(
  method: string,
  url: string,
  extra: Partial<InternalAxiosRequestConfig> = {},
): InternalAxiosRequestConfig {
  return {
    method,
    url,
    baseURL: "/api/v1",
    headers: {},
    ...extra,
  } as InternalAxiosRequestConfig;
}

describe("mockAdapter", () => {
  it("returns abundant dummy data for core list endpoints", async () => {
    const docs = await mockAdapter(req("get", "/documents/"));
    expect(docs.data.length).toBeGreaterThanOrEqual(100);

    const projects = await mockAdapter(req("get", "/projects/"));
    expect(projects.data.length).toBeGreaterThanOrEqual(20);

    const users = await mockAdapter(req("get", "/users/"));
    expect(users.data.length).toBeGreaterThanOrEqual(30);

    const workflows = await mockAdapter(req("get", "/workflows/"));
    expect(workflows.data.length).toBeGreaterThanOrEqual(50);
    expect(workflows.data[0]).toHaveProperty("document_title");
    expect(workflows.data[0]).toHaveProperty("pending_step_count");
  });

  it("authenticates any credentials and returns the mock admin", async () => {
    const form = new URLSearchParams();
    form.append("username", "anyone@example.com");
    form.append("password", "whatever");
    const token = await mockAdapter(req("post", "/auth/token", { data: form }));
    expect(token.data.access_token).toBeTruthy();

    const me = await mockAdapter(req("get", "/auth/me"));
    expect(me.data.role).toBe("admin");
    expect(me.data.email).toContain("@");
  });

  it("paginates and filters audit logs", async () => {
    const page1 = await mockAdapter(
      req("get", "/audit-logs/?page=1&per_page=50"),
    );
    expect(page1.data.items).toHaveLength(50);
    expect(page1.data.total).toBeGreaterThanOrEqual(300);
    expect(page1.data.pages).toBeGreaterThanOrEqual(6);

    const filtered = await mockAdapter(
      req("get", "/audit-logs/?page=1&per_page=50&action=login"),
    );
    expect(
      filtered.data.items.every(
        (i: { action: string }) => i.action === "login",
      ),
    ).toBe(true);
  });

  it("derives stats from the document store", async () => {
    const stats = await mockAdapter(req("get", "/stats/"));
    expect(stats.data.total_documents).toBe(mockDocuments.length);
    expect(stats.data.active_users).toBe(
      mockUsers.filter((u) => u.status === "active").length,
    );
    expect(Object.keys(stats.data.by_type).length).toBeGreaterThanOrEqual(4);
  });

  it("mutates the store on workflow decisions", async () => {
    const wf = mockWorkflows.find((w) => w.status === "in_progress")!;
    const step = wf.steps.find((s) => s.status === "pending")!;
    const res = await mockAdapter(
      req("post", `/workflows/${wf.id}/steps/${step.id}/decide`, {
        data: JSON.stringify({ decision: "reject", comment: "NG" }),
      }),
    );
    expect(res.data.status).toBe("rejected");
    expect(step.status).toBe("rejected");
    expect(step.comment).toBe("NG");
  });

  it("creates and deletes projects in-memory", async () => {
    const before = mockProjects.length;
    const created = await mockAdapter(
      req("post", "/projects/", {
        data: JSON.stringify({ name: "テスト工事", code: "PRJ-TEST-001" }),
      }),
    );
    expect(mockProjects.length).toBe(before + 1);
    await mockAdapter(req("delete", `/projects/${created.data.id}`));
    expect(mockProjects.length).toBe(before);
  });

  it("serves document download as a PDF blob", async () => {
    const res = await mockAdapter(
      req("get", `/documents/${mockDocuments[0].id}/download`, {
        responseType: "blob",
      }),
    );
    expect(res.data).toBeInstanceOf(Blob);
    expect(res.data.type).toBe("application/pdf");
  });

  it("answers timestamp / AI / search endpoints", async () => {
    const docId = mockDocuments[0].id;
    const ts = await mockAdapter(req("post", `/documents/${docId}/timestamp`));
    expect(ts.data.token_type).toBe("rfc3161");

    const verify = await mockAdapter(
      req("get", `/documents/${docId}/timestamp/verify`),
    );
    expect(verify.data.valid).toBe(true);

    const classify = await mockAdapter(
      req("post", `/ai/documents/${docId}/classify`),
    );
    expect(classify.data.confidence).toBeGreaterThan(0);

    const search = await mockAdapter(
      req("get", "/search/documents", {
        params: { q: "橋梁", mode: "keyword", limit: 5 },
      }),
    );
    expect(search.data.hits.length).toBeGreaterThan(0);
    expect(search.data.hits.length).toBeLessThanOrEqual(5);
  });

  it("rejects invalid enum payloads with 422", async () => {
    const wf = mockWorkflows.find((w) =>
      w.steps.some((s) => s.status === "pending"),
    )!;
    const step = wf.steps.find((s) => s.status === "pending")!;
    await expect(
      mockAdapter(
        req("post", `/workflows/${wf.id}/steps/${step.id}/decide`, {
          data: JSON.stringify({ decision: "maybe" }),
        }),
      ),
    ).rejects.toMatchObject({ response: { status: 422 } });

    await expect(
      mockAdapter(
        req("patch", `/users/${mockUsers[1].id}`, {
          data: JSON.stringify({ role: "superuser" }),
        }),
      ),
    ).rejects.toMatchObject({ response: { status: 422 } });
  });

  it("rejects unknown routes with a 404-shaped error", async () => {
    await expect(
      mockAdapter(req("get", "/no-such-endpoint")),
    ).rejects.toMatchObject({
      response: { status: 404 },
    });
  });
});
