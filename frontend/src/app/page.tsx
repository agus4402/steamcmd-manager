"use client";

import Link from "next/link";
import useSWR from "swr";
import { Plus, Server as ServerIcon, CircleCheck, CirclePause, CircleAlert, Cpu } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Server } from "@/lib/types";
import { useServerActions } from "@/lib/useServerActions";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState, ComingSoon } from "@/components/common/states";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import StatCard from "@/components/servers/StatCard";
import ServerTable from "@/components/servers/ServerTable";
import AlertList from "@/components/servers/AlertList";
import FleetUsage from "@/components/servers/FleetUsage";

export default function Dashboard() {
  const { data: servers, error: swrError, isLoading, mutate } = useSWR<Server[]>(
    "servers",
    () => api.servers(),
    { refreshInterval: 3000 },
  );
  const { act, remove, pending } = useServerActions(() => mutate());

  const list = servers ?? [];
  const running = list.filter((s) => s.status === "running").length;
  const stopped = list.filter((s) => s.status === "stopped").length;
  const errored = list.filter((s) => s.status === "errored").length;

  const newButton = (
    <Link href="/new" className={buttonVariants()}>
      <Plus className="size-4" /> New server
    </Link>
  );

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Dashboard" description="Fleet overview and quick actions" actions={newButton} />

      {/* KPI row */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total servers" value={isLoading ? "—" : list.length} icon={ServerIcon} tone="info" />
        <StatCard label="Running" value={isLoading ? "—" : running} icon={CircleCheck} tone="success" />
        <StatCard label="Stopped" value={isLoading ? "—" : stopped} icon={CirclePause} />
        <StatCard
          label="Alerts"
          value={isLoading ? "—" : errored}
          icon={CircleAlert}
          tone={errored ? "danger" : "default"}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Servers */}
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Servers</h2>
            <Link href="/servers" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              View all
            </Link>
          </div>

          {swrError ? (
            <ErrorState
              message={swrError instanceof ApiError ? swrError.message : "Backend unreachable"}
              onRetry={() => mutate()}
            />
          ) : isLoading ? (
            <div className="flex flex-col gap-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <EmptyState
              icon={ServerIcon}
              title="No servers yet"
              hint="Create your first game server to get started."
              action={newButton}
            />
          ) : (
            <ServerTable servers={list} pending={pending} onAct={act} onDelete={remove} />
          )}
        </div>

        {/* Side column: alerts + resource totals + activity */}
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Alerts</h2>
            <AlertList servers={list} />
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Cpu className="size-4 text-muted-foreground" /> Resource usage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <FleetUsage servers={list} />
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Recent activity
            </h2>
            <ComingSoon
              title="Activity feed"
              description="A timeline of installs, restarts and lifecycle events."
              backend="Persist an events/audit-log table and expose /api/events."
            />
          </div>
        </div>
      </div>
    </div>
  );
}
