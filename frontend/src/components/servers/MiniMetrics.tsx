"use client";

import Link from "next/link";
import { Cpu, MemoryStick, Boxes } from "lucide-react";
import { useServerStats } from "@/lib/useServerStats";
import { formatBytes, cn } from "@/lib/utils";

/** Compact live CPU/memory/process readout for the server overview. */
export default function MiniMetrics({
  serverId,
  running,
  href,
}: {
  serverId: string;
  running: boolean;
  href: string;
}) {
  const { stats } = useServerStats(serverId, running, 3000);

  if (!running) {
    return (
      <p className="text-sm text-muted-foreground">Start the server to see live CPU and memory usage.</p>
    );
  }

  const cpu = stats?.cpu_pct ?? 0;
  const memPct = stats?.mem_pct ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3 text-center">
        <Tile icon={<Cpu className="size-4 text-info" />} label="CPU" value={`${cpu.toFixed(0)}%`} />
        <Tile
          icon={<MemoryStick className="size-4 text-success" />}
          label="Memory"
          value={`${memPct.toFixed(0)}%`}
        />
        <Tile icon={<Boxes className="size-4 text-muted-foreground" />} label="Procs" value={stats?.pids ?? 0} />
      </div>

      <Bar label="CPU" pct={cpu} color="bg-info" />
      <Bar
        label={`Memory · ${formatBytes(stats?.mem_used ?? 0)} / ${formatBytes(stats?.mem_limit ?? 0)}`}
        pct={memPct}
        color="bg-success"
      />

      <Link href={href} className="text-center text-sm text-muted-foreground transition-colors hover:text-foreground">
        View full metrics →
      </Link>
    </div>
  );
}

function Tile({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-card/50 p-3">
      <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Bar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-all duration-500", color)}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}
