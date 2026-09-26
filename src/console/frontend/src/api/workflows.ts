import { api } from "./client";

export interface ApproverInfo {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: string;
}

export interface ApprovalStep {
  id: string;
  order: number;
  approver_id: string;
  status: string;
  comment: string | null;
  decided_at: string | null;
  approver: ApproverInfo;
}

export interface WorkflowResponse {
  id: string;
  document_id: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  steps: ApprovalStep[];
}

export interface WorkflowListItem {
  id: string;
  document_id: string;
  document_title: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  step_count: number;
  pending_step_count: number;
}

export interface CreateWorkflowRequest {
  document_id: string;
  approver_ids: string[];
}

export async function listWorkflows(): Promise<WorkflowListItem[]> {
  const res = await api.get<WorkflowListItem[]>("/workflows/");
  return res.data;
}

export async function getWorkflow(id: string): Promise<WorkflowResponse> {
  const res = await api.get<WorkflowResponse>(`/workflows/${id}`);
  return res.data;
}

export async function createWorkflow(
  data: CreateWorkflowRequest,
): Promise<WorkflowResponse> {
  const res = await api.post<WorkflowResponse>("/workflows/", data);
  return res.data;
}

export async function decideStep(
  workflowId: string,
  stepId: string,
  decision: "approve" | "reject",
  comment?: string,
): Promise<WorkflowResponse> {
  const res = await api.post<WorkflowResponse>(
    `/workflows/${workflowId}/steps/${stepId}/decide`,
    { decision, comment },
  );
  return res.data;
}
