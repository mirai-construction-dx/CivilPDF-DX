import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
  login,
  getMe,
  requestPasswordReset,
  OIDC_LOGIN_URL,
} from "../api/auth";
import { loginWithM365, getMe as getM365Me } from "../api/m365Auth";
import { useAuthStore } from "../store/auth";

type LoginTab = "password" | "m365";

export function Login() {
  const [tab, setTab] = useState<LoginTab>("password");

  // Password login
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // M365 login
  const [m365Email, setM365Email] = useState("");
  const [m365Error, setM365Error] = useState("");
  const [m365Loading, setM365Loading] = useState(false);

  // Password reset request dialog
  const [showReset, setShowReset] = useState(false);
  const [resetEmail, setResetEmail] = useState("");
  const [resetMessage, setResetMessage] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetLoading, setResetLoading] = useState(false);

  const setUser = useAuthStore((s) => s.setUser);
  const navigate = useNavigate();

  // OIDC callback returns tokens in the URL fragment (#access_token=...).
  useEffect(() => {
    const fragment = window.location.hash;
    if (!fragment.includes("access_token=")) return;
    const params = new URLSearchParams(fragment.slice(1));
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");
    if (!access) return;
    localStorage.setItem("access_token", access);
    if (refresh) localStorage.setItem("refresh_token", refresh);
    getMe()
      .then((me) => {
        setUser(me);
        window.location.hash = "";
        navigate("/dashboard");
      })
      .catch(() => setError("OIDC セッションの取得に失敗しました"));
  }, [navigate, setUser]);

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const tokens = await login(email, password);
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      const me = await getMe();
      setUser(me);
      navigate("/dashboard");
    } catch {
      setError("メールアドレスまたはパスワードが正しくありません");
    } finally {
      setLoading(false);
    }
  }

  async function handleM365Submit(e: React.FormEvent) {
    e.preventDefault();
    setM365Error("");
    setM365Loading(true);
    try {
      const res = await loginWithM365(m365Email);
      localStorage.setItem("access_token", res.access_token);
      localStorage.setItem("refresh_token", res.refresh_token);
      const me = await getM365Me();
      setUser(me);
      navigate("/dashboard");
    } catch {
      setM365Error(
        "Microsoft 365 での認証に失敗しました。\nメールアドレスがこのシステムに登録されているか確認してください。",
      );
    } finally {
      setM365Loading(false);
    }
  }

  async function handleResetSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResetError("");
    setResetMessage("");
    setResetLoading(true);
    try {
      const result = await requestPasswordReset(resetEmail);
      setResetMessage(result.message ?? "リセット手続きを受け付けました");
      setResetEmail("");
    } catch {
      setResetError(
        "リセット申請に失敗しました。管理者にお問い合わせください。",
      );
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-blue-900 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-sm">
        {/* Brand */}
        <h1 className="text-2xl font-bold text-gray-800 mb-1">CivilPDF DX</h1>
        <p className="text-sm text-gray-500 mb-5">
          建設業向け図面・書類管理システム
        </p>

        {/* Tab switcher */}
        <div
          role="tablist"
          aria-label="ログイン方法"
          className="flex rounded-lg overflow-hidden border border-gray-200 mb-5 text-sm"
        >
          <button
            type="button"
            role="tab"
            id="tab-password"
            aria-selected={tab === "password"}
            aria-controls="panel-password"
            className={`flex-1 py-2 font-medium transition-colors ${
              tab === "password"
                ? "bg-blue-700 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
            onClick={() => {
              setTab("password");
              setError("");
              setM365Error("");
            }}
          >
            ID/パスワード
          </button>
          <button
            type="button"
            role="tab"
            id="tab-m365"
            aria-selected={tab === "m365"}
            aria-controls="panel-m365"
            className={`flex-1 py-2 font-medium transition-colors flex items-center justify-center gap-1.5 ${
              tab === "m365"
                ? "bg-blue-700 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
            onClick={() => {
              setTab("m365");
              setError("");
              setM365Error("");
            }}
          >
            <M365Icon active={tab === "m365"} />
            Microsoft 365
          </button>
        </div>

        {/* Password login form */}
        {tab === "password" && (
          <form
            id="panel-password"
            role="tabpanel"
            aria-labelledby="tab-password"
            onSubmit={handlePasswordSubmit}
            className="space-y-4"
          >
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                メールアドレス
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                パスワード
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {error && (
              <p role="alert" className="text-red-600 text-sm">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-700 hover:bg-blue-800 text-white rounded-lg py-2 text-sm font-semibold disabled:opacity-50 transition-colors"
            >
              {loading ? "ログイン中..." : "ログイン"}
            </button>
            <button
              type="button"
              onClick={() => {
                window.location.href = OIDC_LOGIN_URL;
              }}
              className="w-full border border-gray-300 text-gray-700 rounded-lg py-2 text-sm font-semibold hover:bg-gray-50 transition-colors"
            >
              組織アカウントでログイン (SSO)
            </button>
            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  setResetMessage("");
                  setResetError("");
                  setShowReset(true);
                }}
                className="text-xs text-blue-600 hover:underline"
              >
                パスワードを忘れた場合
              </button>
            </div>
          </form>
        )}

        {/* Microsoft 365 non-interactive login */}
        {tab === "m365" && (
          <form
            id="panel-m365"
            role="tabpanel"
            aria-labelledby="tab-m365"
            onSubmit={handleM365Submit}
            className="space-y-4"
          >
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-700 leading-relaxed">
              <strong>非対話式認証</strong>
              <br />
              メールアドレスを入力するとシステムが Microsoft 365
              テナントに対して自動認証します。パスワード入力は不要です。
            </div>
            <div>
              <label
                htmlFor="m365email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Microsoft 365 メールアドレス
              </label>
              <input
                id="m365email"
                type="email"
                autoComplete="email"
                value={m365Email}
                onChange={(e) => setM365Email(e.target.value)}
                required
                placeholder="user@contoso.onmicrosoft.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {m365Error && (
              <p
                role="alert"
                className="text-red-600 text-xs whitespace-pre-line"
              >
                {m365Error}
              </p>
            )}
            <button
              type="submit"
              disabled={m365Loading}
              className="w-full bg-blue-700 hover:bg-blue-800 text-white rounded-lg py-2.5 text-sm font-semibold disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              {m365Loading ? (
                <>
                  <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
                  Microsoft 365 で認証中...
                </>
              ) : (
                <>
                  <M365Icon active />
                  Microsoft 365 でログイン
                </>
              )}
            </button>
            <p className="text-xs text-gray-400 text-center">
              ロールはシステム管理者により設定されます
            </p>
          </form>
        )}
      </div>

      {showReset && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-dialog-title"
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={() => setShowReset(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="reset-dialog-title"
              className="text-lg font-bold text-gray-800 mb-2"
            >
              パスワード再設定
            </h2>
            <p className="text-xs text-gray-500 mb-4 leading-relaxed">
              登録済みメールアドレスを入力してください。管理者経由で再設定手続きを案内します。
            </p>
            <form onSubmit={handleResetSubmit} className="space-y-3">
              <label
                htmlFor="reset-email"
                className="block text-sm font-medium text-gray-700"
              >
                メールアドレス
              </label>
              <input
                id="reset-email"
                type="email"
                autoComplete="email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {resetMessage && (
                <p role="status" className="text-green-700 text-xs">
                  {resetMessage}
                </p>
              )}
              {resetError && (
                <p role="alert" className="text-red-600 text-xs">
                  {resetError}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowReset(false)}
                  className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  disabled={resetLoading}
                  className="px-4 py-1.5 text-sm bg-blue-700 hover:bg-blue-800 text-white rounded-lg disabled:opacity-50"
                >
                  {resetLoading ? "送信中..." : "送信"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function M365Icon({ active }: { active: boolean }) {
  const color = active ? "#ffffff" : "#0078d4";
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 23 23"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="1" y="1" width="10" height="10" fill={color} opacity="0.9" />
      <rect x="12" y="1" width="10" height="10" fill={color} opacity="0.7" />
      <rect x="1" y="12" width="10" height="10" fill={color} opacity="0.7" />
      <rect x="12" y="12" width="10" height="10" fill={color} opacity="0.9" />
    </svg>
  );
}
