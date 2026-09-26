import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getStats } from "../api/stats";
import { updateMe, changePassword } from "../api/auth";
import {
  getAiConfig,
  updateAiConfig,
  testAiConfig,
  type AiConfigUpdate,
} from "../api/aiSettings";
import { useAuthStore } from "../store/auth";

const ROLE_LABELS: Record<string, string> = {
  admin: "管理者",
  manager: "マネージャー",
  engineer: "技術担当",
  viewer: "閲覧のみ",
};

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center py-2 border-b last:border-0">
      <span className="text-sm text-gray-500 w-40 flex-shrink-0">{label}</span>
      <span className="text-sm font-medium text-gray-800">{value}</span>
    </div>
  );
}

export function Settings() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const isAdmin = user?.role === "admin";

  const [editName, setEditName] = useState(false);
  const [newName, setNewName] = useState("");
  const [editPass, setEditPass] = useState(false);
  const [currentPass, setCurrentPass] = useState("");
  const [newPass, setNewPass] = useState("");

  // AI設定 form state (admin only)
  const [aiApiKey, setAiApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [aiModelName, setAiModelName] = useState("claude-haiku-4-5-20251001");
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiTestResult, setAiTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    staleTime: 60_000,
    enabled: isAdmin,
  });

  const updateNameMutation = useMutation({
    mutationFn: () => updateMe(newName),
    onSuccess: (updated) => {
      setUser(updated);
      qc.invalidateQueries({ queryKey: ["me"] });
      setEditName(false);
      setNewName("");
    },
  });

  const changePassMutation = useMutation({
    mutationFn: () => changePassword(currentPass, newPass),
    onSuccess: () => {
      setEditPass(false);
      setCurrentPass("");
      setNewPass("");
    },
  });

  const { data: aiConfig } = useQuery({
    queryKey: ["ai-config"],
    queryFn: getAiConfig,
    staleTime: 60_000,
    enabled: isAdmin,
  });

  // Sync form state when aiConfig loads (runs once per load)
  useEffect(() => {
    if (aiConfig) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAiModelName(aiConfig.model_name);
      setAiEnabled(aiConfig.enabled);
    }
  }, [aiConfig]);

  const updateAiMutation = useMutation({
    mutationFn: (body: AiConfigUpdate) => updateAiConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-config"] });
      setAiApiKey("");
      setAiTestResult(null);
    },
  });

  const testAiMutation = useMutation({
    mutationFn: testAiConfig,
    onSuccess: (result) => {
      setAiTestResult(result);
    },
  });

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">設定</h1>
      <p className="text-sm text-gray-500 mb-8">
        システム設定とプロフィール情報
      </p>

      {/* プロフィール */}
      <div className="bg-white rounded-xl shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-700">
            プロフィール
          </h2>
          {!editName && (
            <button
              onClick={() => {
                setEditName(true);
                setNewName(user?.full_name || "");
              }}
              className="text-xs text-blue-600 hover:underline"
            >
              編集
            </button>
          )}
        </div>

        {editName ? (
          <div className="space-y-3">
            <div>
              <label
                htmlFor="edit-name"
                className="block text-sm text-gray-600 mb-1"
              >
                氏名
              </label>
              <input
                id="edit-name"
                className="w-full border rounded px-3 py-2 text-sm max-w-sm"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
            {updateNameMutation.error && (
              <p className="text-red-600 text-xs">
                {String(updateNameMutation.error)}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => updateNameMutation.mutate()}
                disabled={updateNameMutation.isPending || !newName.trim()}
                className="bg-blue-700 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
              >
                {updateNameMutation.isPending ? "保存中..." : "保存"}
              </button>
              <button
                onClick={() => setEditName(false)}
                className="text-gray-600 text-sm px-4 py-1.5 rounded border"
              >
                キャンセル
              </button>
            </div>
          </div>
        ) : (
          <>
            <InfoRow label="氏名" value={user?.full_name || "—"} />
            <InfoRow label="メールアドレス" value={user?.email || "—"} />
            <InfoRow label="ユーザー名" value={user?.username || "—"} />
            <InfoRow
              label="ロール"
              value={ROLE_LABELS[user?.role ?? ""] ?? "—"}
            />
            <InfoRow
              label="ステータス"
              value={user?.status === "active" ? "有効" : "無効"}
            />
          </>
        )}
      </div>

      {/* パスワード変更 */}
      <div className="bg-white rounded-xl shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-700">
            パスワード変更
          </h2>
          {!editPass && (
            <button
              onClick={() => setEditPass(true)}
              className="text-xs text-blue-600 hover:underline"
            >
              変更
            </button>
          )}
        </div>
        {editPass ? (
          <div className="space-y-3 max-w-sm">
            <div>
              <label
                htmlFor="current-pass"
                className="block text-sm text-gray-600 mb-1"
              >
                現在のパスワード
              </label>
              <input
                id="current-pass"
                type="password"
                autoComplete="current-password"
                className="w-full border rounded px-3 py-2 text-sm"
                value={currentPass}
                onChange={(e) => setCurrentPass(e.target.value)}
              />
            </div>
            <div>
              <label
                htmlFor="new-pass"
                className="block text-sm text-gray-600 mb-1"
              >
                新しいパスワード（8文字以上）
              </label>
              <input
                id="new-pass"
                type="password"
                autoComplete="new-password"
                className="w-full border rounded px-3 py-2 text-sm"
                value={newPass}
                onChange={(e) => setNewPass(e.target.value)}
              />
            </div>
            {changePassMutation.error && (
              <p role="alert" className="text-red-600 text-xs">
                {String(changePassMutation.error)}
              </p>
            )}
            {changePassMutation.isSuccess && (
              <p role="status" className="text-green-600 text-xs">
                パスワードを変更しました
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => changePassMutation.mutate()}
                disabled={
                  changePassMutation.isPending || !currentPass || !newPass
                }
                className="bg-blue-700 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
              >
                {changePassMutation.isPending ? "変更中..." : "変更する"}
              </button>
              <button
                onClick={() => {
                  setEditPass(false);
                  setCurrentPass("");
                  setNewPass("");
                }}
                className="text-gray-600 text-sm px-4 py-1.5 rounded border"
              >
                キャンセル
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            「変更」ボタンからパスワードを更新できます。
          </p>
        )}
      </div>

      {/* システム情報（管理者のみ） */}
      {isAdmin && (
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">
            システム情報
          </h2>
          {stats ? (
            <>
              <InfoRow label="総ドキュメント数" value={stats.total_documents} />
              <InfoRow label="アクティブユーザー" value={stats.active_users} />
              <InfoRow label="承認待ち" value={stats.pending_approvals} />
              <InfoRow label="今月承認済み" value={stats.approved_this_month} />
            </>
          ) : (
            <p className="text-sm text-gray-400">読み込み中...</p>
          )}
        </div>
      )}

      {/* AI設定（管理者のみ） */}
      {isAdmin && (
        <div className="bg-white rounded-xl shadow p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-1">
            AI モデル設定
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            Anthropic API
            キーを設定することで、文書分類・データ抽出・要約機能が利用できます。
          </p>

          <div className="space-y-4 max-w-lg">
            {/* API キー入力 */}
            <div>
              <label
                htmlFor="ai-api-key"
                className="block text-sm text-gray-600 mb-1"
              >
                Anthropic API キー
                {aiConfig?.has_api_key && (
                  <span className="ml-2 text-xs text-green-600 font-medium">
                    ✓ 設定済み
                  </span>
                )}
              </label>
              <div className="relative">
                <input
                  id="ai-api-key"
                  type={showApiKey ? "text" : "password"}
                  className="w-full border rounded px-3 py-2 text-sm pr-16"
                  value={aiApiKey}
                  placeholder={
                    aiConfig?.has_api_key
                      ? "変更する場合のみ入力してください"
                      : "sk-ant-..."
                  }
                  onChange={(e) => setAiApiKey(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600"
                >
                  {showApiKey ? "隠す" : "表示"}
                </button>
              </div>
            </div>

            {/* モデル名 */}
            <div>
              <label
                htmlFor="ai-model-name"
                className="block text-sm text-gray-600 mb-1"
              >
                モデル名
              </label>
              <input
                id="ai-model-name"
                type="text"
                className="w-full border rounded px-3 py-2 text-sm"
                value={aiModelName}
                onChange={(e) => setAiModelName(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">
                例: claude-haiku-4-5-20251001 / claude-sonnet-4-6
              </p>
            </div>

            {/* 有効/無効 */}
            <div className="flex items-center gap-3">
              <button
                type="button"
                role="switch"
                aria-checked={aiEnabled}
                onClick={() => setAiEnabled((v) => !v)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  aiEnabled ? "bg-blue-600" : "bg-gray-200"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    aiEnabled ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
              <span className="text-sm text-gray-700">
                {aiEnabled ? "AI 機能 有効" : "AI 機能 無効"}
              </span>
            </div>

            {/* テスト接続結果 */}
            {aiTestResult && (
              <div
                className={`text-sm px-3 py-2 rounded ${
                  aiTestResult.ok
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {aiTestResult.ok ? "✓ " : "✗ "}
                {aiTestResult.message}
              </div>
            )}
            {testAiMutation.error && (
              <p className="text-red-600 text-xs">
                {String(testAiMutation.error)}
              </p>
            )}
            {updateAiMutation.error && (
              <p className="text-red-600 text-xs">
                {String(updateAiMutation.error)}
              </p>
            )}
            {updateAiMutation.isSuccess && (
              <p className="text-green-600 text-xs">設定を保存しました</p>
            )}

            {/* ボタン */}
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => {
                  setAiTestResult(null);
                  testAiMutation.mutate();
                }}
                disabled={testAiMutation.isPending}
                className="border border-blue-600 text-blue-600 text-sm px-4 py-1.5 rounded hover:bg-blue-50 disabled:opacity-50"
              >
                {testAiMutation.isPending ? "接続中..." : "テスト接続"}
              </button>
              <button
                type="button"
                onClick={() => {
                  const body: AiConfigUpdate = {
                    model_name: aiModelName || undefined,
                    enabled: aiEnabled,
                  };
                  if (aiApiKey) body.api_key = aiApiKey;
                  updateAiMutation.mutate(body);
                }}
                disabled={updateAiMutation.isPending}
                aria-label="AI設定を保存"
                className="bg-blue-700 text-white text-sm px-4 py-1.5 rounded disabled:opacity-50"
              >
                {updateAiMutation.isPending ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* セキュリティ設定（表示のみ） */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-base font-semibold text-gray-700 mb-4">
          セキュリティポリシー
        </h2>
        <InfoRow label="パスワード有効期限" value="90日" />
        <InfoRow label="セッションタイムアウト" value="8時間" />
        <InfoRow label="MFA" value="無効（予定）" />
        <p className="text-xs text-gray-400 mt-3">
          セキュリティポリシーの変更は管理者にお問い合わせください。
        </p>
      </div>
    </div>
  );
}
