/**
 * Axios adapter for VITE_MOCK mode.
 *
 * Replaces network I/O for the shared axios instance: every /api/v1/*
 * request is routed here and answered from the in-memory mock store,
 * so the whole WebUI runs without a backend. Mutations (create/delete/
 * approve...) update the store so demo flows behave realistically.
 */
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import {
  mockUsers,
  mockCurrentUser,
  mockProjects,
  mockDocuments,
  mockWorkflows,
  mockAuditLogs,
  mockConsents,
  toWorkflowListItem,
  nextId,
  nowIso,
  mockPdfBlob,
  mockZipBlob,
} from "./mockData";
import type { DocumentResponse } from "../api/documents";
import type { WorkflowResponse } from "../api/workflows";
import type { UserRole, UserStatus } from "../api/users";

const LATENCY_MS = 150;

function respond(
  config: InternalAxiosRequestConfig,
  data: unknown,
  status = 200,
): AxiosResponse {
  return {
    data,
    status,
    statusText: status === 200 ? "OK" : String(status),
    headers: {},
    config,
  } as AxiosResponse;
}

function httpError(
  config: InternalAxiosRequestConfig,
  status: number,
  detail: string,
): never {
  const error = new Error(
    `Mock ${status}: ${config.method?.toUpperCase()} ${detail}`,
  ) as Error & {
    response: { status: number; data: unknown };
    config: InternalAxiosRequestConfig;
  };
  error.response = { status, data: { detail } };
  error.config = config;
  throw error;
}

function notFound(config: InternalAxiosRequestConfig, path: string): never {
  httpError(config, 404, `Not found (mock): ${path}`);
}

const USER_ROLES: readonly UserRole[] = [
  "admin",
  "manager",
  "engineer",
  "viewer",
];
const USER_STATUSES: readonly UserStatus[] = [
  "active",
  "inactive",
  "suspended",
];

/** Parse path (without /api/v1 prefix) and merged query params. */
function parseRequest(config: InternalAxiosRequestConfig): {
  path: string;
  query: URLSearchParams;
} {
  const raw = `${config.baseURL ?? ""}${config.url ?? ""}`;
  const url = new URL(raw, "http://mock.local");
  const query = url.searchParams;
  if (config.params) {
    for (const [k, v] of Object.entries(
      config.params as Record<string, unknown>,
    )) {
      if (v !== undefined && v !== null) query.set(k, String(v));
    }
  }
  let path = url.pathname.replace(/^\/api\/v1/, "");
  if (path.length > 1) path = path.replace(/\/+$/, "");
  return { path, query };
}

function parseBody(
  config: InternalAxiosRequestConfig,
): Record<string, unknown> {
  const d = config.data;
  if (d == null) return {};
  if (typeof d === "string") {
    try {
      return JSON.parse(d) as Record<string, unknown>;
    } catch {
      return Object.fromEntries(new URLSearchParams(d));
    }
  }
  if (d instanceof URLSearchParams) return Object.fromEntries(d);
  if (typeof FormData !== "undefined" && d instanceof FormData) {
    const out: Record<string, unknown> = {};
    d.forEach((v, k) => {
      out[k] = v;
    });
    return out;
  }
  return d as Record<string, unknown>;
}

const TOKENS = {
  access_token: "mock-access-token",
  refresh_token: "mock-refresh-token",
  token_type: "bearer",
};

const _APP_VER = "1.2.0";
const _mockPkg = (
  id: string,
  platform: string,
  format: string,
  label: string,
  filename: string,
  size: string,
) => ({
  id,
  platform,
  format,
  label,
  filename,
  version: _APP_VER,
  size_label: size,
  sha256: null,
  download_path: `/api/v1/apps/download/${id}`,
  available: false,
});

