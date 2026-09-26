import { api } from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: "admin" | "manager" | "engineer" | "viewer";
  status: "active" | "inactive" | "suspended";
  created_at: string;
  last_login: string | null;
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const res = await api.post<TokenResponse>("/auth/token", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return res.data;
}

export async function getMe(): Promise<UserResponse> {
  const res = await api.get<UserResponse>("/auth/me");
  return res.data;
}

export async function updateMe(full_name: string): Promise<UserResponse> {
  const res = await api.patch<UserResponse>("/auth/me", { full_name });
  return res.data;
}

export async function changePassword(
  current_password: string,
  new_password: string,
): Promise<void> {
  await api.post("/auth/me/password", { current_password, new_password });
}

export async function requestPasswordReset(
  email: string,
): Promise<{ message: string }> {
  const res = await api.post<{ message: string }>(
    "/auth/password-reset/request",
    {
      email,
    },
  );
  return res.data;
}

export const OIDC_LOGIN_URL = "/api/v1/auth/oidc/login";
