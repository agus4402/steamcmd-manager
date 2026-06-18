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
  ports: TemplatePort[];
  variables: TemplateVar[];
  update_on_start: boolean;
}

export interface SteamCredentials {
  username: string;
  password: string;
  guard_code?: string;
}
