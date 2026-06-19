"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { Server, Stats } from "@/lib/types";
import { formatBytes } from "@/lib/utils";

/**
 * Aggregate CPU/memory across all running servers, polled on a slow interval
 * (one stats call per running server). Falls back gracefully if some fail.
 */
export default function FleetUsage({ servers }: { servers: Server[] }) {
  const runningIds = servers.filter((s) => s.status === "running").map((s) => s.id);

  const { data, isLoading } = useSWR(
    runningIds.length ? ["fleet-stats", runningIds.join(",")] : null,
    async () => {
      const results = await Promise.allSettled(runningIds.map((id) => api.stats(id)));
      return results
        .filter((r): r is PromiseFulfilledResult<Stats> => r.status === "fulfilled")
        .map((r) => r.value)
        .filter((s) => s.running);
    },
    { refreshInterval: 5000, shouldRetryOnError: false },
  );

  if (runningIds.length === 0) {
    return <p className="text-sm text-muted-foreground">No running servers to measure.</p>;
  }

  if (isLoading && !data) {
    return <p className="text-sm text-muted-foreground">Collecting usage…</p>;
  }

  const stats = data ?? [];
  const cpuTotal = stats.reduce((a, s) => a + s.cpu_pct, 0);
  const memUsed = stats.reduce((a, s) => a + s.mem_used, 0);
  const memLimit = stats.reduce((a, s) => a + s.mem_limit, 0);
  const memPct = memLimit ? (memUsed / memLimit) * 100 : 0;

  return (
    <div className="flex flex-col gap-4">
      <Row label={`CPU · ${stats.length} running`} value={`${cpuTotal.toFixed(0)}%`} pct={cpuTotal} color="bg-info" />
      <Row
        label={`Memory · ${formatBytes(memUsed)} / ${formatBytes(memLimit)}`}
        value={`${memPct.toFixed(0)}%`}
        pct={memPct}
        color="bg-success"
      />
    </div>
  );
}

function Row({ label, value, pct, color }: { label: string; value: string; pct: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
        <span className="truncate">{label}</span>
        <span className="font-mono">{value}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}
