import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { UserResponse } from "../api/auth";
import { useAuthStore } from "../store/auth";
import { adminResetPassword, exportPermissionsReport } from "../api/users";

async function listUsers(): Promise<UserResponse[]> {
  const res = await api.get<UserResponse[]>("/users/");
  return res.data;
}

async function createUser(body: {
  email: string;
  username: string;
  full_name: string;
  password: string;
  role: string;
}): Promise<UserResponse> {
  const res = await api.post<UserResponse>("/users/", body);
  return res.data;
}

async function updateUserStatus(
  id: string,
  status: string,
): Promise<UserResponse> {
  const res = await api.patch<UserResponse>(`/users/${id}`, { status });
  return res.data;
}

const roleLabel: Record<string, string> = {
  admin: "管理者",
  manager: "マネージャー",
  engineer: "エンジニア",
  viewer: "閲覧者",
};

const initialForm = {
  email: "",
  username: "",
  full_name: "",
  password: "",
  role: "engineer",
};

export function Users() {
  const qc = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const {
    data: users = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [confirmDisableId, setConfirmDisableId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<UserResponse | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetError, setResetError] = useState("");

  const create = useMutation({
    mutationFn: () => createUser(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
      setForm(initialForm);
    },
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateUserStatus(id, status === "active" ? "inactive" : "active"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setConfirmDisableId(null);
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: () => adminResetPassword(resetTarget!.id, resetPassword),
    onSuccess: () => {
      setResetTarget(null);
      setResetPassword("");
      setResetError("");
    },
    onError: () =>
      setResetError("再設定に失敗しました（8文字以上・2種以上の文字種）"),
  });

  if (currentUser?.role !== "admin" && currentUser?.role !== "manager") {
    return (
      <div className="p-8">
        <p className="text-gray-500">この画面へのアクセス権限がありません</p>
      </div>
    );
  }

  const isAdmin = currentUser?.role === "admin";

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">ユーザー管理</h1>
        <div className="flex gap-2">
          {isAdmin && (
            <>
              <button
                type="button"
                onClick={() => void exportPermissionsReport()}
                className="border border-gray-300 text-gray-700 text-sm px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors"
              >
                権限棚卸し CSV
              </button>
              <button
                onClick={() => setShowForm(true)}
                className="bg-blue-700 hover:bg-blue-800 text-white text-sm px-4 py-2 rounded-lg transition-colors"
              >
                + ユーザー追加
              </button>
            </>
          )}
        </div>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <h2 className="font-semibold text-gray-700 mb-4">新規ユーザー作成</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="user-email"
                className="block text-sm text-gray-600 mb-1"
              >
                メールアドレス
              </label>
              <input
                id="user-email"
                type="email"
                required
                autoComplete="email"
                className="w-full border rounded px-3 py-2 text-sm"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div>
              <label
                htmlFor="user-username"
                className="block text-sm text-gray-600 mb-1"
              >
                ユーザー名
              </label>
              <input
                id="user-username"
                required
                autoComplete="username"
                className="w-full border rounded px-3 py-2 text-sm"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
            </div>
            <div>
              <label
                htmlFor="user-full-name"
                className="block text-sm text-gray-600 mb-1"
              >
                氏名
              </label>
              <input
                id="user-full-name"
                required
                autoComplete="name"
                className="w-full border rounded px-3 py-2 text-sm"
                value={form.full_name}
                onChange={(e) =>
                  setForm({ ...form, full_name: e.target.value })
                }
              />
            </div>
            <div>
              <label
                htmlFor="user-password"
                className="block text-sm text-gray-600 mb-1"
              >
                パスワード（8文字以上）
              </label>
              <input
                id="user-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                className="w-full border rounded px-3 py-2 text-sm"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <div>
              <label
                htmlFor="user-role"
                className="block text-sm text-gray-600 mb-1"
              >
                ロール
              </label>
              <select
                id="user-role"
                className="w-full border rounded px-3 py-2 text-sm"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {Object.entries(roleLabel).map(([val, lbl]) => (
                  <option key={val} value={val}>
                    {lbl}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {create.error && (
            <p role="alert" className="text-red-600 text-sm mt-2">
              {String(create.error)}
            </p>
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
              onClick={() => {
                setShowForm(false);
                setForm(initialForm);
              }}
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
          <span>ユーザー一覧の読み込みに失敗しました</span>
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
        ) : (
          <table className="w-full text-sm min-w-[760px]">
            <thead className="border-b">
              <tr className="text-left text-gray-500">
                <th scope="col" className="px-4 py-3">
                  名前
                </th>
                <th scope="col" className="px-4 py-3">
                  メールアドレス
                </th>
                <th scope="col" className="px-4 py-3">
                  ロール
                </th>
                <th scope="col" className="px-4 py-3">
                  ステータス
                </th>
                <th scope="col" className="px-4 py-3">
                  最終ログイン
                </th>
                {isAdmin && <th scope="col" className="px-4 py-3"></th>}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  className="border-b last:border-0 hover:bg-gray-50"
                >
                  <td className="px-4 py-3 font-medium">{u.full_name}</td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700">
                      {roleLabel[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        u.status === "active"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {u.status === "active" ? "有効" : "無効"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {u.last_login
                      ? new Date(u.last_login).toLocaleDateString("ja-JP")
                      : "—"}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      {u.id !== currentUser?.id && (
                        <span className="inline-flex items-center gap-2">
                          {confirmDisableId === u.id ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="text-xs text-gray-500">
                                無効化しますか?
                              </span>
                              <button
                                onClick={() =>
                                  toggleStatus.mutate({
                                    id: u.id,
                                    status: u.status,
                                  })
                                }
                                disabled={toggleStatus.isPending}
                                className="text-red-600 hover:text-red-800 text-xs font-semibold disabled:opacity-50"
                              >
                                無効化する
                              </button>
                              <button
                                onClick={() => setConfirmDisableId(null)}
                                className="text-gray-500 hover:text-gray-700 text-xs"
                              >
                                キャンセル
                              </button>
                            </span>
                          ) : u.status === "active" ? (
                            <button
                              onClick={() => setConfirmDisableId(u.id)}
                              className="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
                            >
                              無効化
                            </button>
                          ) : (
                            <button
                              onClick={() =>
                                toggleStatus.mutate({
                                  id: u.id,
                                  status: u.status,
                                })
                              }
                              className="text-xs px-2 py-1 rounded border border-green-300 text-green-600 hover:bg-green-50 transition-colors"
                            >
                              有効化
                            </button>
                          )}
                          <button
                            onClick={() => {
                              setResetTarget(u);
                              setResetPassword("");
                              setResetError("");
                            }}
                            className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
                          >
                            パスワード再設定
                          </button>
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {resetTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-user-title"
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={() => setResetTarget(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="reset-user-title"
              className="text-lg font-bold text-gray-800 mb-1"
            >
              パスワード再設定
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              {resetTarget.full_name}（{resetTarget.email}
              ）のパスワードを再設定します。
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                resetPasswordMutation.mutate();
              }}
              className="space-y-3"
            >
              <label
                htmlFor="reset-user-password"
                className="block text-sm font-medium text-gray-700"
              >
                新しいパスワード（8文字以上・2種以上の文字種）
              </label>
              <input
                id="reset-user-password"
                type="password"
                autoComplete="new-password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {resetError && (
                <p role="alert" className="text-red-600 text-xs">
                  {resetError}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setResetTarget(null)}
                  className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  disabled={resetPasswordMutation.isPending}
                  className="px-4 py-1.5 text-sm bg-blue-700 hover:bg-blue-800 text-white rounded-lg disabled:opacity-50"
                >
                  {resetPasswordMutation.isPending ? "送信中..." : "再設定"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
