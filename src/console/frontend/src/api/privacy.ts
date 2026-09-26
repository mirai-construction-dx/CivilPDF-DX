import { api } from "./client";

export interface ConsentRecord {
  id: string;
  user_id: string;
  consent_type: string;
  version: string;
  granted: boolean;
  ip_address: string | null;
  user_agent: string | null;
  source: string | null;
  disclosed_purpose: string | null;
  disclosed_retention_period: string | null;
  disclosed_third_parties: string | null;
  created_at: string;
}

export interface ConsentRequest {
  consent_type: string;
  version: string;
  granted: boolean;
  source?: string;
  disclosed_purpose?: string;
  disclosed_retention_period?: string;
  disclosed_third_parties?: string;
}

export interface DataExportResponse {
  user_id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  status: string;
  created_at: string | null;
  documents: Array<{
    id: string;
    title: string;
    document_type: string;
    filename: string;
    file_size: number;
    created_at: string | null;
    deletion_requested_at: string | null;
  }>;
  consent_records: ConsentRecord[];
  exported_at: string;
}

export interface DeletionResponse {
  user_id: string;
  documents_marked: number;
  deletion_requested_at: string;
  audit_log_id: string;
}

export async function requestDeletion(
  userId: string,
): Promise<DeletionResponse> {
  const res = await api.delete<DeletionResponse>(
    `/privacy/users/${userId}/data`,
  );
  return res.data;
}

export async function exportUserData(
  userId: string,
): Promise<DataExportResponse> {
  const res = await api.get<DataExportResponse>(
    `/privacy/users/${userId}/export`,
  );
  return res.data;
}

export async function recordConsent(
  req: ConsentRequest,
): Promise<ConsentRecord> {
  const res = await api.post<ConsentRecord>("/privacy/consent", req);
  return res.data;
}

export async function getConsentStatus(
  userId: string,
): Promise<ConsentRecord[]> {
  const res = await api.get<ConsentRecord[]>(`/privacy/consent/${userId}`);
  return res.data;
}
