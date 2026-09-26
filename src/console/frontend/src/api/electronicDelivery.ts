import { api } from "./client";

export interface NonPdfaDocumentInfo {
  id: string;
  title: string;
  filename: string;
}

export interface UnreadableDocumentInfo extends NonPdfaDocumentInfo {
  reason: string;
}

export interface DeliveryReadinessResponse {
  ready: boolean;
  document_count: number;
  pdfa_compliant_count: number;
  non_pdfa_documents: NonPdfaDocumentInfo[];
  // Documents whose stored file cannot be read. They make ready=false and the
  // backend refuses to package them unless allow_unreadable is requested.
  unreadable_documents?: UnreadableDocumentInfo[];
  warnings: string[];
}

export async function checkDeliveryReadiness(
  projectId: string,
): Promise<DeliveryReadinessResponse> {
  const res = await api.get<DeliveryReadinessResponse>(
    `/projects/${projectId}/electronic-delivery/check`,
  );
  return res.data;
}

export async function downloadDeliveryZip(
  projectId: string,
  projectCode: string,
): Promise<void> {
  const res = await api.post<Blob>(
    `/projects/${projectId}/electronic-delivery`,
    {},
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const code = projectCode
    .replace(/[^A-Za-z0-9_]/g, "_")
    .toUpperCase()
    .slice(0, 16);
  a.download = `${code}_${date}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Extract the server's explanation from a failed delivery request.
 *
 * The download uses `responseType: 'blob'`, so an error body also arrives as a
 * Blob and has to be read as text before the JSON detail can be shown. Without
 * this the operator only saw a generic failure and could not tell which
 * document blocked the package (the backend answers 409 with that list).
 */
export async function deliveryErrorMessage(err: unknown): Promise<string> {
  const fallback = "ZIP 生成に失敗しました。";
  const data = (err as { response?: { data?: unknown } } | undefined)?.response
    ?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text()) as { detail?: unknown };
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      return fallback;
    }
    return fallback;
  }
  const detail = (data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}
