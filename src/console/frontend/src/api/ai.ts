import { api } from "./client";

export interface ClassifyResponse {
  document_id: string;
  drawing_type: string | null;
  project_type: string | null;
  confidence: number;
  tags: string[];
  classified_at: string;
  model: string;
}

export interface ExtractResponse {
  document_id: string;
  extracted_at: string;
  model: string;
  data: {
    construction_name?: string | null;
    contractor?: string | null;
    site_location?: string | null;
    amount?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    responsible_person?: string | null;
    checklist_items?: string[];
    [key: string]: unknown;
  };
}

export interface SummaryResponse {
  document_id: string;
  summary: string;
  summarized_at: string;
  model: string;
}

export async function classifyDocument(
  documentId: string,
): Promise<ClassifyResponse> {
  const res = await api.post<ClassifyResponse>(
    `/ai/documents/${documentId}/classify`,
  );
  return res.data;
}

export async function extractDocumentData(
  documentId: string,
): Promise<ExtractResponse> {
  const res = await api.post<ExtractResponse>(
    `/ai/documents/${documentId}/extract`,
  );
  return res.data;
}

export async function getDocumentSummary(
  documentId: string,
): Promise<SummaryResponse> {
  const res = await api.get<SummaryResponse>(
    `/ai/documents/${documentId}/summary`,
  );
  return res.data;
}
