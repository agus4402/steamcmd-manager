import { Globe, Plug, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { IntegrationStatus, TunnelStatus } from "@/lib/types";

/** Map a provider's icon key (from the backend catalog) to a lucide icon. */
const ICONS: Record<string, LucideIcon> = {
  globe: Globe,
  plug: Plug,
};

export function providerIcon(key: string): LucideIcon {
  return ICONS[key] ?? Plug;
}

const INTEGRATION_BADGE: Record<
  IntegrationStatus,
  { label: string; variant: "default" | "success" | "warning" | "danger" | "info" }
> = {
  not_connected: { label: "Not connected", variant: "default" },
  pending: { label: "Connecting…", variant: "warning" },
  connected: { label: "Connected", variant: "success" },
  error: { label: "Error", variant: "danger" },
};

export function IntegrationStatusBadge({ status }: { status: IntegrationStatus }) {
  const s = INTEGRATION_BADGE[status] ?? INTEGRATION_BADGE.not_connected;
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

const TUNNEL_BADGE: Record<
  TunnelStatus,
  { label: string; variant: "default" | "success" | "warning" | "danger" | "info" }
> = {
  pending: { label: "Provisioning…", variant: "warning" },
  active: { label: "Active", variant: "success" },
  error: { label: "Error", variant: "danger" },
  disabled: { label: "Disabled", variant: "default" },
};

export function TunnelStatusBadge({ status }: { status: TunnelStatus }) {
  const s = TUNNEL_BADGE[status] ?? TUNNEL_BADGE.pending;
  return <Badge variant={s.variant}>{s.label}</Badge>;
}
