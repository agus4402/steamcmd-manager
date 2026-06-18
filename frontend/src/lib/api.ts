import type { Server, SteamCredentials, Template } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const TOKEN_KEY = "steamcmd_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    // Session expired / missing token: bounce to login (except on the login call).
    if (res.status === 401 && typeof window !== "undefined" && path !== "/api/auth/login") {
      setToken(null);
      window.location.href = "/login";
    }
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<{ username: string }>("/api/auth/me"),
  templates: () => request<Template[]>("/api/templates"),
  servers: () => request<Server[]>("/api/servers"),
  server: (id: string) => request<Server>(`/api/servers/${id}`),
  create: (body: { template_id: string; name: string; variables: Record<string, string> }) =>
    request<Server>("/api/servers", { method: "POST", body: JSON.stringify(body) }),
  patch: (id: string, body: { variables?: Record<string, string>; startup_template?: string }) =>
    request<Server>(`/api/servers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => request<null>(`/api/servers/${id}`, { method: "DELETE" }),
  action: (id: string, act: string, creds?: SteamCredentials) =>
    request<Server>(`/api/servers/${id}/${act}`, {
      method: "POST",
      body: creds ? JSON.stringify(creds) : undefined,
    }),
};

export function consoleWsUrl(id: string): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${wsBase}/api/servers/${id}/console${qs}`;
}

export { ApiError };
