import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAuditLogs, downloadAuditLogsCsv } from "../api/auditLogs";

const resourceTypeLabel: Record<string, string> = {
  document: "文書",
  workflow: "ワークフロー",
  user: "ユーザー",
  project: "プロジェクト",
};

const actionLabel: Record<string, { label: string; cls: string }> = {
  "document.upload": {
    label: "アップロード",
    cls: "bg-blue-100 text-blue-700",
  },
  "document.delete": { label: "削除", cls: "bg-red-100 text-red-700" },
  "document.update": { label: "更新", cls: "bg-yellow-100 text-yellow-700" },
  "workflow.create": {
    label: "ワークフロー作成",
    cls: "bg-purple-100 text-purple-700",
  },
  "workflow.approve": { label: "承認", cls: "bg-green-100 text-green-700" },
  "workflow.reject": { label: "却下", cls: "bg-red-100 text-red-700" },
  "user.login": { label: "ログイン", cls: "bg-gray-100 text-gray-600" },
  "user.create": { label: "ユーザー作成", cls: "bg-blue-100 text-blue-700" },
};

export function AuditLogs() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-logs", page, actionFilter, resourceFilter],
    queryFn: () =>
      listAuditLogs({
        page,
        per_page: 50,
        action: actionFilter || undefined,
        resource_type: resourceFilter || undefined,
      }),
  });

  const logs = data?.items ?? [];
  const totalPages = data?.pages ?? 0;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">監査ログ</h1>

      <div className="flex gap-3 mb-4">
        <select
          className="border rounded px-3 py-2 text-sm"
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">すべてのアクション</option>
          <option value="document.upload">アップロード</option>
          <option value="document.delete">削除</option>
          <option value="workflow.create">ワークフロー作成</option>
          <option value="workflow.approve">承認</option>
          <option value="workflow.reject">却下</option>
          <option value="user.login">ログイン</option>
        </select>

        <select
          className="border rounded px-3 py-2 text-sm"
          value={resourceFilter}
          onChange={(e) => {
            setResourceFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">すべてのリソース</option>
          <option value="document">文書</option>
          <option value="workflow">ワークフロー</option>
          <option value="user">ユーザー</option>
          <option value="project">プロジェクト</option>
        </select>

        {data && (
          <span className="ml-auto text-sm text-gray-500 self-center">
            合計 {data.total} 件
          </span>
        )}
        <button
          type="button"
          disabled={isExporting}
          onClick={() => {
            setIsExporting(true);
            downloadAuditLogsCsv({
              action: actionFilter || undefined,
              resource_type: resourceFilter || undefined,
            })
              .catch(() => undefined)
              .finally(() => setIsExporting(false));
          }}
          className="text-sm px-3 py-2 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {isExporting ? "出力中..." : "CSV出力"}
        </button>
      </div>

      {isError && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700 flex items-center justify-between gap-3"
        >
          <span>監査ログの読み込みに失敗しました</span>
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
        ) : logs.length === 0 ? (
          <p className="p-6 text-gray-400 text-sm">ログがありません</p>
        ) : (
          <table className="w-full text-sm min-w-[860px]">
            <thead className="border-b">
              <tr className="text-left text-gray-500">
                <th scope="col" className="px-4 py-3">
                  日時
                </th>
                <th scope="col" className="px-4 py-3">
                  ユーザー
                </th>
                <th scope="col" className="px-4 py-3">
                  アクション
                </th>
                <th scope="col" className="px-4 py-3">
                  リソース種別
                </th>
                <th scope="col" className="px-4 py-3">
                  リソースID
                </th>
                <th scope="col" className="px-4 py-3">
                  IPアドレス
                </th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => {
                const a = actionLabel[log.action] ?? {
                  label: log.action,
                  cls: "bg-gray-100 text-gray-600",
                };
                return (
                  <tr
                    key={log.id}
                    className="border-b last:border-0 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString("ja-JP")}
                    </td>
                    <td className="px-4 py-3">
                      {log.user ? (
                        <span className="font-medium">
                          {log.user.full_name}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs ${a.cls}`}
                      >
                        {a.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {log.resource_type
                        ? (resourceTypeLabel[log.resource_type] ??
                          log.resource_type)
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                      {log.resource_id
                        ? log.resource_id.slice(0, 8) + "..."
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                      {log.ip_address ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 rounded border text-sm disabled:opacity-40"
          >
            前へ
          </button>
          <span className="px-3 py-1 text-sm text-gray-600">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 rounded border text-sm disabled:opacity-40"
          >
            次へ
          </button>
        </div>
      )}
    </div>
  );
}
