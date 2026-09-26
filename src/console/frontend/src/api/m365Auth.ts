/**
 * Microsoft 365 Non-interactive (Client Credentials) Authentication
 *
 * Flow:
 *   Frontend (email only) → POST /auth/m365/login
 *   Backend: client_id + client_secret + tenant_id → MS Graph token
 *   Backend: validates user membership in tenant → issues our JWT
 *   Role is determined by CivilPDF-DX DB, NOT by M365 groups
 *
 * Required values (configured in system settings):
 *   1. tenant_id   — Azure AD Directory (tenant) ID
 *   2. client_id   — App registration Application (client) ID
 *   3. client_secret — App registration client secret value
 */

import { api } from "./client";
import type { TokenResponse, UserResponse } from "./auth";

export interface M365Config {
  tenantId: string;
  clientId: string;
  clientSecret: string;
  enabled: boolean;
}

export interface M365LoginRequest {
  email: string;
}

export interface M365LoginResponse extends TokenResponse {
  m365_user: {
    displayName: string;
    mail: string;
    userPrincipalName: string;
    id: string;
  };
  is_new_user: boolean;
}

export interface M365UserLookupResult {
  exists_in_tenant: boolean;
  display_name: string;
  user_principal_name: string;
  account_enabled: boolean;
}

/** POST /auth/m365/login — non-interactive client credentials flow */
export async function loginWithM365(email: string): Promise<M365LoginResponse> {
  const res = await api.post<M365LoginResponse>("/auth/m365/login", { email });
  return res.data;
}

/** POST /auth/m365/test-connection — validate tenant config */
export async function testM365Connection(
  config: Omit<M365Config, "enabled">,
): Promise<{ ok: boolean; tenant_name: string; user_count: number }> {
  const res = await api.post("/auth/m365/test-connection", config);
  return res.data;
}

/** GET /auth/m365/config — fetch current M365 config (secrets masked) */
export async function getM365Config(): Promise<
  Omit<M365Config, "clientSecret"> & { clientSecretSet: boolean }
> {
  const res = await api.get("/auth/m365/config");
  return res.data;
}

/** PUT /auth/m365/config — update M365 config */
export async function saveM365Config(config: M365Config): Promise<void> {
  await api.put("/auth/m365/config", config);
}

/** GET /users/m365/lookup?email= — check if email exists in M365 tenant */
export async function lookupM365User(
  email: string,
): Promise<M365UserLookupResult> {
  const res = await api.get<M365UserLookupResult>("/users/m365/lookup", {
    params: { email },
  });
  return res.data;
}

/** GET /auth/me after M365 login — same as normal getMe */
export async function getMe(): Promise<UserResponse> {
  const res = await api.get<UserResponse>("/auth/me");
  return res.data;
}
