import { useEffect, useState } from "react";
import { fetchDocumentBlob } from "../api/documents";

export interface DocumentPreviewModalProps {
  documentId: string | null;
  filename?: string;
  title?: string;
  onClose: () => void;
}

function isPdfFilename(filename?: string): boolean {
  if (!filename) return false;
  return filename.toLowerCase().endsWith(".pdf");
}

export function DocumentPreviewModal({
  documentId,
  filename,
  title,
  onClose,
}: DocumentPreviewModalProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const previewable = isPdfFilename(filename);

  useEffect(() => {
    if (!documentId || !previewable) return;
    let revoked = false;
    let createdUrl: string | null = null;

    fetchDocumentBlob(documentId)
      .then((blob) => {
        if (revoked) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch((e: unknown) => {
        if (revoked) return;
        setError(e instanceof Error ? e.message : "プレビューに失敗しました");
      })
      .finally(() => {
        if (!revoked) setLoading(false);
      });

    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      setObjectUrl(null);
    };
  }, [documentId, previewable]);

  useEffect(() => {
    if (!documentId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [documentId, onClose]);

  if (!documentId) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="ドキュメントプレビュー"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="font-semibold text-gray-800 truncate">
            {title || filename || "プレビュー"}
          </h2>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="text-gray-500 hover:text-gray-800 text-2xl leading-none px-2"
          >
            ×
          </button>
        </div>

        <div className="flex-1 bg-gray-100">
          {!previewable ? (
            <div className="h-full flex items-center justify-center text-gray-500 text-sm">
              プレビュー非対応のファイル形式です
            </div>
          ) : loading ? (
            <div className="h-full flex items-center justify-center text-gray-500 text-sm">
              読み込み中...
            </div>
          ) : error ? (
            <div className="h-full flex items-center justify-center text-red-500 text-sm">
              {error}
            </div>
          ) : objectUrl ? (
            <iframe
              src={objectUrl}
              title={title || filename || "PDF preview"}
              // 同一オリジンの Blob のみ表示。PDF ビューアの描画に必要な
              // allow-scripts / allow-same-origin に限定し、トップナビゲーション等は禁止する。
              sandbox="allow-scripts allow-same-origin"
              className="w-full h-full border-0"
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
