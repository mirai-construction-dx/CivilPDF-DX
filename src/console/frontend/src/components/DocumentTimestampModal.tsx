import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  applyTimestamp,
  verifyTimestamp,
  type TimestampVerifyResponse,
} from "../api/documents";
import { useModalDialog } from "../hooks/useModalDialog";

interface Props {
  documentId: string;
  documentTitle: string;
  onClose: () => void;
}

export function DocumentTimestampModal({
  documentId,
  documentTitle,
  onClose,
}: Props) {
  const [applied, setApplied] = useState(false);
  const dialogRef = useModalDialog(true, onClose);

  const verify = useQuery<TimestampVerifyResponse>({
    queryKey: ["timestamp-verify", documentId],
    queryFn: () => verifyTimestamp(documentId),
    enabled: true,
  });

  const stamp = useMutation({
    mutationFn: () => applyTimestamp(documentId),
    onSuccess: () => {
      setApplied(true);
      verify.refetch();
    },
  });

  const statusBadge = (v: TimestampVerifyResponse | undefined) => {
    if (!v) return null;
    if (v.valid) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800">
          ✅ 整合性確認済み
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800">
        ❌ {v.message}
      </span>
    );
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="timestamp-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-700 text-xl font-bold"
          aria-label="閉じる"
        >
          ×
        </button>

        <h2
          id="timestamp-modal-title"
          className="text-lg font-bold text-gray-800 mb-1"
        >
          🔏 電子タイムスタンプ
        </h2>
        <p className="text-sm text-gray-500 mb-4 truncate">{documentTitle}</p>

        {/* Current status */}
        <div className="bg-gray-50 rounded-lg p-4 mb-4 text-sm">
          <div className="font-semibold text-gray-700 mb-2">現在の状態</div>
          {verify.isLoading && <span className="text-gray-400">確認中...</span>}
          {verify.data && (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                {statusBadge(verify.data)}
              </div>
              {verify.data.file_hash && (
                <div className="text-gray-500 font-mono text-xs break-all">
                  SHA-256: {verify.data.file_hash}
                </div>
              )}
              {verify.data.verified_at && (
                <div className="text-gray-500 text-xs">
                  タイムスタンプ付与日時:{" "}
                  {new Date(verify.data.verified_at).toLocaleString("ja-JP")}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Law compliance note */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-xs text-blue-800">
          <strong>電子帳簿保存法・e-文書法対応</strong>
          <p className="mt-1 text-blue-700">
            RFC 3161
            タイムスタンプにより、文書の作成・保存時刻を第三者機関（TSA）が証明します。
            TSA 未設定時はローカル HMAC によるフォールバックが使用されます。
          </p>
        </div>

        {applied && (
          <div className="bg-green-50 border border-green-200 rounded p-2 mb-4 text-xs text-green-700">
            ✅ タイムスタンプを付与しました。
          </div>
        )}

        {stamp.isError && (
          <div className="bg-red-50 border border-red-200 rounded p-2 mb-4 text-xs text-red-700">
            ❌ タイムスタンプ付与に失敗しました。
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            閉じる
          </button>
          <button
            onClick={() => stamp.mutate()}
            disabled={stamp.isPending}
            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {stamp.isPending ? "付与中..." : "🔏 タイムスタンプ付与"}
          </button>
        </div>
      </div>
    </div>
  );
}
