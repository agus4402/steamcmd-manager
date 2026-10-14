export type ServerStatus =
  | "created"
  | "installing"
  | "updating"
  | "running"
  | "stopped"
  | "errored";

export interface Port {
  name: string;
  protocol: string;
  host_port: number;
  is_primary: boolean;
}

export interface Progress {
  percent: number;
  downloaded: number;
  total: number;
}

export interface Server {
  id: string;
  name: string;
  template_id: string;
  app_id: number;
  status: ServerStatus;
  variables: Record<string, string>;
  anonymous_login: boolean;
  update_on_start: boolean;
  max_backups: number;
  /** Steam beta branch for installs/updates; null = public branch. */
  steam_branch: string | null;
  /** Non-null when the game supports Steam Workshop (drives the Workshop tab). */
  workshop_app_id: number | null;
  workshop_auto_update: string;
  error_message: string | null;
  ports: Port[];
  created_at: string;
  progress: Progress | null;
}

export type WorkshopModStatus =
  | "queued"
  | "downloading"
  | "installing"
  | "installed"
  | "update_available"
  | "error"
  | "missing_dependency";

/** Statuses where the row is actively changing — drives polling. */
export const WORKSHOP_INFLIGHT: WorkshopModStatus[] = [
  "queued",
  "downloading",
  "installing",
];

export interface WorkshopMod {
  id: string;
  server_id: string;
  provider: string;
  item_id: string;
  name: string | null;
  status: WorkshopModStatus;
  size: number;
  error_message: string | null;
  title: string | null;
  author_id: string | null;
  author_name: string | null;
  preview_url: string | null;
  subscribers: number;
  favorites: number;
  file_size: number;
  time_updated_remote: string | null;
  installed_time_updated: string | null;
  is_dependency: boolean;
  required_by: string | null;
  created_at: string;
}

export interface WorkshopDependency {
  item_id: string;
  title: string | null;
}

export interface ModSummary {
  item_id: string;
  title: string | null;
  author_id: string | null;
  author_name: string | null;
  preview_url: string | null;
  subscribers: number;
  favorites: number;
  file_size: number;
  time_updated: string | null;
  time_created: string | null;
}

export interface ModDetails extends ModSummary {
  description: string | null;
  images: string[];
  dependencies: WorkshopDependency[];
}

export interface SearchResult {
  items: ModSummary[];
  total: number;
  page: number;
}

export interface ImportPreviewItem {
  item_id: string;
  title: string | null;
  preview_url: string | null;
  file_size: number;
  installed: boolean;
  duplicate: boolean;
  missing: boolean;
}

export interface ImportPreview {
  items: ImportPreviewItem[];
  unparsed: string[];
}

export interface ImportResult {
  queued: WorkshopMod[];
  skipped: string[];
}

export type AutoUpdateMode = "disabled" | "daily" | "weekly" | "startup";

export interface SyncResult {
  restored: number;
  missing: number;
  on_disk: number;
}

export interface TemplatePort {
  name: string;
  protocol: string;
  default: number;
}

export interface TemplateVar {
  key: string;
  default: string;
}

export interface Template {
  id: string;
  name: string;
  app_id: number;
  anonymous_login: boolean;
  supported: boolean;
  unsupported_reason: string | null;
  workshop_supported: boolean;
  ports: TemplatePort[];
  variables: TemplateVar[];
  update_on_start: boolean;
  /** Suggested Steam beta branches (e.g. "legacy41"). */
  branches: string[];
  /** How downloaded Workshop mods get enabled for this game. */
  workshop_note: string | null;
}

export interface SteamCredentials {
  username: string;
  password: string;
  guard_code?: string;
}

export interface Snapshot {
  id: string;
  created_at: string;
  size: number;
}

export type ScheduleActionType = "start" | "stop" | "restart" | "update" | "backup";

export interface ScheduledAction {
  id: string;
  server_id: string;
  action: ScheduleActionType;
  cron: string;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  created_at: string;
  server_name: string | null;
}

export type NotificationLevel = "info" | "success" | "warning" | "error";

export interface Notification {
  id: string;
  level: NotificationLevel;
  title: string;
  message: string | null;
  server_id: string | null;
  server_name: string | null;
  read: boolean;
  created_at: string;
}

export type BackupStatus = "idle" | "creating" | "done" | "error";

export interface BackupJob {
  status: BackupStatus;
  id: string | null;
  size: number;
  error: string | null;
}

export interface Stats {
  running: boolean;
  cpu_pct: number;
  mem_used: number;
  mem_limit: number;
  mem_pct: number;
  net_rx: number;
  net_tx: number;
  blk_read: number;
  blk_write: number;
  pids: number;
  online_cpus: number;
}

export type IntegrationStatus = "not_connected" | "pending" | "connected" | "error";

export interface Integration {
  /** null until a connection row exists for this provider. */
  id: string | null;
  provider: string;
  name: string;
  description: string;
  icon: string;
  capabilities: string[];
  status: IntegrationStatus;
  account_label: string | null;
  last_sync_at: string | null;
  error_message: string | null;
  tunnel_count: number;
}

export interface ConnectStart {
  integration_id: string;
  claim_url: string | null;
  expires_at: string | null;
}

export interface ConnectStatus {
  integration_id: string;
  status: IntegrationStatus;
  account_label: string | null;
  error_message: string | null;
}

export type TunnelStatus = "pending" | "active" | "error" | "disabled";

export interface IntegrationTunnel {
  id: string;
  integration_id: string;
  server_id: string | null;
  name: string;
  remote_domain: string | null;
  local_port: number;
  protocol: string;
  status: TunnelStatus;
  error_message: string | null;
  created_at: string;
}
