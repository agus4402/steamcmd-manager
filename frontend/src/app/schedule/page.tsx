"use client";

import Link from "next/link";
import useSWR from "swr";
import { Clock, CircleCheck, CircleAlert } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ScheduledAction } from "@/lib/types";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function SchedulePage() {
  const { data, error, isLoading } = useSWR<ScheduledAction[]>("all-schedules", () =>
    api.allSchedules(),
  );
  const list = data ?? [];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Schedule" description="Automated tasks across all servers" />

      {error ? (
        <ErrorState message={error instanceof ApiError ? error.message : "Could not load schedule"} />
      ) : isLoading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="No scheduled tasks"
          hint="Add scheduled restarts, updates or backups from a server's Schedule tab."
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Server</th>
                <th className="px-4 py-2.5 font-medium">Task</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Last run</th>
                <th className="px-4 py-2.5 text-right font-medium">State</th>
              </tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className="border-b border-border last:border-0 transition-colors hover:bg-card/60">
                  <td className="px-4 py-3">
                    <Link
                      href={`/servers/${a.server_id}/schedule`}
                      className="font-medium transition-colors hover:text-primary"
                    >
                      {a.server_name ?? a.server_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium capitalize">{a.action}</div>
                    <div className="font-mono text-xs text-muted-foreground">{a.cron}</div>
                  </td>
                  <td className="hidden px-4 py-3 md:table-cell">
                    {a.last_run_at ? (
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        {a.last_status === "error" ? (
                          <CircleAlert className="size-3.5 text-danger" />
                        ) : (
                          <CircleCheck className="size-3.5 text-success" />
                        )}
                        <span title={a.last_error ?? undefined}>{new Date(a.last_run_at).toLocaleString()}</span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">never</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Badge variant={a.enabled ? "success" : "outline"}>
                      {a.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
