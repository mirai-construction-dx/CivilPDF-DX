import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listWorkflows,
  getWorkflow,
  decideStep,
  resubmitWorkflow,
  type WorkflowResponse,
  type ApprovalStep,
} from "../api/workflows";
import { getDocument } from "../api/documents";
import { useAuthStore } from "../store/auth";
import { useModalDialog } from "../hooks/useModalDialog";

const statusLabel: Record<string, { label: string; cls: string }> = {
  in_progress: { label: "審査中", cls: "bg-orange-100 text-orange-700" },
  approved: { label: "承認済", cls: "bg-green-100 text-green-700" },
  rejected: { label: "却下", cls: "bg-red-100 text-red-700" },
  returned: { label: "差戻し", cls: "bg-amber-100 text-amber-700" },
};

const stepStatusLabel: Record<string, { label: string; cls: string }> = {
  pending: { label: "保留中", cls: "bg-yellow-100 text-yellow-700" },
  approved: { label: "承認", cls: "bg-green-100 text-green-700" },
  rejected: { label: "却下", cls: "bg-red-100 text-red-700" },
  returned: { label: "差戻し", cls: "bg-amber-100 text-amber-700" },
};

/** API エラーの detail（403/409 等）があればそれを、無ければ文字列化して返す。 */
function errorDetail(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } } | null | undefined
  )?.response?.data?.detail;
  return typeof detail === "string" ? detail : String(error);
}

// ---------- WorkflowDetailModal ----------

interface DetailModalProps {
  workflowId: string;
  onClose: () => void;
}

