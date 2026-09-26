import { api } from "./client";

// API client for the Editor integration endpoints (backend: api/editor.py +
// api/revisions.py). Types mirror api/schemas.py so the DX console can drive the
// already-implemented backend (ReviewSidecar import, flatten gate, editor
// events, workflow polling, PDF revisions).

// ─── ReviewSidecar ───────────────────────────────────────────────────────────
export interface ReviewSidecarImportResponse {
  id: string;
  status: string;
  review_sidecar: Record<string, unknown> | null;
  review_sidecar_imported_at: string | null;
}

export interface ReviewSidecarGetResponse {
  review_sidecar: Record<string, unknown> | null;
  review_sidecar_imported_at: string | null;
}

// Mirrors the CivilPDF-Editor `civilpdf.review/v1` contract (lib/review/schema.ts).
export interface ReviewSidecarPayload {
  schema?: string;
  generator?: string;
  savedAt?: string;
  stamps?: unknown[];
  annotations?: unknown[];
}

export async function getReviewSidecar(
  docId: string,
): Promise<ReviewSidecarGetResponse> {
  const res = await api.get<ReviewSidecarGetResponse>(
    `/documents/${docId}/review-sidecar`,
  );
  return res.data;
}

export async function importReviewSidecar(
  docId: string,
  payload: ReviewSidecarPayload,
): Promise<ReviewSidecarImportResponse> {
  const res = await api.post<ReviewSidecarImportResponse>(
    `/documents/${docId}/review-sidecar`,
    payload,
  );
  return res.data;
}

// ─── Flatten-check gate ──────────────────────────────────────────────────────
export interface FlattenCheckResponse {
  is_flattened: boolean;
  flattened_hash: string | null;
  status: string;
}

export async function flattenCheck(
  docId: string,
): Promise<FlattenCheckResponse> {
  const res = await api.post<FlattenCheckResponse>(
    `/documents/${docId}/flatten-check`,
  );
  return res.data;
}

// ─── Editor events (audit) ───────────────────────────────────────────────────
export type EditorEventType =
  "stamp.placed" | "stamp.removed" | "annotation.added" | "comment.added";

export interface EditorEventItem {
  event_type: EditorEventType;
  detail?: unknown;
  occurred_at: string;
}

export interface EditorEventsResponse {
  created: number;
}

export async function postEditorEvents(
  docId: string,
  events: EditorEventItem[],
): Promise<EditorEventsResponse> {
  const res = await api.post<EditorEventsResponse>(
    `/documents/${docId}/editor-events`,
    events,
  );
  return res.data;
}

// ─── Workflow status (Editor polling) ────────────────────────────────────────
export interface WorkflowStep {
  approver_id: string;
  order: number;
  status: string;
  comment: string | null;
  decided_at: string | null;
}

export interface WorkflowStatusResponse {
  status: string;
  updated_at: string | null;
  steps: WorkflowStep[];
  editor_sync: Record<string, unknown> | null;
}

export async function getWorkflowStatus(
  docId: string,
): Promise<WorkflowStatusResponse> {
  const res = await api.get<WorkflowStatusResponse>(
    `/documents/${docId}/workflow-status`,
  );
  return res.data;
}

// ─── Revisions ───────────────────────────────────────────────────────────────
export interface RevisionResponse {
  id: string;
  document_id: string;
  version_number: number;
  filename: string;
  file_size: number;
  revision: string | null;
  revision_note: string | null;
  is_from_editor: boolean;
  editor_session_id: string | null;
  created_at: string;
}

export async function listRevisions(
  docId: string,
): Promise<RevisionResponse[]> {
  const res = await api.get<RevisionResponse[]>(
    `/documents/${docId}/revisions`,
  );
  return res.data;
}

export async function uploadRevision(
  docId: string,
  file: File,
  opts?: {
    revision?: string;
    revisionNote?: string;
    isFromEditor?: boolean;
    editorSessionId?: string;
  },
): Promise<RevisionResponse> {
  const form = new FormData();
  form.append("file", file);
  if (opts?.revision) form.append("revision", opts.revision);
  if (opts?.revisionNote) form.append("revision_note", opts.revisionNote);
  form.append("is_from_editor", String(opts?.isFromEditor ?? false));
  if (opts?.editorSessionId)
    form.append("editor_session_id", opts.editorSessionId);
  const res = await api.post<RevisionResponse>(
    `/documents/${docId}/revisions`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}
