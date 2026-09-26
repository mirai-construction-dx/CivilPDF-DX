// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { describe, it, expect, afterEach } from "vitest";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuthStore } from "../store/auth";

function setup(authenticated: boolean) {
  if (authenticated) {
    localStorage.setItem("access_token", "token123");
  } else {
    localStorage.clear();
  }
  useAuthStore.setState({ isAuthenticated: authenticated, user: null });
}

describe("ProtectedRoute", () => {
  afterEach(() => {
    localStorage.clear();
    useAuthStore.setState({ isAuthenticated: false, user: null });
  });

  it("renders children when authenticated", () => {
    setup(true);
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Protected Content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });

  it("redirects to login when not authenticated", () => {
    setup(false);
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Protected Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });
});
