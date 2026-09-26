import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  checkDeliveryReadiness,
  deliveryErrorMessage,
  downloadDeliveryZip,
  type DeliveryReadinessResponse,
} from "../api/electronicDelivery";
import { useModalDialog } from "../hooks/useModalDialog";

interface Props {
  projectId: string;
  projectName: string;
  projectCode: string;
  onClose: () => void;
}

export function ElectronicDeliveryModal({
  projectId,
  projectName,
  projectCode,
  onClose,
}: Props) {
  const [downloaded, setDownloaded] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const dialogRef = useModalDialog(true, onClose);

  const readiness = useQuery<DeliveryReadinessResponse>({
    queryKey: ["delivery-readiness", projectId],
    queryFn: () => checkDeliveryReadiness(projectId),
  });

  const download = useMutation({
    mutationFn: () => downloadDeliveryZip(projectId, projectCode),
    onSuccess: () => {
      setErrorMessage(null);
      setDownloaded(true);
    },
    onError: (err: unknown) => {
      setDownloaded(false);
      void deliveryErrorMessage(err).then(setErrorMessage);
    },
  });

  const data = readiness.data;
  const unreadable = data?.unreadable_documents ?? [];

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delivery-modal-title"
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
          id="delivery-modal-title"
          className="text-lg font-bold text-gray-800 mb-1"
        >
          📦 電子納品パッケージ生成
        </h2>
        <p className="text-sm text-gray-500 mb-4 truncate">{projectName}</p>

        {/* Readiness check */}
        <div className="bg-gray-50 rounded-lg p-4 mb-4 text-sm">
          <div className="font-semibold text-gray-700 mb-2">納品準備状況</div>
          {readiness.isLoading && (
            <span className="text-gray-400">確認中...</span>
          )}
          {data && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                {data.ready ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800">
                    ✅ 納品可能
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-yellow-100 text-yellow-800">
                    ⚠️ 要確認
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                <div>
                  文書数:{" "}
                  <span className="font-semibold text-gray-800">
                    {data.document_count}
                  </span>
                </div>
                <div>
                  PDF/A準拠:{" "}
                  <span className="font-semibold text-gray-800">
                    {data.pdfa_compliant_count}
                  </span>
                </div>
              </div>
              {data.non_pdfa_documents.length > 0 && (
                <div className="mt-2">
                  <div className="text-xs font-semibold text-yellow-700 mb-1">
                    PDF/A 非準拠ファイル:
                  </div>
                  <ul className="list-disc list-inside space-y-0.5">
                    {data.non_pdfa_documents.map((d) => (
                      <li
                        key={d.id}
                        className="text-xs text-yellow-800 truncate"
                      >
                        {d.title}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {unreadable.length > 0 && (
                <div className="mt-2">
                  <div className="text-xs font-semibold text-red-700 mb-1">
                    読み取れないファイル（納品パッケージにできません）:
                  </div>
                  <ul className="list-disc list-inside space-y-0.5">
                    {unreadable.map((d) => (
                      <li key={d.id} className="text-xs text-red-800 truncate">
                        {d.title} — {d.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {data.warnings.length > 0 && (
                <div className="space-y-1 mt-1">
                  {data.warnings.map((w, i) => (
                    <div
                      key={i}
                      className="text-xs text-yellow-700 bg-yellow-50 rounded px-2 py-1"
                    >
                      ⚠️ {w}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* MLIT compliance note */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-xs text-blue-800">
          <strong>国交省 CALS/EC 電子納品要領準拠</strong>
          <p className="mt-1 text-blue-700">
            ZIP パッケージには DRAWINGS / PHOTO / INSPECTION 等フォルダと
            工事管理情報（INDEX.XML）が自動生成されます。
          </p>
        </div>

        {downloaded && (
          <div className="bg-green-50 border border-green-200 rounded p-2 mb-4 text-xs text-green-700">
            ✅ ZIP ファイルをダウンロードしました。
          </div>
        )}

        {download.isError && (
          <div className="bg-red-50 border border-red-200 rounded p-2 mb-4 text-xs text-red-700">
            ❌ {errorMessage ?? "ZIP 生成に失敗しました。"}
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
            onClick={() => download.mutate()}
            disabled={download.isPending}
            className="px-4 py-2 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {download.isPending ? "生成中..." : "📦 ZIP ダウンロード"}
          </button>
        </div>
      </div>
    </div>
  );
}
