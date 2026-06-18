"use client";

import useSWR from "swr";
import { Activity } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FullHealth {
  status?: string;
  db?: boolean;
  agent?: boolean;
  [k: string]: unknown;
}

/** Compact backend-health indicator polled from /api/health/full. */
export default function HealthBadge() {
  const { data, error } = useSWR<FullHealth>("health", () => api.health(), {
    refreshInterval: 15000,
    shouldRetryOnError: false,
  });

  const healthy = !error && data && data.db !== false && data.agent !== false;
  const label = error ? "Offline" : !data ? "Checking" : healthy ? "Healthy" : "Degraded";
  const color = error ? "bg-danger" : !data ? "bg-muted-foreground" : healthy ? "bg-success" : "bg-warning";

  return (
    <span
      className="hidden items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground sm:flex"
      title={`Backend: ${label}`}
    >
      <Activity className="size-3.5" />
      <span className="relative flex size-2">
        <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-60", color, healthy && "animate-ping")} />
        <span className={cn("relative inline-flex size-2 rounded-full", color)} />
      </span>
      {label}
    </span>
  );
}