const MOCK_APPS_RELEASES = {
  stable_version: `v${_APP_VER}`,
  packages: [
    _mockPkg(
      "win-exe",
      "windows",
      "exe",
      "インストーラー (.exe / NSIS)",
      "CivilPDF.Editor_1.2.0_x64-setup.exe",
      "約 1.9 MB",
    ),
    _mockPkg(
      "win-msi",
      "windows",
      "msi",
      "インストーラー (.msi)",
      "CivilPDF.Editor_1.2.0_x64_en-US.msi",
      "約 2.4 MB",
    ),
  ],
  channels: [
    {
      id: "stable",
      label: "Stable",
      version: `v${_APP_VER}`,
      release_date: "2026-06-22",
      description:
        "安定版。テキスト編集モード（v1.2.0 新機能）・注釈（Phase A）・検索/しおり/透かし/メタデータ（Phase B）・画像→PDF/比較/フォーム（Phase C）を搭載。未署名ビルドのため OS のセキュリティ警告が表示される場合があります。",
      user_count: 0,
    },
  ],
  pending_platforms: [
    {
      platform: "macos",
      label: "macOS",
      status: "pending",
      note: "後日対応（ペンディング）。現在は Windows 版のみ提供しています",
    },
  ],
};

const MOCK_APPS_RELEASE_NOTES = {
  notes: [
    {
      version: _APP_VER,
      channel: "stable",
      release_date: "2026-06-22",
      summary:
        "v1.2.0 安定版 — テキスト編集モードを追加（注釈・検索・文書加工・変換機能を継続搭載）",
      items: [
        {
          type: "FEAT",
          text: "テキスト編集モード（v1.2.0: PDF 上のテキストを直接編集・PDF へ焼き込み）",
        },
        {
          type: "FEAT",
          text: "注釈（Phase A: ハイライト・下線・取消線・付箋・手書き・消去）",
        },
        {
          type: "FEAT",
          text: "テキスト検索・しおり・透かし・メタデータ編集（Phase B）",
        },
        {
          type: "FEAT",
          text: "画像→PDF・PDF 比較・フォームフィールド確認（Phase C）",
        },
        {
          type: "NOTE",
          text: "未署名ビルド。Windows SmartScreen の警告が表示される場合があります",
        },
      ],
      highlights: "v1.2.0 — テキスト編集モード搭載の安定版（mock）",
    },
  ],
};

const MOCK_APPS_BUILD_INFO = {
  product: "CivilPDF Editor Client",
  stable_version: `v${_APP_VER}`,
  build_number: `${_APP_VER}+build.mock`,
  git_commit: "mock123",
  build_date: "2026-04-28",
  channel: "stable",
  runtime: "Tauri v2（システムの WebView を利用）",
  supported_os: ["Windows 10 / 11 (64bit)"],
  min_supported_version: _APP_VER,
};

