import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Login } from "./pages/Login";
import { EnterpriseLayout } from "./components/enterprise/EnterpriseLayout";
import { useAuthStore } from "./store/auth";
import { getMe } from "./api/auth";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

export default function App() {
  const setUser = useAuthStore((s) => s.setUser);

  // Rehydrate the authenticated user on reload. When a real access_token
  // exists in localStorage the interceptor sends it as Bearer. In dev-bypass
  // mode (DEBUG=true, no token) the backend's get_current_user returns the
  // dev admin user unconditionally, so the call still succeeds.
  useEffect(() => {
    const { user, isAuthenticated } = useAuthStore.getState();
    if (user || !isAuthenticated) return;
    getMe()
      .then(setUser)
      .catch(() => {
        // 401 is handled by the axios interceptor (redirect to /login);
        // ignore other transient errors and keep the current auth state.
      });
  }, [setUser]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <EnterpriseLayout />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
