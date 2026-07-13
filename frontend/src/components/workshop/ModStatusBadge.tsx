import {
  Loader2,
  CircleCheck,
  CircleAlert,
  Download,
  Clock,
  ArrowUpCircle,
  Unplug,
} from "lucide-react";
import type { WorkshopModStatus } from "@/lib/types";

const MAP: Record<
  WorkshopModStatus,
  { label: string; cls: string; icon: typeof Loader2; spin?: boolean }
> = {
  queued: { label: "Queued", cls: "text-muted-foreground", icon: Clock },
  downloading: { label: "Downloading…", cls: "text-warning", icon: Download, spin: true },
  installing: { label: "Installing…", cls: "text-warning", icon: Loader2, spin: true },
  installed: { label: "Installed", cls: "text-success", icon: CircleCheck },
  update_available: { label: "Update available", cls: "text-info", icon: ArrowUpCircle },
  error: { label: "Failed", cls: "text-danger", icon: CircleAlert },
  missing_dependency: { label: "Missing dependency", cls: "text-danger", icon: Unplug },
};

export function ModStatusBadge({
  status,
  title,
}: {
  status: WorkshopModStatus;
  title?: string;
}) {
  const m = MAP[status] ?? MAP.queued;
  const Icon = m.icon;
  return (
    <span className={`flex items-center gap-1.5 text-xs ${m.cls}`} title={title}>
      <Icon className={`size-3.5 ${m.spin ? "animate-spin" : ""}`} /> {m.label}
    </span>
  );
}
