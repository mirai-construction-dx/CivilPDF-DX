import { api } from "./client";

export interface SearchHit {
  document_id: string;
  title: string;
  document_type: string;
  status: string;
  project_id: string;
  snippet: string;
  score: number;
  tags: string[];
}

export interface SearchResponse {
  query: string;
  mode: "keyword" | "semantic";
  expanded_terms: string[];
  total: number;
  hits: SearchHit[];
}

export async function searchDocuments(
  q: string,
  mode: "keyword" | "semantic" = "keyword",
  limit = 20,
): Promise<SearchResponse> {
  const res = await api.get<SearchResponse>("/search/documents", {
    params: { q, mode, limit },
  });
  return res.data;
}

export async function reindexDocuments(): Promise<{
  indexed: number;
  status: string;
}> {
  const res = await api.post("/search/documents/reindex");
  return res.data;
}

export async function suggestTerms(q: string): Promise<string[]> {
  const res = await api.get<string[]>("/search/documents/suggest", {
    params: { q },
  });
  return res.data;
}
