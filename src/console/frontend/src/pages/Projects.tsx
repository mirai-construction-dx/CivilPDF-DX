import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listProjects, createProject, deleteProject } from "../api/projects";
import { useAuthStore } from "../store/auth";
import { ElectronicDeliveryModal } from "../components/ElectronicDeliveryModal";

export function Projects() {
  const qc = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const isAdmin = currentUser?.role === "admin";
  const canDownload = isAdmin || currentUser?.role === "manager";

  const {
    data: projects = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deliveryProject, setDeliveryProject] = useState<{
    id: string;
    name: string;
    code: string;
  } | null>(null);

  const filteredProjects = useMemo(() => {
    if (searchQuery === "") return projects;
    return projects.filter((p) =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase()),
    );
  }, [projects, searchQuery]);

  const create = useMutation({
    mutationFn: () => createProject({ name, code, description }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setShowForm(false);
      setName("");
      setCode("");
      setDescription("");
    },
  });

  const remove = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setConfirmDeleteId(null);
    },
  });

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">プロジェクト</h1>
        {isAdmin && (
          <button
            onClick={() => setShowForm(true)}
            className="bg-blue-700 hover:bg-blue-800 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            + 新規作成
          </button>
        )}
      </div>

      {showForm && (
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <h2 className="font-semibold text-gray-700 mb-4">プロジェクト作成</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="proj-name"
                className="block text-sm text-gray-600 mb-1"
              >
                プロジェクト名
              </label>
              <input
                id="proj-name"
                required
                className="w-full border rounded px-3 py-2 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label
                htmlFor="proj-code"
                className="block text-sm text-gray-600 mb-1"
              >
                コード
              </label>
              <input
                id="proj-code"
                required
                className="w-full border rounded px-3 py-2 text-sm"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <div className="col-span-2">
              <label
                htmlFor="proj-description"
                className="block text-sm text-gray-600 mb-1"
              >
                説明
              </label>
              <textarea
                id="proj-description"
                className="w-full border rounded px-3 py-2 text-sm"
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
          {create.error && (
            <p className="text-red-600 text-sm mt-2">{String(create.error)}</p>
          )}
          <div className="flex gap-3 mt-4">
            <button
              onClick={() => create.mutate()}
              disabled={create.isPending}
              className="bg-blue-700 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            >
              {create.isPending ? "作成中..." : "作成"}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-gray-600 px-4 py-2 rounded text-sm border"
            >
              キャンセル
            </button>
          </div>
        </div>
      )}

      {isError && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700 flex items-center justify-between gap-3"
        >
          <span>プロジェクトの読み込みに失敗しました</span>
          <button
            onClick={() => void refetch()}
            className="text-xs px-2 py-1 rounded border border-red-300 hover:bg-red-100"
          >
            再試行
          </button>
        </div>
      )}

      {/* Search bar */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="search"
          placeholder="プロジェクト名で検索..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[200px]"
          aria-label="プロジェクト名で検索"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            className="text-xs text-gray-500 underline px-2"
          >
            クリア
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl shadow overflow-x-auto">
        {isLoading ? (
          <p className="p-6 text-gray-400 text-sm">読み込み中...</p>
        ) : filteredProjects.length === 0 ? (
          <p className="p-6 text-gray-400 text-sm">
            {projects.length > 0
              ? "条件に一致するプロジェクトがありません"
              : "プロジェクトがありません"}
          </p>
        ) : (
          <table className="w-full text-sm min-w-[640px]">
            <thead className="border-b">
              <tr className="text-left text-gray-500">
                <th scope="col" className="px-4 py-3">
                  プロジェクト名
                </th>
                <th scope="col" className="px-4 py-3">
                  コード
                </th>
                <th scope="col" className="px-4 py-3">
                  ステータス
                </th>
                <th scope="col" className="px-4 py-3">
                  作成日
                </th>
                <th scope="col" className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filteredProjects.map((p) => (
                <tr
                  key={p.id}
                  className="border-b last:border-0 hover:bg-gray-50"
                >
                  <td className="px-4 py-3 font-medium">{p.name}</td>
                  <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                    {p.code}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        p.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {p.is_active ? "有効" : "無効"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {new Date(p.created_at).toLocaleDateString("ja-JP")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {canDownload && (
                        <button
                          onClick={() =>
                            setDeliveryProject({
                              id: p.id,
                              name: p.name,
                              code: p.code,
                            })
                          }
                          className="text-emerald-600 hover:text-emerald-800 text-xs whitespace-nowrap"
                          title="電子納品 ZIP 生成"
                        >
                          📦 電子納品
                        </button>
                      )}
                      {isAdmin &&
                        (confirmDeleteId === p.id ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="text-xs text-gray-500">
                              削除しますか?
                            </span>
                            <button
                              onClick={() => remove.mutate(p.id)}
                              disabled={remove.isPending}
                              className="text-red-600 hover:text-red-800 text-xs font-semibold disabled:opacity-50"
                            >
                              削除する
                            </button>
                            <button
                              onClick={() => setConfirmDeleteId(null)}
                              className="text-gray-500 hover:text-gray-700 text-xs"
                            >
                              キャンセル
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(p.id)}
                            className="text-red-500 hover:text-red-700 text-xs"
                          >
                            削除
                          </button>
                        ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {deliveryProject && (
        <ElectronicDeliveryModal
          projectId={deliveryProject.id}
          projectName={deliveryProject.name}
          projectCode={deliveryProject.code}
          onClose={() => setDeliveryProject(null)}
        />
      )}
    </div>
  );
}
