import { type FC, useState, type CSSProperties } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listDocuments, type DocumentResponse } from "../../../api/documents";
import {
  getReviewSidecar,
  getWorkflowStatus,
  listRevisions,
  flattenCheck,
  type FlattenCheckResponse,
} from "../../../api/editor";
import { listAuditLogs } from "../../../api/auditLogs";
import { getDxSyncStats } from "../../../api/stats";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

// DocumentStatus → 日本語ラベル（backend models/document.py の Enum に対応）。
const STATUS_LABEL: Record<string, string> = {
  draft: "ドラフト",
  pending_review: "レビュー待ち",
  approved: "承認済み",
  rejected: "却下",
  archived: "アーカイブ",
  editor_draft: "Editor 編集中",
  editor_reviewed: "Editor レビュー完了",
  finalized: "確定（フラット化済）",
};

function statusLabel(s: string): string {
  return STATUS_LABEL[s] ?? s;
}

export const EditorSyncView: FC<ViewProps> = ({ onShowToast }) => {
  const qc = useQueryClient();
  const [selectedDocId, setSelectedDocId] = useState<string>("");

  const { data: documents } = useQuery({
    queryKey: ["documents", "for-editor-sync"],
    queryFn: () => listDocuments({ per_page: 100 }),
  });

  const enabled = !!selectedDocId;

  const { data: sidecar } = useQuery({
    queryKey: ["editor", "review-sidecar", selectedDocId],
    queryFn: () => getReviewSidecar(selectedDocId),
    enabled,
  });

  const { data: workflow } = useQuery({
    queryKey: ["editor", "workflow-status", selectedDocId],
    queryFn: () => getWorkflowStatus(selectedDocId),
    enabled,
  });

  const { data: revisions } = useQuery({
    queryKey: ["editor", "revisions", selectedDocId],
    queryFn: () => listRevisions(selectedDocId),
    enabled,
  });

  const { data: auditLogs } = useQuery({
    queryKey: ["editor", "audit", selectedDocId],
    queryFn: () => listAuditLogs({ resource_type: "document", per_page: 100 }),
    enabled,
  });

  // DX 同期成功率（dx_sync_metrics / Admin 限定）。非 Admin は 403 になるため
  // retry を無効にし、画面に「Admin 限定」と表示する。
  const { data: dxStats, isError: dxStatsError } = useQuery({
    queryKey: ["stats", "dx-sync"],
    queryFn: () => getDxSyncStats(),
    retry: false,
  });

  const flattenMutation = useMutation({
    mutationFn: () => flattenCheck(selectedDocId),
    onSuccess: (data: FlattenCheckResponse) => {
      onShowToast(
        `確定保存しました（status: ${statusLabel(data.status)}）`,
        "ok",
      );
      qc.invalidateQueries({ queryKey: ["editor"] });
    },
    onError: () => {
      onShowToast(
        "確定保存に失敗しました（フォームフィールド/注釈が残っている可能性）",
        "error",
      );
    },
  });

  // editor-events は記録専用 API のため、表示は既存 audit-logs を resource_id で絞る。
  const docAudit = (auditLogs?.items ?? []).filter(
    (a) => a.resource_id === selectedDocId,
  );

  const stamps = Array.isArray(sidecar?.review_sidecar?.stamps)
    ? (sidecar!.review_sidecar!.stamps as unknown[])
    : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* DX sync success rate (SLO >= 99%) */}
      <div className="ep-panel">
        <div className="ep-panel-head">
          <h3>📡 DX 同期成功率</h3>
          <span className="ep-pill ep-pill-muted">
            dx_sync_metrics / SLO ≥ 99%
          </span>
        </div>
        {dxStats ? (
          <>
            <div
              className="ep-stat-grid"
              style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
            >
              <div className="ep-stat">
                <div className="lbl">30日成功率</div>
                <div className="val">
                  {dxStats.success_rate_30d !== null
                    ? `${dxStats.success_rate_30d}%`
                    : "—"}
                </div>
                <div className="delta">30日 {dxStats.recent_30d.total} 件</div>
              </div>
              <div className="ep-stat">
                <div className="lbl">累計成功率</div>
                <div className="val">
                  {dxStats.success_rate_total !== null
                    ? `${dxStats.success_rate_total}%`
                    : "—"}
                </div>
                <div className="delta">累計 {dxStats.total} 件</div>
              </div>
              <div className="ep-stat">
                <div className="lbl">成功</div>
                <div className="val">{dxStats.success}</div>
                <div className="delta">30日 {dxStats.recent_30d.success}</div>
              </div>
              <div className="ep-stat">
                <div className="lbl">失敗（30日）</div>
                <div
                  className="val"
                  style={{ color: "var(--danger, #b91c1c)" }}
                >
                  {dxStats.recent_30d.error}
                </div>
                <div className="delta">
                  {Object.entries(dxStats.by_error_kind_30d)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" / ") || "分類なし"}
                </div>
              </div>
            </div>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                marginTop: "10px",
              }}
            >
              <thead>
                <tr>
                  <th style={thStyle}>月</th>
                  <th style={thStyle}>成功</th>
                  <th style={thStyle}>失敗</th>
                  <th style={thStyle}>成功率</th>
                </tr>
              </thead>
              <tbody>
                {dxStats.monthly.map((m) => {
                  const rate =
                    m.success + m.error > 0
                      ? ((m.success / (m.success + m.error)) * 100).toFixed(1)
                      : "—";
                  return (
                    <tr key={m.month}>
                      <td style={tdStyle}>{m.month}</td>
                      <td style={tdStyle}>{m.success}</td>
                      <td style={tdStyle}>{m.error}</td>
                      <td style={tdStyle}>{rate}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        ) : dxStatsError ? (
          <p style={{ color: "var(--muted)", padding: "12px 0" }}>
            DX 同期統計は Admin 権限でのみ表示できます（403）。
          </p>
        ) : (
          <p style={{ color: "var(--muted)", padding: "12px 0" }}>
            読み込み中...
          </p>
        )}
      </div>

      {/* Header + document selector */}
      <div className="ep-panel">
        <div className="ep-panel-head">
          <h3>🖊️ Editor 連携</h3>
          <span className="ep-pill ep-pill-muted">
            ReviewSidecar・改訂・確定ゲート・監査・ワークフロー
          </span>
        </div>
        <div style={{ padding: "12px 0" }}>
          <label
            htmlFor="editor-doc-select"
            style={{
              display: "block",
              marginBottom: "6px",
              color: "var(--muted)",
            }}
          >
            対象ドキュメント
          </label>
          <select
            id="editor-doc-select"
            value={selectedDocId}
            onChange={(e) => setSelectedDocId(e.target.value)}
            style={{ width: "100%", maxWidth: "520px", padding: "8px" }}
          >
            <option value="">— ドキュメントを選択 —</option>
            {(documents ?? []).map((d: DocumentResponse) => (
              <option key={d.id} value={d.id}>
                {d.title}（{statusLabel(d.status)}）
              </option>
            ))}
          </select>
        </div>
      </div>

      {!selectedDocId ? (
        <div className="ep-panel">
          <p
            style={{
              color: "var(--muted)",
              padding: "20px",
              textAlign: "center",
            }}
          >
            ドキュメントを選択すると、Editor
            連携情報（押印レビュー・改訂・監査・ワークフロー）が表示されます。
          </p>
        </div>
      ) : (
        <>
          {/* Key stats */}
          <div
            className="ep-stat-grid"
            style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
          >
            <div className="ep-stat">
              <div className="lbl">ワークフロー状態</div>
              <div className="val" style={{ fontSize: "18px" }}>
                {workflow ? statusLabel(workflow.status) : "—"}
              </div>
              <div className="delta">
                承認ステップ {workflow?.steps.length ?? 0}
              </div>
            </div>
            <div className="ep-stat">
              <div className="lbl">押印（ReviewSidecar）</div>
              <div className="val">{stamps.length}</div>
              <div className="delta">
                {sidecar?.review_sidecar_imported_at ? "取込済み" : "未取込"}
              </div>
            </div>
            <div className="ep-stat">
              <div className="lbl">改訂数</div>
              <div className="val">{revisions?.length ?? 0}</div>
              <div className="delta">
                Editor 由来{" "}
                {(revisions ?? []).filter((r) => r.is_from_editor).length}
              </div>
            </div>
            <div className="ep-stat">
              <div className="lbl">監査イベント</div>
              <div className="val">{docAudit.length}</div>
              <div className="delta">SHA-256 chain</div>
            </div>
          </div>

          {/* ReviewSidecar + Flatten gate */}
          <div className="ep-panel">
            <div className="ep-panel-head">
              <h3>🔖 押印レビュー（ReviewSidecar）</h3>
              <span
                className={`ep-pill ${
                  sidecar?.review_sidecar_imported_at
                    ? "ep-pill-stable"
                    : "ep-pill-muted"
                }`}
              >
                {sidecar?.review_sidecar_imported_at ? "取込済み" : "未取込"}
              </span>
            </div>
            <div style={{ padding: "8px 0" }}>
              {sidecar?.review_sidecar_imported_at ? (
                <p style={{ color: "var(--muted)" }}>
                  取込日時:{" "}
                  {new Date(sidecar.review_sidecar_imported_at).toLocaleString(
                    "ja-JP",
                  )}
                  ／押印 {stamps.length} 件
                </p>
              ) : (
                <p style={{ color: "var(--muted)" }}>
                  Editor からの ReviewSidecar はまだ取り込まれていません。
                </p>
              )}
              <button
                className="ep-btn ep-btn-primary ep-btn-sm"
                style={{ marginTop: "8px" }}
                disabled={flattenMutation.isPending}
                onClick={() => flattenMutation.mutate()}
              >
                {flattenMutation.isPending
                  ? "確定処理中..."
                  : "🔒 確定保存（フラット化検証）"}
              </button>
              <span
                style={{
                  marginLeft: "10px",
                  color: "var(--muted)",
                  fontSize: "13px",
                }}
              >
                確定すると status が FINALIZED に遷移し、SHA-256
                ハッシュが記録されます
              </span>
            </div>
          </div>

          {/* Revisions */}
          <div className="ep-panel">
            <div className="ep-panel-head">
              <h3>📑 改訂履歴</h3>
            </div>
            {(revisions?.length ?? 0) === 0 ? (
              <p style={{ color: "var(--muted)", padding: "8px 0" }}>
                改訂はまだありません。
              </p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                    <th>版</th>
                    <th>改訂</th>
                    <th>ファイル</th>
                    <th>由来</th>
                    <th>日時</th>
                  </tr>
                </thead>
                <tbody>
                  {(revisions ?? []).map((r) => (
                    <tr
                      key={r.id}
                      style={{ borderTop: "1px solid var(--border)" }}
                    >
                      <td>v{r.version_number}</td>
                      <td>{r.revision ?? "—"}</td>
                      <td>{r.filename}</td>
                      <td>
                        {r.is_from_editor ? (
                          <span className="ep-pill ep-pill-stable">Editor</span>
                        ) : (
                          <span className="ep-pill ep-pill-muted">手動</span>
                        )}
                      </td>
                      <td>{new Date(r.created_at).toLocaleString("ja-JP")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Audit timeline */}
          <div className="ep-panel">
            <div className="ep-panel-head">
              <h3>🛡️ 監査タイムライン</h3>
              <span className="ep-pill ep-pill-muted">
                改ざん検知 hash chain
              </span>
            </div>
            {docAudit.length === 0 ? (
              <p style={{ color: "var(--muted)", padding: "8px 0" }}>
                このドキュメントの監査イベントはまだありません。
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {docAudit.slice(0, 20).map((a) => (
                  <li
                    key={a.id}
                    style={{
                      padding: "6px 0",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <span className="ep-pill ep-pill-stable">{a.action}</span>
                    <span style={{ marginLeft: "8px" }}>
                      {a.user?.full_name ?? "system"}
                    </span>
                    <span
                      style={{
                        marginLeft: "8px",
                        color: "var(--muted)",
                        fontSize: "12px",
                      }}
                    >
                      {new Date(a.created_at).toLocaleString("ja-JP")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "6px 8px",
  borderBottom: "1px solid var(--border, #e2e8f0)",
  fontSize: "12px",
  color: "var(--muted)",
};

const tdStyle: CSSProperties = {
  padding: "6px 8px",
  borderBottom: "1px solid var(--border, #e2e8f0)",
  fontSize: "13px",
};
