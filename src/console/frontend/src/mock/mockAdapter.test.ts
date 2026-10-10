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

  /* ---------- WEB-WF-005 差戻し（return） / 再申請（resubmit） ---------- */

  it("returns a step then resubmits the workflow", async () => {
    const created = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[0].id,
          approver_ids: [mockUsers[1].id, mockUsers[2].id],
        }),
      }),
    );
    const wf = mockWorkflows.find((w) => w.id === created.data.id)!;
    const doc = mockDocuments.find((d) => d.id === mockDocuments[0].id)!;
    const first = wf.steps[0];

    const returned = await mockAdapter(
      req("post", `/workflows/${wf.id}/steps/${first.id}/decide`, {
        data: JSON.stringify({ decision: "return", comment: "寸法不整合" }),
      }),
    );
    expect(returned.data.status).toBe("returned");
    expect(first.status).toBe("returned");
    expect(first.comment).toBe("寸法不整合");
    expect(first.decided_at).not.toBeNull();
    expect(wf.completed_at).toBeNull();
    expect(doc.status).toBe("draft");

    const resubmitted = await mockAdapter(
      req("post", `/workflows/${wf.id}/resubmit`),
    );
    expect(resubmitted.data.status).toBe("in_progress");
    expect(wf.status).toBe("in_progress");
    expect(wf.completed_at).toBeNull();
    expect(wf.steps.every((s) => s.status === "pending")).toBe(true);
    expect(wf.steps.every((s) => s.comment === null)).toBe(true);
    expect(wf.steps.every((s) => s.decided_at === null)).toBe(true);
    expect(doc.status).toBe("pending_review");
  });

  it("rejects resubmit for a workflow that is not returned with 409", async () => {
    const wf = mockWorkflows.find((w) => w.status === "approved")!;
    await expect(
      mockAdapter(req("post", `/workflows/${wf.id}/resubmit`)),
    ).rejects.toMatchObject({
      response: { status: 409 },
    });
  });

  it("rejects return when a previous step is already approved with 409", async () => {
    const created = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[1].id,
          approver_ids: [mockUsers[1].id, mockUsers[2].id],
        }),
      }),
    );
    const wf = mockWorkflows.find((w) => w.id === created.data.id)!;
    wf.steps[0].status = "approved";

    await expect(
      mockAdapter(
        req("post", `/workflows/${wf.id}/steps/${wf.steps[1].id}/decide`, {
          data: JSON.stringify({ decision: "return", comment: null }),
        }),
      ),
    ).rejects.toMatchObject({
      response: { status: 409 },
    });
    expect(wf.steps[1].status).toBe("pending");
  });

  it("rejects decisions while the workflow is returned with 409", async () => {
    const created = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[2].id,
          approver_ids: [mockUsers[1].id, mockUsers[2].id],
        }),
      }),
    );
    const wf = mockWorkflows.find((w) => w.id === created.data.id)!;
    const [first, second] = wf.steps;

    await mockAdapter(
      req("post", `/workflows/${wf.id}/steps/${first.id}/decide`, {
        data: JSON.stringify({ decision: "return", comment: "要修正" }),
      }),
    );
    expect(wf.status).toBe("returned");

    await expect(
      mockAdapter(
        req("post", `/workflows/${wf.id}/steps/${second.id}/decide`, {
          data: JSON.stringify({ decision: "approve" }),
        }),
      ),
    ).rejects.toMatchObject({
      response: {
        status: 409,
        data: {
          detail: "Workflow was returned; resubmit it before deciding steps",
        },
      },
    });
    expect(second.status).toBe("pending");

    // 再申請後は通常どおり decide できる
    await mockAdapter(req("post", `/workflows/${wf.id}/resubmit`));
    const approved = await mockAdapter(
      req("post", `/workflows/${wf.id}/steps/${first.id}/decide`, {
        data: JSON.stringify({ decision: "approve" }),
      }),
    );
    expect(approved.data.status).toBe("in_progress");
    expect(first.status).toBe("approved");
  });

  it("rejects deciding an already-decided step with 409", async () => {
    const created = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[3].id,
          approver_ids: [mockUsers[1].id, mockUsers[2].id],
        }),
      }),
    );
    const wf = mockWorkflows.find((w) => w.id === created.data.id)!;
    const [first, second] = wf.steps;
    const decide = (stepId: string, decision: string) =>
      mockAdapter(
        req("post", `/workflows/${wf.id}/steps/${stepId}/decide`, {
          data: JSON.stringify({ decision, comment: null }),
        }),
      );

    // approved 済みステップへの再決定
    await decide(first.id, "approve");
    await expect(decide(first.id, "approve")).rejects.toMatchObject({
      response: { status: 409, data: { detail: "Step already decided" } },
    });
    expect(first.status).toBe("approved");

    // rejected 済みステップへの再決定
    await decide(second.id, "reject");
    await expect(decide(second.id, "reject")).rejects.toMatchObject({
      response: { status: 409, data: { detail: "Step already decided" } },
    });
    expect(second.status).toBe("rejected");

    // returned 済みステップへの再決定は「二重決定」が先に返る（差戻し中の 409 より前）
    const returnedCreated = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[4].id,
          approver_ids: [mockUsers[1].id],
        }),
      }),
    );
    const returnedWf = mockWorkflows.find(
      (w) => w.id === returnedCreated.data.id,
    )!;
    const returnedStep = returnedWf.steps[0];
    await mockAdapter(
      req(
        "post",
        `/workflows/${returnedWf.id}/steps/${returnedStep.id}/decide`,
        {
          data: JSON.stringify({ decision: "return", comment: "要修正" }),
        },
      ),
    );
    expect(returnedWf.status).toBe("returned");

    await expect(
      mockAdapter(
        req(
          "post",
          `/workflows/${returnedWf.id}/steps/${returnedStep.id}/decide`,
          { data: JSON.stringify({ decision: "return" }) },
        ),
      ),
    ).rejects.toMatchObject({
      response: { status: 409, data: { detail: "Step already decided" } },
    });
    expect(returnedStep.status).toBe("returned");
  });

  it("rejects approve/reject until previous steps are approved", async () => {
    const created = await mockAdapter(
      req("post", "/workflows/", {
        data: JSON.stringify({
          document_id: mockDocuments[5].id,
          approver_ids: [mockUsers[1].id, mockUsers[2].id],
        }),
      }),
    );
    const wf = mockWorkflows.find((w) => w.id === created.data.id)!;
    const [first, second] = wf.steps;
    const decide = (stepId: string, decision: string) =>
      mockAdapter(
        req("post", `/workflows/${wf.id}/steps/${stepId}/decide`, {
          data: JSON.stringify({ decision, comment: null }),
        }),
      );

    // 先行（step1）が未承認のうちは step2 を承認できない
    await expect(decide(second.id, "approve")).rejects.toMatchObject({
      response: {
        status: 409,
        data: { detail: "Previous approval steps must be approved first" },
      },
    });
    expect(second.status).toBe("pending");

    // 却下も同じ順序ガードで拒否される
    await expect(decide(second.id, "reject")).rejects.toMatchObject({
      response: {
        status: 409,
        data: { detail: "Previous approval steps must be approved first" },
      },
    });
    expect(second.status).toBe("pending");
    expect(wf.status).toBe("in_progress");

    // step1 を承認すれば step2 を承認できる（全ステップ承認で wf=approved）
    await decide(first.id, "approve");
    const decided = await decide(second.id, "approve");
    expect(decided.data.status).toBe("approved");
    expect(second.status).toBe("approved");
    expect(wf.completed_at).not.toBeNull();
  });

  it("validates the decision body (422) before resolving wf/step (404)", async () => {
    // 不正 decision × 不在 step → body 検証が先で 422
    await expect(
      mockAdapter(
        req("post", "/workflows/wf-001/steps/no-such-step/decide", {
          data: JSON.stringify({ decision: "maybe" }),
        }),
      ),
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: {
          detail: "Invalid decision: maybe (expected approve|reject|return)",
        },
      },
    });

    // 不正 decision × 不在 workflow でも 422
    await expect(
      mockAdapter(
        req("post", "/workflows/no-such-wf/steps/no-such-step/decide", {
          data: JSON.stringify({ decision: "maybe" }),
        }),
      ),
    ).rejects.toMatchObject({
      response: { status: 422 },
    });

    // 正しい decision なら従来どおり 404
    await expect(
      mockAdapter(
        req("post", "/workflows/wf-001/steps/no-such-step/decide", {
          data: JSON.stringify({ decision: "approve" }),
        }),
      ),
    ).rejects.toMatchObject({
      response: { status: 404 },
    });
  });
});
