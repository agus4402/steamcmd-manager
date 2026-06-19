"use client";

import { Cpu, MemoryStick, ArrowDownUp, HardDrive, Boxes, Activity } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import StatCard from "@/components/servers/StatCard";
import MetricChart from "@/components/servers/MetricChart";
import { useServerStats } from "@/lib/useServerStats";
import { formatBytes } from "@/lib/utils";
import { useServerCtx } from "../server-context";

const RUNNING = new Set(["running"]);

export default function ServerMetricsPage() {
  const { server } = useServerCtx();
  const enabled = RUNNING.has(server.status);
  const { stats, history, error, isLoading } = useServerStats(server.id, enabled);

  if (!enabled) {
    return (
      <EmptyState
        icon={Activity}
        title="Server not running"
        hint="Start the server to see live CPU, memory, network and disk metrics."
      />
    );
  }

  if (error) {
    return <ErrorState message="Could not load metrics from the agent." />;
  }

  if (isLoading && !stats) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Current readouts */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="CPU"
          value={`${(stats?.cpu_pct ?? 0).toFixed(1)}%`}
          icon={Cpu}
          tone="info"
          hint={`${stats?.online_cpus ?? 0} cores`}
        />
        <StatCard
          label="Memory"
          value={`${(stats?.mem_pct ?? 0).toFixed(1)}%`}
          icon={MemoryStick}
          tone="success"
          hint={`${formatBytes(stats?.mem_used ?? 0)} / ${formatBytes(stats?.mem_limit ?? 0)}`}
        />
        <StatCard
          label="Network"
          value={formatBytes(stats?.net_rx ?? 0)}
          icon={ArrowDownUp}
          hint={`↓ in · ↑ ${formatBytes(stats?.net_tx ?? 0)} out`}
        />
        <StatCard
          label="Processes"
          value={stats?.pids ?? 0}
          icon={Boxes}
          hint={`disk ${formatBytes((stats?.blk_read ?? 0) + (stats?.blk_write ?? 0))}`}
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Cpu className="size-4 text-info" /> CPU usage
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-2">
            <MetricChart data={history} dataKey="cpu" color="#0ea5e9" max={100} format={(v) => `${v.toFixed(0)}%`} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <MemoryStick className="size-4 text-success" /> Memory usage
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-2">
            <MetricChart data={history} dataKey="memPct" color="#22c55e" max={100} format={(v) => `${v.toFixed(0)}%`} />
          </CardContent>
        </Card>
      </div>

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <HardDrive className="size-3.5" /> Live snapshots polled every few seconds; history is kept in your browser
        for this session.
      </p>
    </div>
  );
}
