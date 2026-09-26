import { Outlet, NavLink, useNavigate } from "react-router";
import { useAuthStore } from "../store/auth";

const navItems = [
  { to: "/dashboard", label: "ダッシュボード" },
  { to: "/documents", label: "ドキュメント" },
  { to: "/projects", label: "プロジェクト" },
  { to: "/workflows", label: "承認ワークフロー" },
  { to: "/users", label: "ユーザー管理" },
  { to: "/audit-logs", label: "監査ログ" },
];

export function Layout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-56 bg-blue-900 text-white flex flex-col">
        <div className="px-4 py-5 text-xl font-bold border-b border-blue-700">
          CivilPDF DX
        </div>
        <nav className="flex-1 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block px-4 py-2 text-sm hover:bg-blue-800 transition-colors ${
                  isActive ? "bg-blue-700 font-semibold" : ""
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-blue-700 text-sm">
          <p className="text-blue-300 truncate">{user?.email ?? ""}</p>
          <button
            onClick={handleLogout}
            className="mt-2 text-blue-200 hover:text-white underline text-xs"
          >
            ログアウト
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
