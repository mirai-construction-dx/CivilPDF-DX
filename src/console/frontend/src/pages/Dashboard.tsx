import { useQuery } from "@tanstack/react-query";
import { listDocuments } from "../api/documents";
import { getStats } from "../api/stats";
import { useAuthStore } from "../store/auth";

const DOC_TYPE_LABELS: Record<string, string> = {
  drawing: "図面",
  specification: "仕様書",
  report: "報告書",
  contract: "契約書",
  other: "その他",
};

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  draft: { label: "下書き", cls: "bg-gray-100 text-gray-600" },
  pending_review: {
    label: "レビュー待ち",
    cls: "bg-yellow-100 text-yellow-700",
  },
  approved: { label: "承認済", cls: "bg-green-100 text-green-700" },
  rejected: { label: "却下", cls: "bg-red-100 text-red-700" },
};

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: number | string;
  sub?: string;
  color: string;
}) {
  return (
    <div className={`bg-white rounded-xl shadow p-6 border-l-4 ${color}`}>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-3xl font-bold text-gray-800 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function Dashboard() {
  const user = useAuthStore((s) => s.user);

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    staleTime: 60_000,
  });

  const { data: documents = [] } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(),
    staleTime: 30_000,
  });

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">ダッシュボード</h1>
      <p className="text-sm text-gray-500 mb-8">
        ようこそ、{user?.full_name || user?.email} さん
      </p>

      {/* KPI カード */}
      <div className="grid grid-cols-2 gap-6 mb-8 lg:grid-cols-4">
        <StatCard
          label="ドキュメント"
          value={stats?.total_documents ?? documents.length}
          sub={stats ? `今週 +${stats.uploaded_this_week}` : undefined}
          color="border-blue-500"
        />
        <StatCard
          label="承認待ち"
          value={stats?.pending_approvals ?? 0}
          color="border-orange-500"
        />
        <StatCard
          label="今月承認済"
          value={stats?.approved_this_month ?? 0}
          color="border-green-500"
        />
        <StatCard
          label="アクティブユーザー"
          value={stats?.active_users ?? 0}
          sub={stats ? formatBytes(stats.total_file_size_bytes) : undefined}
          color="border-purple-500"
        />
      </div>

      {/* 種別・ステータス分布 */}
      {stats &&
        (Object.keys(stats.by_type).length > 0 ||
          Object.keys(stats.by_status).length > 0) && (
          <div className="grid grid-cols-1 gap-6 mb-8 lg:grid-cols-2">
            {Object.keys(stats.by_type).length > 0 && (
              <div className="bg-white rounded-xl shadow p-6">
                <h2 className="text-sm font-semibold text-gray-600 mb-3">
                  種別分布
                </h2>
                <div className="space-y-2">
                  {Object.entries(stats.by_type).map(([type, count]) => (
                    <div
                      key={type}
                      className="flex items-center justify-between"
                    >
                      <span className="text-sm text-gray-600">
                        {DOC_TYPE_LABELS[type] ?? type}
                      </span>
                      <span className="text-sm font-medium text-gray-800">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {Object.keys(stats.by_status).length > 0 && (
              <div className="bg-white rounded-xl shadow p-6">
                <h2 className="text-sm font-semibold text-gray-600 mb-3">
                  ステータス分布
                </h2>
                <div className="space-y-2">
                  {Object.entries(stats.by_status).map(([status, count]) => {
                    const s = STATUS_LABELS[status] ?? {
                      label: status,
                      cls: "bg-gray-100 text-gray-600",
                    };
                    return (
                      <div
                        key={status}
                        className="flex items-center justify-between"
                      >
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs ${s.cls}`}
                        >
                          {s.label}
                        </span>
                        <span className="text-sm font-medium text-gray-800">
                          {count}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

      {/* 最近のドキュメント */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          最近のドキュメント
        </h2>
        {documents.length === 0 ? (
          <p className="text-gray-400 text-sm">ドキュメントがありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th scope="col" className="pb-2">
                    タイトル
                  </th>
                  <th scope="col" className="pb-2">
                    種別
                  </th>
                  <th scope="col" className="pb-2">
                    ステータス
                  </th>
                  <th scope="col" className="pb-2">
                    登録日
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.slice(0, 5).map((doc) => {
                  const s = STATUS_LABELS[doc.status] ?? {
                    label: doc.status,
                    cls: "bg-blue-100 text-blue-700",
                  };
                  return (
                    <tr
                      key={doc.id}
                      className="border-b last:border-0 hover:bg-gray-50"
                    >
                      <td className="py-2 font-medium">{doc.title}</td>
                      <td className="py-2 text-gray-500">
                        {DOC_TYPE_LABELS[doc.document_type] ??
                          doc.document_type}
                      </td>
                      <td className="py-2">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs ${s.cls}`}
                        >
                          {s.label}
                        </span>
                      </td>
                      <td className="py-2 text-gray-400">
                        {new Date(doc.created_at).toLocaleDateString("ja-JP")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
