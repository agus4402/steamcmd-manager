import {
  CircleDot,
  CircleCheck,
  CirclePause,
  CircleAlert,
  Download,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import type { ServerStatus } from "@/lib/types";
import { Badge, type BadgeProps } from "@/components/ui/badge";

// Status conveyed by icon AND color (never color alone) for accessibility.
const MAP: Record<ServerStatus, { variant: BadgeProps["variant"]; icon: LucideIcon; label: string; spin?: boolean }> = {
  running: { variant: "success", icon: CircleCheck, label: "Running" },
  stopped: { variant: "default", icon: CirclePause, label: "Stopped" },
  installing: { variant: "warning", icon: Download, label: "Installing", spin: true },
  updating: { variant: "warning", icon: RefreshCw, label: "Updating", spin: true },
  errored: { variant: "danger", icon: CircleAlert, label: "Errored" },
  created: { variant: "info", icon: CircleDot, label: "Created" },
};

export default function StatusBadge({ status }: { status: ServerStatus }) {
  const { variant, icon: Icon, label, spin } = MAP[status] ?? MAP.created;
  return (
    <Badge variant={variant}>
      <Icon className={`size-3 ${spin ? "animate-spin" : ""}`} />
      {label}
    </Badge>
  );
}
