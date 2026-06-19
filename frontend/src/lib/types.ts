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
  error_message: string | null;
  ports: Port[];
  created_at: string;
  progress: Progress | null;
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
  ports: TemplatePort[];
  variables: TemplateVar[];
  update_on_start: boolean;
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
