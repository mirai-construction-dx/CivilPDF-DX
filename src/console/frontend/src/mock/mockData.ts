/**
 * Mock data store for VITE_MOCK mode.
 *
 * Deterministic (seeded PRNG) construction-domain dummy data:
 * users, projects, documents, workflows, audit logs, consents.
 * Mutated in-memory by the mock adapter so CRUD flows work in demos.
 */
import type { UserResponse, UserRole, UserStatus } from "../api/users";
import type { DocumentResponse } from "../api/documents";
import type { ProjectResponse } from "../api/projects";
import type {
  WorkflowResponse,
  WorkflowListItem,
  ApprovalStep,
} from "../api/workflows";
import type { AuditLogItem } from "../api/auditLogs";
import type { ConsentRecord } from "../api/privacy";

/* ---------- deterministic PRNG (mulberry32) ---------- */
let seed = 20260612;
function rand(): number {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(rand() * arr.length)];
}
function randInt(min: number, max: number): number {
  return min + Math.floor(rand() * (max - min + 1));
}

/* ---------- fixed time base so data is stable across reloads ---------- */
const BASE = new Date("2026-06-12T09:00:00+09:00").getTime();
const DAY = 24 * 60 * 60 * 1000;
function daysAgo(days: number, jitterHours = 0): string {
  const jitter = jitterHours ? randInt(0, jitterHours) * 3600_000 : 0;
  return new Date(BASE - days * DAY - jitter).toISOString();
}

export function nowIso(): string {
  return new Date(BASE).toISOString();
}

