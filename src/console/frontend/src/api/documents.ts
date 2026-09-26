import { api } from "./client";

export interface DocumentResponse {
  id: string;
  title: string;
  document_type: string;
  status: string;
  filename: string;
  file_size: number;
  page_count: number | null;
  is_pdfa: boolean;
  pdfa_version?: string | null;
  tags: string[];
  project_id: string;
  owner_id: string;
  created_at: string;
  updated_at: string | null;
  timestamp_verified_at?: string | null;
  retention_expires_at?: string | null;
  is_archived?: boolean;
  deletion_requested_at?: string | null;
  iso19650_originator?: string | null;
  iso19650_functional_breakdown?: string | null;
  iso19650_form?: string | null;
  iso19650_discipline?: string | null;
  iso19650_number?: string | null;
}

export interface ListDocumentsParams {
  project_id?: string;
  document_type?: string;
  status?: string;
  page?: number;
  per_page?: number;
  include_meta?: boolean;
}

export interface DocumentPage {
  items: DocumentResponse[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export async function listDocuments(
  params?: ListDocumentsParams,
): Promise<DocumentResponse[]> {
  const res = await api.get<DocumentResponse[]>("/documents/", {
    params,
  });
  return res.data;
}

export async function downloadDocumentsCsv(
  params: Pick<
    ListDocumentsParams,
    "project_id" | "document_type" | "status"
  > = {},
): Promise<void> {
  const res = await api.get<Blob>("/documents/export.csv", {
    params,
    responseType: "blob",
  });
  const disposition = res.headers["content-disposition"] as string | undefined;
  const match = disposition?.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? "documents.csv";
  const url = URL.createObjectURL(res.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function listDocumentsPaginated(
  page: number,
  perPage = 20,
): Promise<DocumentPage> {
  const res = await api.get<DocumentPage>("/documents/", {
    params: { page, per_page: perPage, include_meta: true },
  });
  return res.data;
}

export async function getDocument(id: string): Promise<DocumentResponse> {
  const res = await api.get<DocumentResponse>(`/documents/${id}`);
  return res.data;
}

export interface Iso19650Metadata {
  originator?: string;
  functional_breakdown?: string;
  form?: string;
  discipline?: string;
  number?: string;
}

export async function uploadDocument(
  projectId: string,
  title: string,
  documentType: string,
  file: File,
  iso19650?: Iso19650Metadata,
): Promise<DocumentResponse> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("title", title);
  form.append("document_type", documentType);
  form.append("file", file);
  if (iso19650?.originator)
    form.append("iso19650_originator", iso19650.originator);
  if (iso19650?.functional_breakdown)
    form.append("iso19650_functional_breakdown", iso19650.functional_breakdown);
  if (iso19650?.form) form.append("iso19650_form", iso19650.form);
  if (iso19650?.discipline)
    form.append("iso19650_discipline", iso19650.discipline);
  if (iso19650?.number) form.append("iso19650_number", iso19650.number);
  const res = await api.post<DocumentResponse>("/documents/", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/documents/${id}`);
}

export async function listTrash(): Promise<DocumentResponse[]> {
  const res = await api.get<DocumentResponse[]>("/documents/trash");
  return res.data;
}

export async function restoreDocument(id: string): Promise<DocumentResponse> {
  const res = await api.post<DocumentResponse>(`/documents/${id}/restore`);
  return res.data;
}

export async function fetchDocumentBlob(id: string): Promise<Blob> {
  const res = await api.get<Blob>(`/documents/${id}/download`, {
    responseType: "blob",
  });
  return res.data;
}

export interface TimestampResponse {
  document_id: string;
  file_hash: string;
  token_type: "rfc3161" | "local_hmac";
  tsa_url: string;
  verified_at: string;
  token_present: boolean;
}

export interface TimestampVerifyResponse {
  document_id: string;
  valid: boolean;
  message: string;
  file_hash: string | null;
  verified_at: string | null;
}

export async function applyTimestamp(id: string): Promise<TimestampResponse> {
  const res = await api.post<TimestampResponse>(`/documents/${id}/timestamp`);
  return res.data;
}

export async function verifyTimestamp(
  id: string,
): Promise<TimestampVerifyResponse> {
  const res = await api.get<TimestampVerifyResponse>(
    `/documents/${id}/timestamp/verify`,
  );
  return res.data;
}