function WorkflowDetailModal({ workflowId, onClose }: DetailModalProps) {
  const qc = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const dialogRef = useModalDialog(true, onClose);
  const [comment, setComment] = useState("");
  const [actingStepId, setActingStepId] = useState<string | null>(null);

  const { data: wf, isLoading } = useQuery<WorkflowResponse>({
    queryKey: ["workflow", workflowId],
    queryFn: () => getWorkflow(workflowId),
  });

  // 再申請の権限判定（設計 D10）: owner 判定のため文書を取得する。
  const { data: doc } = useQuery({
    queryKey: ["document", wf?.document_id],
    queryFn: () => getDocument(wf!.document_id),
    enabled: !!wf?.document_id,
  });

  const decide = useMutation({
    mutationFn: ({
      stepId,
      decision,
    }: {
      stepId: string;
      decision: "approve" | "reject" | "return";
    }) => decideStep(workflowId, stepId, decision, comment || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow", workflowId] });
      qc.invalidateQueries({ queryKey: ["workflows"] });
      setComment("");
      setActingStepId(null);
    },
  });

  const resubmit = useMutation({
    mutationFn: () => resubmitWorkflow(workflowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow", workflowId] });
      qc.invalidateQueries({ queryKey: ["workflows"] });
      setComment("");
      setActingStepId(null);
    },
  });

  function isMyPendingStep(step: ApprovalStep): boolean {
    return step.approver_id === currentUser?.id && step.status === "pending";
  }

  // 差戻し中は再申請するまで decide を受け付けない（backend 契約）。
  const isReturned = wf?.status === "returned";

  // 差戻し可能条件（設計 D11）: 自分の pending ステップで、かつ
  // 先行ステップ（order が小さい）に承認済みが無いこと。
  // 差戻し中（returned）は再申請まで操作不可。
  function canReturnStep(step: ApprovalStep): boolean {
    if (isReturned || !isMyPendingStep(step)) return false;
    return !(wf?.steps ?? []).some(
      (s) => s.order < step.order && s.status === "approved",
    );
  }

  // 再申請の表示条件（設計 D10）: 差戻し中で、admin または文書 owner。
  // 権限判定（owner の文書取得）が終わるまでは非表示。
  const canResubmit =
    isReturned &&
    !!currentUser &&
    (currentUser.role === "admin" || doc?.owner_id === currentUser.id);

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="workflow-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2
            id="workflow-modal-title"
            className="text-lg font-bold text-gray-800"
          >
            ワークフロー詳細
          </h2>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-4 flex-1">
          {isLoading ? (
            <p className="text-gray-400 text-sm">読み込み中...</p>
          ) : !wf ? (
            <p className="text-gray-400 text-sm">
              ワークフローが見つかりません
            </p>
          ) : (
            <>
              {/* Status badge */}
              <div className="mb-4 flex items-center gap-3">
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${statusLabel[wf.status]?.cls ?? "bg-gray-100 text-gray-600"}`}
                >
                  {statusLabel[wf.status]?.label ?? wf.status}
                </span>
                <span className="text-xs text-gray-400">
                  開始: {new Date(wf.created_at).toLocaleDateString("ja-JP")}
                </span>
                {wf.completed_at && (
                  <span className="text-xs text-gray-400">
                    完了:{" "}
                    {new Date(wf.completed_at).toLocaleDateString("ja-JP")}
                  </span>
                )}
              </div>

              {/* 再申請（差戻し中のみ） */}
              {wf.status === "returned" && canResubmit && (
                <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
                  <p className="text-xs text-amber-800">
                    差戻しされた承認依頼です。修正後に再申請できます。
                  </p>
                  <button
                    onClick={() => resubmit.mutate()}
                    disabled={resubmit.isPending}
                    className="bg-amber-600 hover:bg-amber-700 text-white text-xs px-3 py-1.5 rounded transition-colors disabled:opacity-50"
                  >
                    再申請
                  </button>
                  {resubmit.error && (
                    <p className="text-red-600 text-xs">
                      {errorDetail(resubmit.error)}
                    </p>
                  )}
                </div>
              )}

              {/* Steps */}
              <h3 className="text-sm font-semibold text-gray-600 mb-3">
                承認ステップ
              </h3>
              <ol className="space-y-3">
                {wf.steps
                  .slice()
                  .sort((a, b) => a.order - b.order)
                  .map((step) => {
                    const ss = stepStatusLabel[step.status] ?? {
                      label: step.status,
                      cls: "bg-gray-100 text-gray-600",
                    };
                    // 差戻し中（returned）は再申請まで承認・却下・差戻しを出さない。
                    const canAct =
                      isMyPendingStep(step) && !decide.isPending && !isReturned;
                    const isExpanded = actingStepId === step.id;

                    return (
                      <li key={step.id} className="border rounded-lg p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-800 truncate">
                              {step.order}. {step.approver.full_name}
                            </p>
                            <p className="text-xs text-gray-400">
                              {step.approver.email}
                            </p>
                            {step.comment && (
                              <p className="text-xs text-gray-500 mt-1 italic">
                                「{step.comment}」
                              </p>
                            )}
                            {step.decided_at && (
                              <p className="text-xs text-gray-400 mt-0.5">
                                {new Date(step.decided_at).toLocaleDateString(
                                  "ja-JP",
                                )}
                              </p>
                            )}
                          </div>
                          <div className="flex flex-col items-end gap-1 shrink-0">
                            <span
                              className={`px-2 py-0.5 rounded-full text-xs ${ss.cls}`}
                            >
                              {ss.label}
                            </span>
                            {canAct && !isExpanded && (
                              <button
                                onClick={() => setActingStepId(step.id)}
                                className="text-xs text-blue-600 underline mt-1"
                              >
                                操作する
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Inline action form */}
                        {isExpanded && !isReturned && (
                          <div className="mt-3 border-t pt-3 space-y-2">
                            <textarea
                              rows={2}
                              placeholder="コメント（任意）"
                              value={comment}
                              onChange={(e) => setComment(e.target.value)}
                              className="w-full border rounded px-3 py-2 text-sm resize-none"
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() =>
                                  decide.mutate({
                                    stepId: step.id,
                                    decision: "approve",
                                  })
                                }
                                disabled={decide.isPending}
                                className="flex-1 bg-green-600 hover:bg-green-700 text-white text-xs py-1.5 rounded transition-colors disabled:opacity-50"
                              >
                                承認
                              </button>
                              <button
                                onClick={() =>
                                  decide.mutate({
                                    stepId: step.id,
                                    decision: "reject",
                                  })
                                }
                                disabled={decide.isPending}
                                className="flex-1 bg-red-600 hover:bg-red-700 text-white text-xs py-1.5 rounded transition-colors disabled:opacity-50"
                              >
                                却下
                              </button>
                              {canReturnStep(step) && (
                                <button
                                  onClick={() =>
                                    decide.mutate({
                                      stepId: step.id,
                                      decision: "return",
                                    })
                                  }
                                  disabled={decide.isPending}
                                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white text-xs py-1.5 rounded transition-colors disabled:opacity-50"
                                >
                                  差戻し
                                </button>
                              )}
                              <button
                                onClick={() => {
                                  setActingStepId(null);
                                  setComment("");
                                }}
                                className="px-3 border text-xs py-1.5 rounded text-gray-600"
                              >
                                キャンセル
                              </button>
                            </div>
                            {decide.error && (
                              <p className="text-red-600 text-xs">
                                {errorDetail(decide.error)}
                              </p>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- Workflows (list) ----------

export function Workflows() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const {
    data: workflows = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["workflows"],
    queryFn: listWorkflows,
  });

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">
        承認ワークフロー
      </h1>

      {isError && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700 flex items-center justify-between gap-3"
        >
          <span>ワークフローの読み込みに失敗しました</span>
          <button
            onClick={() => void refetch()}
            className="text-xs px-2 py-1 rounded border border-red-300 hover:bg-red-100"
          >
            再試行
          </button>
        </div>
      )}

      <div className="bg-white rounded-xl shadow overflow-x-auto">
        {isLoading ? (
          <p className="p-6 text-gray-400 text-sm">読み込み中...</p>
        ) : workflows.length === 0 ? (
          <p className="p-6 text-gray-400 text-sm">ワークフローがありません</p>
        ) : (
          <table className="w-full text-sm min-w-[760px]">
            <thead className="border-b">
              <tr className="text-left text-gray-500">
                <th scope="col" className="px-4 py-3">
                  ドキュメント
                </th>
                <th scope="col" className="px-4 py-3">
                  ステータス
                </th>
                <th scope="col" className="px-4 py-3">
                  ステップ数
                </th>
                <th scope="col" className="px-4 py-3">
                  承認待ち
                </th>
                <th scope="col" className="px-4 py-3">
                  作成日
                </th>
                <th scope="col" className="px-4 py-3">
                  完了日
                </th>
                <th scope="col" className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {workflows.map((wf) => {
                const s = statusLabel[wf.status] ?? {
                  label: wf.status,
                  cls: "bg-gray-100 text-gray-600",
                };
                return (
                  <tr
                    key={wf.id}
                    className="border-b last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-medium">
                      {wf.document_title}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs ${s.cls}`}
                      >
                        {s.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-center">
                      {wf.step_count}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {wf.pending_step_count > 0 ? (
                        <span className="px-2 py-0.5 rounded-full text-xs bg-orange-100 text-orange-700">
                          {wf.pending_step_count}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {new Date(wf.created_at).toLocaleDateString("ja-JP")}
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {wf.completed_at
                        ? new Date(wf.completed_at).toLocaleDateString("ja-JP")
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setSelectedId(wf.id)}
                        className="text-xs text-blue-600 hover:text-blue-800 underline"
                      >
                        詳細
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selectedId && (
        <WorkflowDetailModal
          workflowId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