let idCounter = 1000;
export function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter.toString(36)}`;
}

/* ---------- users ---------- */
const FAMILY = [
  "佐藤",
  "鈴木",
  "高橋",
  "田中",
  "伊藤",
  "渡辺",
  "山本",
  "中村",
  "小林",
  "加藤",
  "吉田",
  "山田",
  "佐々木",
  "山口",
  "松本",
  "井上",
];
const GIVEN = [
  "太郎",
  "健一",
  "直樹",
  "裕子",
  "美咲",
  "翔太",
  "大輔",
  "恵子",
  "誠",
  "由美",
  "拓也",
  "彩花",
  "亮",
  "千尋",
  "修平",
  "奈々",
];

function makeUser(i: number, role: UserRole, status: UserStatus): UserResponse {
  const fam = FAMILY[i % FAMILY.length];
  const giv = GIVEN[(i * 7) % GIVEN.length];
  const username = `user${String(i).padStart(3, "0")}`;
  return {
    id: `u-${String(i).padStart(3, "0")}`,
    email: `${username}@civilpdf.example.jp`,
    username,
    full_name: `${fam} ${giv}`,
    role,
    status,
    last_login: status === "active" ? daysAgo(randInt(0, 14), 12) : null,
    created_at: daysAgo(randInt(60, 380), 12),
  };
}

export const mockUsers: UserResponse[] = [
  {
    id: "u-000",
    email: "admin@civilpdf.example.jp",
    username: "admin",
    full_name: "管理者 太郎",
    role: "admin",
    status: "active",
    last_login: daysAgo(0),
    created_at: daysAgo(400),
  },
  ...Array.from({ length: 31 }, (_, i) => {
    const n = i + 1;
    const role: UserRole =
      n <= 3 ? "admin" : n <= 9 ? "manager" : n <= 24 ? "engineer" : "viewer";
    const status: UserStatus =
      n % 13 === 0 ? "suspended" : n % 9 === 0 ? "inactive" : "active";
    return makeUser(n, role, status);
  }),
];

/** Current session user in mock mode (admin persona). */
export const mockCurrentUser: UserResponse = mockUsers[0];

/* ---------- projects ---------- */
const PROJECT_NAMES = [
  "国道246号 橋梁耐震補強工事",
  "東名高速 トンネル照明更新工事",
  "多摩川 護岸改修工事",
  "中央環状線 舗装補修工事",
  "相模原市 下水道管渠更生工事",
  "横浜港 岸壁改良工事",
  "圏央道 法面保護工事",
  "荒川 河川敷整備工事",
  "第二東名 遮音壁設置工事",
  "市道12号線 電線共同溝工事",
  "県道51号 歩道拡幅工事",
  "利根川 樋管改築工事",
  "川崎市 雨水調整池築造工事",
  "青梅街道 無電柱化工事",
  "武蔵野線 跨線橋補修工事",
  "海老名IC ランプ改良工事",
  "都市計画道路3・4・12号線 街路築造工事",
  "相模川 床止め補修工事",
  "国道16号 交差点改良工事",
  "横須賀港 防波堤嵩上げ工事",
  "町田市 公共下水道枝線工事",
  "中央道 橋脚補強工事",
  "鶴見川 堤防強化工事",
  "厚木市 配水管布設替工事",
];

export const mockProjects: ProjectResponse[] = PROJECT_NAMES.map((name, i) => ({
  id: `p-${String(i + 1).padStart(3, "0")}`,
  name,
  code: `PRJ-2026-${String(i + 1).padStart(3, "0")}`,
  description:
    i % 3 === 0
      ? null
      : `${name}（発注者: ${pick(["国土交通省 関東地方整備局", "神奈川県 県土整備局", "東京都 建設局", "NEXCO中日本", "横浜市 道路局"])} / 工期: 2026年度）`,
  is_active: i % 6 !== 5,
  created_at: daysAgo(randInt(30, 360), 12),
}));

/* ---------- documents ---------- */
const DOC_TYPES = [
  "drawing",
  "specification",
  "report",
  "contract",
  "photo",
  "calculation",
] as const;
const DOC_STATUSES = [
  "draft",
  "pending_review",
  "approved",
  "rejected",
  "archived",
] as const;
const DOC_TITLE_PARTS: Record<(typeof DOC_TYPES)[number], string[]> = {
  drawing: [
    "平面図",
    "縦断図",
    "横断図",
    "構造一般図",
    "配筋詳細図",
    "仮設計画図",
  ],
  specification: [
    "特記仕様書",
    "施工計画書",
    "品質管理計画書",
    "安全管理計画書",
  ],
  report: [
    "月間工程報告書",
    "出来形管理報告書",
    "品質試験成績書",
    "安全巡視報告書",
  ],
  contract: ["工事請負契約書", "変更契約書", "下請負契約書"],
  photo: ["着手前写真台帳", "施工状況写真台帳", "完成写真台帳"],
  calculation: ["構造計算書", "数量計算書", "仮設構造計算書"],
};
const TAG_POOL = [
  "橋梁",
  "舗装",
  "耐震",
  "河川",
  "トンネル",
  "下水道",
  "電子納品",
  "CALS/EC",
  "第1工区",
  "第2工区",
  "夜間施工",
  "出来形",
  "品質管理",
  "安全",
];

export const mockDocuments: DocumentResponse[] = Array.from(
  { length: 150 },
  (_, i) => {
    const type = DOC_TYPES[i % DOC_TYPES.length];
    const project = mockProjects[i % mockProjects.length];
    const status = DOC_STATUSES[Math.floor(rand() * DOC_STATUSES.length)];
    const created = daysAgo(randInt(0, 180), 12);
    const seq = String(i + 1).padStart(3, "0");
    return {
      id: `d-${seq}`,
      title: `${project.name.slice(0, 12)} ${pick(DOC_TITLE_PARTS[type])} (Rev.${randInt(0, 4)})`,
      document_type: type,
      status,
      filename: `DOC_${project.code}_${seq}.pdf`,
      file_size: randInt(120, 48_000) * 1024,
      page_count: randInt(1, 120),
      is_pdfa: rand() > 0.25,
      tags: Array.from(
        new Set([pick(TAG_POOL), pick(TAG_POOL), pick(TAG_POOL)]),
      ),
      project_id: project.id,
      owner_id: pick(mockUsers).id,
      created_at: created,
      updated_at: rand() > 0.5 ? daysAgo(randInt(0, 30), 12) : null,
    };
  },
);

/* ---------- workflows ---------- */
function makeSteps(wfIndex: number, wfStatus: string): ApprovalStep[] {
  const count = randInt(1, 3);
  const approvers = mockUsers.filter(
    (u) => u.role === "manager" || u.role === "admin",
  );
  return Array.from({ length: count }, (_, s) => {
    const approver = approvers[(wfIndex + s) % approvers.length];
    let status = "pending";
    if (wfStatus === "approved") status = "approved";
    else if (wfStatus === "rejected")
      status = s === count - 1 ? "rejected" : "approved";
    const decided = status === "pending" ? null : daysAgo(randInt(0, 20), 12);
    return {
      id: `ws-${wfIndex}-${s}`,
      order: s + 1,
      approver_id: approver.id,
      status,
      comment:
        status === "approved"
          ? pick([
              "内容確認しました。承認します。",
              "図面整合性 OK。",
              "数量根拠を確認済み。",
              null as unknown as string,
            ])
          : status === "rejected"
            ? "配筋詳細図の寸法不整合があるため差戻します。"
            : null,
      decided_at: decided,
      approver: {
        id: approver.id,
        email: approver.email,
        username: approver.username,
        full_name: approver.full_name,
        role: approver.role,
      },
    };
  });
}

export const mockWorkflows: WorkflowResponse[] = Array.from(
  { length: 60 },
  (_, i) => {
    const doc = mockDocuments[(i * 2) % mockDocuments.length];
    const status =
      i % 3 === 0 ? "in_progress" : i % 3 === 1 ? "approved" : "rejected";
    const steps = makeSteps(i, status);
    return {
      id: `wf-${String(i + 1).padStart(3, "0")}`,
      document_id: doc.id,
      status,
      created_at: daysAgo(randInt(0, 90), 12),
      completed_at:
        status === "in_progress" ? null : daysAgo(randInt(0, 30), 12),
      steps,
    };
  },
);

export function toWorkflowListItem(wf: WorkflowResponse): WorkflowListItem {
  const doc = mockDocuments.find((d) => d.id === wf.document_id);
  return {
    id: wf.id,
    document_id: wf.document_id,
    document_title: doc?.title ?? "(削除済み文書)",
    status: wf.status,
    created_at: wf.created_at,
    completed_at: wf.completed_at,
    step_count: wf.steps.length,
    pending_step_count: wf.steps.filter((s) => s.status === "pending").length,
  };
}

/* ---------- audit logs ---------- */
const AUDIT_ACTIONS = [
  "login",
  "logout",
  "upload_document",
  "delete_document",
  "download_document",
  "create_project",
  "delete_project",
  "approve_step",
  "reject_step",
  "create_workflow",
  "create_user",
  "update_user",
  "apply_timestamp",
  "verify_timestamp",
  "electronic_delivery",
  "export_user_data",
  "request_deletion",
  "update_m365_config",
];
const AUDIT_RESOURCES: Record<string, string | null> = {
  login: null,
  logout: null,
  upload_document: "document",
  delete_document: "document",
  download_document: "document",
  create_project: "project",
  delete_project: "project",
  approve_step: "workflow",
  reject_step: "workflow",
  create_workflow: "workflow",
  create_user: "user",
  update_user: "user",
  apply_timestamp: "document",
  verify_timestamp: "document",
  electronic_delivery: "project",
  export_user_data: "user",
  request_deletion: "user",
  update_m365_config: "system",
};

export const mockAuditLogs: AuditLogItem[] = Array.from(
  { length: 400 },
  (_, i) => {
    const user = pick(mockUsers);
    const action = pick(AUDIT_ACTIONS);
    const resourceType = AUDIT_RESOURCES[action];
    const resourceId =
      resourceType === "document"
        ? pick(mockDocuments).id
        : resourceType === "project"
          ? pick(mockProjects).id
          : resourceType === "workflow"
            ? pick(mockWorkflows).id
            : resourceType === "user"
              ? pick(mockUsers).id
              : null;
    return {
      id: `al-${String(i + 1).padStart(4, "0")}`,
      user_id: user.id,
      action,
      resource_type: resourceType,
      resource_id: resourceId,
      detail: resourceId ? `${action} (${resourceId})` : action,
      ip_address: `192.168.${randInt(0, 4)}.${randInt(2, 254)}`,
      created_at: daysAgo(randInt(0, 60), 23),
      user: {
        id: user.id,
        email: user.email,
        username: user.username,
        full_name: user.full_name,
        role: user.role,
      },
    };
  },
).sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

/* ---------- consents ---------- */
export const mockConsents: ConsentRecord[] = mockUsers
  .slice(0, 12)
  .map((u, i) => ({
    id: `c-${String(i + 1).padStart(3, "0")}`,
    user_id: u.id,
    consent_type: pick(["privacy_policy", "data_processing", "cookie"]),
    version: "v1.2",
    granted: rand() > 0.1,
    ip_address: `192.168.0.${randInt(2, 254)}`,
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    source: "web",
    disclosed_purpose: "文書管理・承認ワークフロー運用のため",
    disclosed_retention_period: "契約終了後5年間",
    disclosed_third_parties: "なし",
    created_at: daysAgo(randInt(10, 200), 12),
  }));

/* ---------- minimal valid one-page PDF for preview/download ---------- */
const MOCK_PDF_SOURCE = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 90 >> stream
BT /F1 24 Tf 72 770 Td (CivilPDF-DX MOCK DOCUMENT) Tj 0 -36 Td (VITE_MOCK=1 sample) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
trailer << /Root 1 0 R >>
%%EOF`;

export function mockPdfBlob(): Blob {
  return new Blob([MOCK_PDF_SOURCE], { type: "application/pdf" });
}

/** Fake ZIP blob (valid empty-archive signature) for electronic delivery download. */
export function mockZipBlob(): Blob {
  return new Blob(
    [
      new Uint8Array([
        0x50, 0x4b, 0x05, 0x06, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0,
      ]),
    ],
    {
      type: "application/zip",
    },
  );
}
