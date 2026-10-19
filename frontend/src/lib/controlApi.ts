import { ApiError, STOP_TIMEOUT_MS } from "./api";
import type { ServerQuery, ServerStatus } from "./types";

/**
 * Client for the public per-server control page (/control/<id>). Kept apart from
 * `api` on purpose: it uses a server-password token (never the admin one), and a
 * 401 here just means "ask for the password again", not "go to /login".
 * Requests are same-origin (app/api/control proxies them to the backend), so the
 * page also works through a single public address such as a Playit tunnel.
 */

export interface ControlMeta {
  name: string;
  game: string;
  /** False when the server has no SERVER_PASSWORD (page disabled). */
  enabled: boolean;
}

export interface ControlServer {
  id: string;
  name: string;
  game: string;
  status: ServerStatus;
  ports: {
    name: string;
    protocol: string;
    host_port: number;
    /** Public address of this port's own tunnel (Playit), when it has one. */
    public_address: string | null;
  }[];
  /** Host of the panel's tunnel: opened through it, LAN host:port is meaningless. */
  panel_public_host: string | null;
}

export type ControlAction = "start" | "stop" | "restart";

const tokenKey = (serverId: string) => `steamcmd_control_${serverId}`;

export function getControlToken(serverId: string): string | null {
  try {
    return window.localStorage.getItem(tokenKey(serverId));
  } catch {
    return null;
  }
}

export function setControlToken(serverId: string, token: string | null): void {
  try {
    if (token) window.localStorage.setItem(tokenKey(serverId), token);
    else window.localStorage.removeItem(tokenKey(serverId));
  } catch {
    /* storage unavailable: the session just won't persist */
  }
}

async function request<T>(
  serverId: string,
  path: string,
  opts: RequestInit = {},
  timeoutMs = 15000,
): Promise<T> {
  const token = getControlToken(serverId);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`/api/control/${serverId}${path}`, {
      ...opts,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError("request timed out", 408);
    }
    throw new ApiError("network error", 0);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    if (res.status === 401 && path !== "/login") setControlToken(serverId, null);
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const controlApi = {
  meta: (serverId: string) => request<ControlMeta>(serverId, "/meta"),
  login: async (serverId: string, password: string) => {
    const { access_token } = await request<{ access_token: string }>(serverId, "/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    setControlToken(serverId, access_token);
  },
  server: (serverId: string) => request<ControlServer>(serverId, ""),
  query: (serverId: string) => request<ServerQuery>(serverId, "/query"),
  // Stop/restart wait for the game to save and exit, like the panel's actions.
  action: (serverId: string, action: ControlAction) =>
    request<ControlServer>(serverId, `/${action}`, { method: "POST" }, STOP_TIMEOUT_MS),
};
