import type {
  BackupJob,
  ConnectStart,
  ConnectStatus,
  Integration,
  IntegrationTunnel,
  Notification,
  ScheduleActionType,
  ScheduledAction,
  Server,
  Snapshot,
  Stats,
  SteamCredentials,
  Template,
  WorkshopMod,
  ImportPreview,
  ImportResult,
  ModDetails,
  SearchResult,
  SyncResult,
  AutoUpdateMode,
  ConfigFilesList,
  ConfigFileContent,
  ConfigWriteResult,
} from "./types";

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

// Abort slow requests so a hung backend never freezes the UI indefinitely.
const REQUEST_TIMEOUT_MS = 15000;
// Volume operations (backup/restore/clone) tar or copy the whole data dir and
// can legitimately run for many minutes — they get a much longer ceiling.
const LONG_OP_TIMEOUT_MS = 20 * 60 * 1000;

async function request<T>(
  path: string,
  opts: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const token = getToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...opts,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(opts.headers ?? {}),
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
  health: () => request<{ status?: string; db?: boolean; agent?: boolean }>("/api/health/full"),
  templates: () => request<Template[]>("/api/templates"),
  servers: () => request<Server[]>("/api/servers"),
  server: (id: string) => request<Server>(`/api/servers/${id}`),
  stats: (id: string) => request<Stats>(`/api/servers/${id}/stats`),
  create: (body: { template_id: string; name: string; variables: Record<string, string> }) =>
    request<Server>("/api/servers", { method: "POST", body: JSON.stringify(body) }),
  patch: (
    id: string,
    body: { variables?: Record<string, string>; startup_template?: string; steam_branch?: string | null },
  ) =>
    request<Server>(`/api/servers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => request<null>(`/api/servers/${id}`, { method: "DELETE" }),
  action: (id: string, act: string, creds?: SteamCredentials) =>
    request<Server>(`/api/servers/${id}/${act}`, {
      method: "POST",
      body: creds ? JSON.stringify(creds) : undefined,
    }),
  clone: (id: string, name: string) =>
    request<Server>(
      `/api/servers/${id}/clone`,
      { method: "POST", body: JSON.stringify({ name }) },
      LONG_OP_TIMEOUT_MS,
    ),
  backups: (id: string) => request<Snapshot[]>(`/api/servers/${id}/backups`),
  // Backups run as a background job: this returns immediately; poll backupStatus.
  createBackup: (id: string) => request<BackupJob>(`/api/servers/${id}/backups`, { method: "POST" }),
  backupStatus: (id: string) => request<BackupJob>(`/api/servers/${id}/backups/status`),
  restoreBackup: (id: string, snapshotId: string, startAfter: boolean = false) =>
    request<Server>(
      `/api/servers/${id}/backups/${snapshotId}/restore`,
      { method: "POST", body: JSON.stringify({ start_after: startAfter }) },
      LONG_OP_TIMEOUT_MS,
    ),
  deleteBackup: (id: string, snapshotId: string) =>
    request<null>(`/api/servers/${id}/backups/${snapshotId}`, { method: "DELETE" }),
  updateBackupConfig: (id: string, maxBackups: number) =>
    request<Server>(`/api/servers/${id}/backup-config`, {
      method: "PATCH",
      body: JSON.stringify({ max_backups: maxBackups }),
    }),

  schedule: (id: string) => request<ScheduledAction[]>(`/api/servers/${id}/schedule`),
  allSchedules: () => request<ScheduledAction[]>("/api/schedule"),
  createSchedule: (id: string, body: { action: ScheduleActionType; cron: string; enabled?: boolean }) =>
    request<ScheduledAction>(`/api/servers/${id}/schedule`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSchedule: (
    id: string,
    actionId: string,
    body: { action?: ScheduleActionType; cron?: string; enabled?: boolean },
  ) =>
    request<ScheduledAction>(`/api/servers/${id}/schedule/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteSchedule: (id: string, actionId: string) =>
    request<null>(`/api/servers/${id}/schedule/${actionId}`, { method: "DELETE" }),

  mods: (id: string) => request<WorkshopMod[]>(`/api/servers/${id}/mods`),
  addMod: (id: string, item: string, name?: string) =>
    request<WorkshopMod>(`/api/servers/${id}/mods`, {
      method: "POST",
      body: JSON.stringify({ item, name: name || null }),
    }),
  configFiles: (id: string) => request<ConfigFilesList>(`/api/servers/${id}/config/files`),
  configFile: (id: string, path: string) =>
    request<ConfigFileContent>(`/api/servers/${id}/config/file?path=${encodeURIComponent(path)}`),
  writeConfigFile: (
    id: string,
    body: {
      path: string;
      content?: string;
      changes?: Record<string, string>;
      base_mtime?: number;
      restart?: boolean;
    },
  ) =>
    request<ConfigWriteResult>(`/api/servers/${id}/config/file`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  restoreConfigFile: (id: string, path: string, restart = false) =>
    request<ConfigWriteResult>(`/api/servers/${id}/config/file/restore`, {
      method: "POST",
      body: JSON.stringify({ path, restart }),
    }),
  removeMod: (id: string, modId: string) =>
    request<null>(`/api/servers/${id}/mods/${modId}`, { method: "DELETE" }),
  retryMod: (id: string, modId: string) =>
    request<WorkshopMod>(`/api/servers/${id}/mods/${modId}/retry`, { method: "POST" }),
  updateMod: (id: string, modId: string) =>
    request<WorkshopMod>(`/api/servers/${id}/mods/${modId}/update`, { method: "POST" }),
  checkModUpdates: (id: string) =>
    request<WorkshopMod[]>(`/api/servers/${id}/mods/check-updates`, { method: "POST" }),
  updateAllMods: (id: string) =>
    request<WorkshopMod[]>(`/api/servers/${id}/mods/update-all`, { method: "POST" }),
  syncMods: (id: string) =>
    request<SyncResult>(`/api/servers/${id}/mods/sync`, { method: "POST" }),
  setWorkshopAutoUpdate: (id: string, mode: AutoUpdateMode) =>
    request<{ mode: AutoUpdateMode }>(`/api/servers/${id}/workshop/auto-update`, {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
  modDetails: (itemId: string, provider = "steam") =>
    request<ModDetails>(`/api/workshop/mod/${itemId}?provider=${provider}`),
  searchWorkshop: (params: {
    gameId: number;
    query?: string;
    page?: number;
    pageSize?: number;
    sortBy?: string;
  }) => {
    const qs = new URLSearchParams({
      gameId: String(params.gameId),
      query: params.query ?? "",
      page: String(params.page ?? 1),
      pageSize: String(params.pageSize ?? 30),
    });
    if (params.sortBy) qs.set("sortBy", params.sortBy);
    return request<SearchResult>(`/api/workshop/search?${qs.toString()}`);
  },
  importPreview: (id: string, input: string) =>
    request<ImportPreview>(`/api/servers/${id}/mods/import`, {
      method: "POST",
      body: JSON.stringify({ input }),
    }),
  importInstall: (id: string, input: string, install: string[]) =>
    request<ImportResult>(`/api/servers/${id}/mods/import`, {
      method: "POST",
      body: JSON.stringify({ input, install }),
    }),

  notifications: {
    list: (unreadOnly = false, limit = 100) =>
      request<Notification[]>(`/api/notifications?unread_only=${unreadOnly}&limit=${limit}`),
    unreadCount: () => request<{ count: number }>("/api/notifications/unread-count"),
    markRead: (id: string) => request<null>(`/api/notifications/${id}/read`, { method: "POST" }),
    markAllRead: () => request<{ count: number }>("/api/notifications/read-all", { method: "POST" }),
    remove: (id: string) => request<null>(`/api/notifications/${id}`, { method: "DELETE" }),
    clearAll: () => request<null>("/api/notifications", { method: "DELETE" }),
  },

  integrations: {
    list: () => request<Integration[]>("/api/integrations"),
    get: (id: string) => request<Integration>(`/api/integrations/${id}`),
    connect: (provider: string) =>
      request<ConnectStart>(`/api/integrations/${provider}/connect`, { method: "POST" }),
    connectStatus: (id: string) =>
      request<ConnectStatus>(`/api/integrations/${id}/connect/status`),
    sync: (id: string) => request<Integration>(`/api/integrations/${id}/sync`, { method: "POST" }),
    disconnect: (id: string) => request<null>(`/api/integrations/${id}`, { method: "DELETE" }),
    tunnels: (id: string) => request<IntegrationTunnel[]>(`/api/integrations/${id}/tunnels`),
    createTunnel: (
      id: string,
      body: { server_id: string | null; local_port: number; protocol: string; name?: string | null },
    ) =>
      request<IntegrationTunnel>(`/api/integrations/${id}/tunnels`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deleteTunnel: (id: string, tunnelId: string) =>
      request<null>(`/api/integrations/${id}/tunnels/${tunnelId}`, { method: "DELETE" }),
  },
};

export function consoleWsUrl(id: string): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${wsBase}/api/servers/${id}/console${qs}`;
}

export { ApiError };
