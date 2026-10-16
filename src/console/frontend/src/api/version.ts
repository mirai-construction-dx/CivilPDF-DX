/**
 * Running server info from the backend liveness probe (`/health`, proxied by
 * nginx in production). Fields are null when unavailable so the UI can omit
 * them instead of showing stale hard-coded values.
 */
export interface ServerInfo {
  version: string | null;
  /** `"staging"` / `"production"` / `"development"`, or null when unknown. */
  environment: string | null;
}

export async function fetchServerInfo(): Promise<ServerInfo> {
  try {
    const res = await fetch("/health", {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return { version: null, environment: null };
    const body: unknown = await res.json();
    const version =
      body && typeof body === "object"
        ? (body as { version?: unknown }).version
        : undefined;
    const environment =
      body && typeof body === "object"
        ? (body as { environment?: unknown }).environment
        : undefined;
    return {
      version: typeof version === "string" && version ? version : null,
      environment:
        typeof environment === "string" && environment ? environment : null,
    };
  } catch {
    return { version: null, environment: null };
  }
}

export async function fetchServerVersion(): Promise<string | null> {
  return (await fetchServerInfo()).version;
}

export async function fetchServerEnvironment(): Promise<string | null> {
  return (await fetchServerInfo()).environment;
}
