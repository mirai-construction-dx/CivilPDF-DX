import { api } from "./client";

export interface AuditLogItem {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  detail: string | null;
  ip_address: string | null;
  created_at: string;
  user: {
    id: string;
    email: string;
    username: string;
    full_name: string;
    role: string;
  } | null;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AuditLogFilters {
  page?: number;
  per_page?: number;
  action?: string;
  resource_type?: string;
  user_id?: string;
}

export async function listAuditLogs(
  filters: AuditLogFilters = {},
): Promise<AuditLogListResponse> {
  const params = new URLSearchParams();
  if (filters.page) params.set("page", String(filters.page));
  if (filters.per_page) params.set("per_page", String(filters.per_page));
  if (filters.action) params.set("action", filters.action);
  if (filters.resource_type) params.set("resource_type", filters.resource_type);
  if (filters.user_id) params.set("user_id", filters.user_id);

  const res = await api.get<AuditLogListResponse>(
    `/audit-logs/?${params.toString()}`,
  );
  return res.data;
}

export async function downloadAuditLogsCsv(
  filters: Pick<AuditLogFilters, "action" | "resource_type" | "user_id"> = {},
): Promise<void> {
  const res = await api.get<Blob>("/audit-logs/export.csv", {
    params: filters,
    responseType: "blob",
  });
  const disposition = res.headers["content-disposition"] as string | undefined;
  const match = disposition?.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? "audit-logs.csv";
  const url = URL.createObjectURL(res.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
