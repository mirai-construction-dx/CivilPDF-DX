import { api } from "./client";

export type UserRole = "admin" | "manager" | "engineer" | "viewer";
export type UserStatus = "active" | "inactive" | "suspended";

export interface UserResponse {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: UserRole;
  status: UserStatus;
  last_login: string | null;
  created_at: string;
}

export interface CreateUserRequest {
  email: string;
  username: string;
  full_name: string;
  password: string;
  role?: UserRole;
}

export interface UpdateUserRequest {
  full_name?: string;
  role?: UserRole;
  status?: UserStatus;
  unlock?: boolean;
}

export async function listUsers(): Promise<UserResponse[]> {
  const res = await api.get<UserResponse[]>("/users/");
  return res.data;
}

export async function createUser(
  data: CreateUserRequest,
): Promise<UserResponse> {
  const res = await api.post<UserResponse>("/users/", data);
  return res.data;
}

export async function updateUser(
  id: string,
  data: UpdateUserRequest,
): Promise<UserResponse> {
  const res = await api.patch<UserResponse>(`/users/${id}`, data);
  return res.data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

export async function adminResetPassword(
  id: string,
  new_password: string,
): Promise<void> {
  await api.post(`/users/${id}/password-reset`, { new_password });
}

export async function exportPermissionsReport(): Promise<void> {
  const res = await api.get<Blob>("/users/permissions-report?format=csv", {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = "permissions-report.csv";
  a.click();
  URL.revokeObjectURL(url);
}