function handle(config: InternalAxiosRequestConfig): unknown {
  const method = (config.method ?? "get").toLowerCase();
  const { path, query } = parseRequest(config);
  const body = parseBody(config);

  /* ----- auth ----- */
  if (path === "/auth/token" && method === "post") return TOKENS;
  if (path === "/auth/refresh" && method === "post") return TOKENS;
  if (path === "/auth/me" && method === "get") return mockCurrentUser;
  if (path === "/auth/me" && method === "patch") {
    if (typeof body.full_name === "string")
      mockCurrentUser.full_name = body.full_name;
    return mockCurrentUser;
  }
  if (path === "/auth/me/password" && method === "post")
    return { detail: "password changed (mock)" };

  /* ----- apps (PDF Editor 配信) ----- */
  if (path === "/apps/releases" && method === "get") return MOCK_APPS_RELEASES;
  if (path === "/apps/release-notes" && method === "get") {
    const ch = query.get("channel");
    return {
      notes: ch
        ? MOCK_APPS_RELEASE_NOTES.notes.filter((n) => n.channel === ch)
        : MOCK_APPS_RELEASE_NOTES.notes,
    };
  }
  if (path === "/apps/build-info" && method === "get")
    return MOCK_APPS_BUILD_INFO;
  {
    const dm = path.match(/^\/apps\/download\/([^/]+)$/);
    if (dm && method === "get") {
      const pkg = MOCK_APPS_RELEASES.packages.find((p) => p.id === dm[1]);
      if (!pkg) httpError(config, 404, "Package not found");
      return {
        url: null,
        sha256: pkg!.sha256,
        message: "ダウンロードリンクは近日公開予定です（mock）",
      };
    }
  }

  /* ----- M365 ----- */
  if (path === "/auth/m365/login" && method === "post") {
    return {
      ...TOKENS,
      m365_user: {
        displayName: mockCurrentUser.full_name,
        mail: String(body.email ?? mockCurrentUser.email),
        userPrincipalName: String(body.email ?? mockCurrentUser.email),
        id: "m365-mock-object-id",
      },
      is_new_user: false,
    };
  }
  if (path === "/auth/m365/test-connection" && method === "post") {
    return {
      ok: true,
      tenant_name: "CivilPDF Mock Tenant",
      user_count: mockUsers.length,
    };
  }
  if (path === "/auth/m365/config" && method === "get") {
    return {
      tenantId: "00000000-0000-0000-0000-0000mocktenant",
      clientId: "00000000-0000-0000-0000-0000mockclient",
      enabled: true,
      clientSecretSet: true,
    };
  }
  if (path === "/auth/m365/config" && method === "put") return null;
  if (path === "/users/m365/lookup" && method === "get") {
    return {
      exists_in_tenant: true,
      display_name: "モック ユーザー",
      user_principal_name: query.get("email") ?? "",
      account_enabled: true,
    };
  }

  /* ----- documents ----- */
  if (path === "/documents" && method === "get") {
    let docs = [...mockDocuments];
    const projectId = query.get("project_id");
    const docType = query.get("document_type");
    const status = query.get("status");
    if (projectId) docs = docs.filter((d) => d.project_id === projectId);
    if (docType) docs = docs.filter((d) => d.document_type === docType);
    if (status) docs = docs.filter((d) => d.status === status);
    return docs;
  }
  if (path === "/documents" && method === "post") {
    const file = body.file as File | undefined;
    const doc: DocumentResponse = {
      id: nextId("d"),
      title: String(body.title ?? "新規アップロード文書"),
      document_type: String(body.document_type ?? "report"),
      status: "draft",
      filename: file?.name ?? "uploaded.pdf",
      file_size: file?.size ?? 1024 * 256,
      page_count: 1,
      is_pdfa: false,
      tags: [],
      project_id: String(body.project_id ?? mockProjects[0].id),
      owner_id: mockCurrentUser.id,
      created_at: nowIso(),
      updated_at: null,
    };
    mockDocuments.unshift(doc);
    return doc;
  }

  let m = path.match(/^\/documents\/([^/]+)$/);
  if (m && method === "delete") {
    const idx = mockDocuments.findIndex((d) => d.id === m![1]);
    if (idx >= 0) mockDocuments.splice(idx, 1);
    return null;
  }
  m = path.match(/^\/documents\/([^/]+)\/download$/);
  if (m && method === "get") return mockPdfBlob();
  m = path.match(/^\/documents\/([^/]+)\/timestamp$/);
  if (m && method === "post") {
    return {
      document_id: m[1],
      file_hash: "a3f5".repeat(16),
      token_type: "rfc3161",
      tsa_url: "https://freetsa.org/tsr",
      verified_at: nowIso(),
      token_present: true,
    };
  }
  m = path.match(/^\/documents\/([^/]+)\/timestamp\/verify$/);
  if (m && method === "get") {
    return {
      document_id: m[1],
      valid: true,
      message: "タイムスタンプは有効です（モック検証）",
      file_hash: "a3f5".repeat(16),
      verified_at: nowIso(),
    };
  }

  /* ----- projects ----- */
  if (path === "/projects" && method === "get") return [...mockProjects];
  if (path === "/projects" && method === "post") {
    const project = {
      id: nextId("p"),
      name: String(body.name ?? "新規プロジェクト"),
      code: String(body.code ?? `PRJ-2026-${nextId("c")}`),
      description: (body.description as string | undefined) ?? null,
      is_active: true,
      created_at: nowIso(),
    };
    mockProjects.unshift(project);
    return project;
  }
  m = path.match(/^\/projects\/([^/]+)$/);
  if (m && method === "get") {
    const project = mockProjects.find((p) => p.id === m![1]);
    if (!project) notFound(config, path);
    return project;
  }
  if (m && method === "delete") {
    const idx = mockProjects.findIndex((p) => p.id === m![1]);
    if (idx >= 0) mockProjects.splice(idx, 1);
    return null;
  }
  m = path.match(/^\/projects\/([^/]+)\/electronic-delivery\/check$/);
  if (m && method === "get") {
    const docs = mockDocuments.filter((d) => d.project_id === m![1]);
    const nonPdfa = docs.filter((d) => !d.is_pdfa);
    return {
      ready: nonPdfa.length === 0,
      document_count: docs.length,
      pdfa_compliant_count: docs.length - nonPdfa.length,
      non_pdfa_documents: nonPdfa
        .slice(0, 10)
        .map((d) => ({ id: d.id, title: d.title, filename: d.filename })),
      unreadable_documents: [],
      warnings:
        nonPdfa.length > 0
          ? [`PDF/A 非準拠の文書が ${nonPdfa.length} 件あります（モック判定）`]
          : [],
    };
  }
  m = path.match(/^\/projects\/([^/]+)\/electronic-delivery$/);
  if (m && method === "post") return mockZipBlob();

  /* ----- workflows ----- */
  if (path === "/workflows" && method === "get")
    return mockWorkflows.map(toWorkflowListItem);
  if (path === "/workflows" && method === "post") {
    const approverIds = (body.approver_ids as string[] | undefined) ?? [
      mockUsers[1].id,
    ];
    const wf: WorkflowResponse = {
      id: nextId("wf"),
      document_id: String(body.document_id ?? mockDocuments[0].id),
      status: "in_progress",
      created_at: nowIso(),
      completed_at: null,
      steps: approverIds.map((approverId, i) => {
        const approver =
          mockUsers.find((u) => u.id === approverId) ?? mockUsers[1];
        return {
          id: nextId("ws"),
          order: i + 1,
          approver_id: approver.id,
          status: "pending",
          comment: null,
          decided_at: null,
          approver: {
            id: approver.id,
            email: approver.email,
            username: approver.username,
            full_name: approver.full_name,
            role: approver.role,
          },
        };
      }),
    };
    mockWorkflows.unshift(wf);
    return wf;
  }
  m = path.match(/^\/workflows\/([^/]+)$/);
  if (m && method === "get") {
    const wf = mockWorkflows.find((w) => w.id === m![1]);
    if (!wf) notFound(config, path);
    return wf;
  }
  m = path.match(/^\/workflows\/([^/]+)\/steps\/([^/]+)\/decide$/);
  if (m && method === "post") {
    const wf = mockWorkflows.find((w) => w.id === m![1]);
    if (!wf) notFound(config, path);
    const step = wf!.steps.find((s) => s.id === m![2]);
    if (!step) notFound(config, path);
    if (body.decision !== "approve" && body.decision !== "reject") {
      httpError(
        config,
        422,
        `Invalid decision: ${String(body.decision)} (expected approve|reject)`,
      );
    }
    step!.status = body.decision === "approve" ? "approved" : "rejected";
    step!.comment = (body.comment as string | undefined) ?? null;
    step!.decided_at = nowIso();
    if (body.decision === "reject") {
      wf!.status = "rejected";
      wf!.completed_at = nowIso();
    } else if (wf!.steps.every((s) => s.status === "approved")) {
      wf!.status = "approved";
      wf!.completed_at = nowIso();
    }
    return wf;
  }

  /* ----- users ----- */
  if (path === "/users" && method === "get") return [...mockUsers];
  if (path === "/users" && method === "post") {
    if (
      body.role !== undefined &&
      !USER_ROLES.includes(body.role as UserRole)
    ) {
      httpError(config, 422, `Invalid role: ${String(body.role)}`);
    }
    const user = {
      id: nextId("u"),
      email: String(body.email ?? "new@civilpdf.example.jp"),
      username: String(body.username ?? "newuser"),
      full_name: String(body.full_name ?? "新規 ユーザー"),
      role: (body.role as UserRole | undefined) ?? "viewer",
      status: "active" as UserStatus,
      last_login: null,
      created_at: nowIso(),
    };
    mockUsers.push(user);
    return user;
  }
  m = path.match(/^\/users\/([^/]+)$/);
  if (m && method === "patch") {
    const user = mockUsers.find((u) => u.id === m![1]);
    if (!user) notFound(config, path);
    if (typeof body.full_name === "string") user!.full_name = body.full_name;
    if (body.role !== undefined) {
      if (!USER_ROLES.includes(body.role as UserRole))
        httpError(config, 422, `Invalid role: ${String(body.role)}`);
      user!.role = body.role as UserRole;
    }
    if (body.status !== undefined) {
      if (!USER_STATUSES.includes(body.status as UserStatus))
        httpError(config, 422, `Invalid status: ${String(body.status)}`);
      user!.status = body.status as UserStatus;
    }
    return user;
  }
  if (m && method === "delete") {
    const idx = mockUsers.findIndex((u) => u.id === m![1]);
    if (idx > 0) mockUsers.splice(idx, 1);
    return null;
  }

  /* ----- audit logs ----- */
  if (path === "/audit-logs" && method === "get") {
    let items = [...mockAuditLogs];
    const action = query.get("action");
    const resourceType = query.get("resource_type");
    const userId = query.get("user_id");
    if (action) items = items.filter((a) => a.action === action);
    if (resourceType)
      items = items.filter((a) => a.resource_type === resourceType);
    if (userId) items = items.filter((a) => a.user_id === userId);
    const page = Number(query.get("page") ?? "1");
    const perPage = Number(query.get("per_page") ?? "50");
    const total = items.length;
    return {
      items: items.slice((page - 1) * perPage, page * perPage),
      total,
      page,
      per_page: perPage,
      pages: Math.max(1, Math.ceil(total / perPage)),
    };
  }

  /* ----- stats ----- */
  if (path === "/stats" && method === "get") {
    const byType: Record<string, number> = {};
    const byStatus: Record<string, number> = {};
    for (const d of mockDocuments) {
      byType[d.document_type] = (byType[d.document_type] ?? 0) + 1;
      byStatus[d.status] = (byStatus[d.status] ?? 0) + 1;
    }
    return {
      total_documents: mockDocuments.length,
      pending_approvals: mockWorkflows.filter((w) => w.status === "in_progress")
        .length,
      active_users: mockUsers.filter((u) => u.status === "active").length,
      approved_this_month: mockWorkflows.filter((w) => w.status === "approved")
        .length,
      uploaded_this_week: Math.min(mockDocuments.length, 17),
      total_file_size_bytes: mockDocuments.reduce(
        (acc, d) => acc + d.file_size,
        0,
      ),
      by_type: byType,
      by_status: byStatus,
    };
  }

  if (path === "/stats/dx-sync" && method === "get") {
    return {
      total: 128,
      success: 126,
      error: 2,
      success_rate_total: 98.44,
      success_rate_30d: 99.2,
      recent_30d: { total: 125, success: 124, error: 1 },
      by_error_kind_30d: { rbac: 1 },
      monthly: [
        { month: "2026-03", success: 98, error: 1 },
        { month: "2026-04", success: 110, error: 1 },
        { month: "2026-05", success: 121, error: 0 },
        { month: "2026-06", success: 118, error: 2 },
        { month: "2026-07", success: 125, error: 1 },
        { month: "2026-08", success: 124, error: 1 },
      ],
    };
  }

  /* ----- AI ----- */
  m = path.match(/^\/ai\/documents\/([^/]+)\/classify$/);
  if (m && method === "post") {
    const doc = mockDocuments.find((d) => d.id === m![1]);
    return {
      document_id: m[1],
      drawing_type: doc?.document_type === "drawing" ? "構造一般図" : null,
      project_type: "道路橋梁",
      confidence: 0.93,
      tags: doc?.tags ?? ["橋梁", "耐震"],
      classified_at: nowIso(),
      model: "claude-haiku-4-5 (mock)",
    };
  }
  m = path.match(/^\/ai\/documents\/([^/]+)\/extract$/);
  if (m && method === "post") {
    return {
      document_id: m[1],
      extracted_at: nowIso(),
      model: "claude-haiku-4-5 (mock)",
      data: {
        construction_name: "国道246号 橋梁耐震補強工事（第1工区）",
        contractor: "株式会社シビル建設",
        site_location: "神奈川県川崎市高津区",
        amount: "¥128,500,000",
        start_date: "2026-04-01",
        end_date: "2027-03-15",
        responsible_person: "監理技術者 佐藤 健一",
        checklist_items: [
          "施工計画書 提出済",
          "品質管理計画 承認済",
          "安全管理体制 確認済",
        ],
      },
    };
  }
  m = path.match(/^\/ai\/documents\/([^/]+)\/summary$/);
  if (m && method === "get") {
    return {
      document_id: m[1],
      summary:
        "本書は橋梁耐震補強工事に関する施工計画書である。落橋防止装置の設置、支承交換、炭素繊維巻立て補強を主要工種とし、夜間片側交互通行規制下での施工手順、品質管理基準（出来形・写真管理含む）、安全管理体制を規定している。（モック要約）",
      summarized_at: nowIso(),
      model: "claude-haiku-4-5 (mock)",
    };
  }

  /* ----- search ----- */
  if (path === "/search/documents" && method === "get") {
    const q = query.get("q") ?? "";
    const mode = (query.get("mode") ?? "keyword") as "keyword" | "semantic";
    const limit = Number(query.get("limit") ?? "20");
    const hits = mockDocuments
      .filter(
        (d) => !q || d.title.includes(q) || d.tags.some((t) => t.includes(q)),
      )
      .slice(0, limit)
      .map((d, i) => ({
        document_id: d.id,
        title: d.title,
        document_type: d.document_type,
        status: d.status,
        project_id: d.project_id,
        snippet: `…${d.title} に関する記載。${d.tags.join("・")} 関連。（モック抜粋）…`,
        score: Math.round((1 - i * 0.03) * 100) / 100,
        tags: d.tags,
      }));
    return {
      query: q,
      mode,
      expanded_terms:
        mode === "semantic"
          ? [q, "耐震補強", "橋梁点検", "補修設計"].filter(Boolean)
          : [],
      total: hits.length,
      hits,
    };
  }
  if (path === "/search/documents/reindex" && method === "post") {
    return { indexed: mockDocuments.length, status: "completed" };
  }
  if (path === "/search/documents/suggest" && method === "get") {
    const q = query.get("q") ?? "";
    return ["橋梁", "耐震補強", "施工計画書", "出来形管理", "電子納品"].filter(
      (t) => !q || t.includes(q),
    );
  }

  /* ----- privacy ----- */
  m = path.match(/^\/privacy\/users\/([^/]+)\/data$/);
  if (m && method === "delete") {
    return {
      user_id: m[1],
      documents_marked: mockDocuments.filter((d) => d.owner_id === m![1])
        .length,
      deletion_requested_at: nowIso(),
      audit_log_id: nextId("al"),
    };
  }
  m = path.match(/^\/privacy\/users\/([^/]+)\/export$/);
  if (m && method === "get") {
    const user = mockUsers.find((u) => u.id === m![1]) ?? mockCurrentUser;
    return {
      user_id: user.id,
      email: user.email,
      username: user.username,
      full_name: user.full_name,
      role: user.role,
      status: user.status,
      created_at: user.created_at,
      documents: mockDocuments
        .filter((d) => d.owner_id === user.id)
        .map((d) => ({
          id: d.id,
          title: d.title,
          document_type: d.document_type,
          filename: d.filename,
          file_size: d.file_size,
          created_at: d.created_at,
          deletion_requested_at: null,
        })),
      consent_records: mockConsents.filter((c) => c.user_id === user.id),
      exported_at: nowIso(),
    };
  }
  if (path === "/privacy/consent" && method === "post") {
    const rec = {
      id: nextId("c"),
      user_id: mockCurrentUser.id,
      consent_type: String(body.consent_type ?? "privacy_policy"),
      version: String(body.version ?? "v1.2"),
      granted: Boolean(body.granted),
      ip_address: "192.168.0.10",
      user_agent: "Mozilla/5.0 (mock)",
      source: (body.source as string | undefined) ?? "web",
      disclosed_purpose: (body.disclosed_purpose as string | undefined) ?? null,
      disclosed_retention_period:
        (body.disclosed_retention_period as string | undefined) ?? null,
      disclosed_third_parties:
        (body.disclosed_third_parties as string | undefined) ?? null,
      created_at: nowIso(),
    };
    mockConsents.push(rec);
    return rec;
  }
  m = path.match(/^\/privacy\/consent\/([^/]+)$/);
  if (m && method === "get")
    return mockConsents.filter((c) => c.user_id === m![1]);

  notFound(config, path);
}

export async function mockAdapter(
  config: InternalAxiosRequestConfig,
): Promise<AxiosResponse> {
  await new Promise((r) => setTimeout(r, LATENCY_MS));
  const data = handle(config);
  return respond(config, data);
}
