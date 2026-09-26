import { type Page } from "@playwright/test";

// ── Shared fixtures ──────────────────────────────────────────────────────────
export const ADMIN_USER = {
  id: "e2e-admin",
  email: "admin@example.com",
  username: "admin",
  full_name: "管理者",
  role: "admin",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  last_login: null,
};

export const DOC_DRAWING = {
  id: "doc-1",
  title: "橋梁設計図",
  document_type: "drawing",
  status: "approved",
  filename: "bridge.pdf",
  file_size: 102400,
  page_count: 10,
  is_pdfa: true,
  tags: [],
  project_id: "proj-1",
  owner_id: "u1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: null,
};

export const DOC_REPORT = {
  ...DOC_DRAWING,
  id: "doc-2",
  title: "工事報告書",
  document_type: "report",
};

export const PROJECT = {
  id: "proj-1",
  name: "道路改良工事",
  code: "RD-001",
  description: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const TIMESTAMP_VERIFY = {
  document_id: "doc-1",
  valid: true,
  message: "OK",
  file_hash: "abc123def456abc123def456",
  verified_at: "2026-06-01T00:00:00Z",
};

const TIMESTAMP_APPLY = {
  document_id: "doc-1",
  file_hash: "abc123def456abc123def456",
  token_type: "local_hmac",
  tsa_url: "",
  verified_at: "2026-06-01T00:00:00Z",
  token_present: true,
};

const DELIVERY_READINESS = {
  ready: true,
  document_count: 3,
  pdfa_compliant_count: 3,
  non_pdfa_documents: [],
  warnings: [],
};

// The shell renders the workflow badge from /stats/ pending_approvals, so the
// value here is deliberately different from the old hardcoded "7".
export const STATS = {
  total_documents: 2,
  pending_approvals: 3,
  active_users: 5,
  approved_this_month: 1,
  uploaded_this_week: 1,
  total_file_size_bytes: 204800,
  by_type: { drawing: 1, report: 1 },
  by_status: { approved: 2 },
};

interface SetupOptions {
  documents?: unknown[];
  projects?: unknown[];
}

/**
 * Seed an authenticated session and intercept every backend call with
 * deterministic JSON. The app reads the token from localStorage on boot and
 * rehydrates the user via GET /auth/me, so RBAC-gated UI renders for an admin.
 */
export async function setupApp(
  page: Page,
  opts: SetupOptions = {},
): Promise<void> {
  const documents = opts.documents ?? [DOC_DRAWING];
  const projects = opts.projects ?? [PROJECT];

  await page.addInitScript(() => {
    localStorage.setItem("access_token", "e2e-access-token");
    localStorage.setItem("refresh_token", "e2e-refresh-token");
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    const json = (data: unknown) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(data),
      });

    if (pathname.endsWith("/auth/me")) return json(ADMIN_USER);
    if (pathname === "/api/v1/documents/" && method === "GET") {
      const includeMeta = new URL(request.url()).searchParams.get(
        "include_meta",
      );
      if (includeMeta === "true") {
        return json({
          items: documents,
          total: documents.length,
          page: 1,
          per_page: 20,
          pages: 1,
        });
      }
      return json(documents);
    }
    if (pathname.endsWith("/documents/trash") && method === "GET")
      return json([]);
    if (pathname === "/api/v1/projects/" && method === "GET")
      return json(projects);
    if (pathname === "/api/v1/notifications/unread-count")
      return json({ unread: 1 });
    if (pathname === "/api/v1/notifications/") {
      return json({
        items: [
          {
            id: "notif-1",
            notification_type: "workflow.assigned",
            title: "承認依頼が届いています",
            body: "文書「橋梁設計図」の承認が依頼されました",
            resource_type: "workflow",
            resource_id: "wf-1",
            is_read: false,
            created_at: "2026-08-12T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        pages: 1,
      });
    }
    if (pathname.endsWith("/timestamp/verify")) return json(TIMESTAMP_VERIFY);
    if (pathname.endsWith("/timestamp") && method === "POST")
      return json(TIMESTAMP_APPLY);
    if (pathname === "/api/v1/stats/") return json(STATS);
    if (pathname.endsWith("/electronic-delivery/check"))
      return json(DELIVERY_READINESS);
    if (pathname.endsWith("/electronic-delivery") && method === "POST") {
      return route.fulfill({
        contentType: "application/zip",
        body: "PK-e2e-zip-bytes",
      });
    }
    // Default: empty collection so unrelated views never hang on a pending call.
    return json([]);
  });
}
