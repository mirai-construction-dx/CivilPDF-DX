/**
 * Running server version from the backend liveness probe (`/health`, proxied by
 * nginx in production). Returns null when unavailable so the UI can omit it
 * instead of showing a stale hard-coded version.
 */
export async function fetchServerVersion(): Promise<string | null> {
  try {
    const res = await fetch("/health", {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    const body: unknown = await res.json();
    const version =
      body && typeof body === "object"
        ? (body as { version?: unknown }).version
        : undefined;
    return typeof version === "string" && version ? version : null;
  } catch {
    return null;
  }
}
