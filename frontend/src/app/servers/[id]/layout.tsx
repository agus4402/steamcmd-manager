"use client";

import * as React from "react";
import { use } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import useSWR from "swr";
import { Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Progress, Server } from "@/lib/types";
import { useServerActions } from "@/lib/useServerActions";
import { SERVER_NAV } from "@/lib/nav";
import { ServerCtx } from "./server-context";
import StatusBadge from "@/components/StatusBadge";
import ProgressBar from "@/components/ProgressBar";
import ServerActions from "@/components/servers/ServerActions";
import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const BUSY = new Set(["installing", "updating"]);

export default function ServerLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const pathname = usePathname();
  const router = useRouter();
  const { data: server, error, isLoading, mutate } = useSWR<Server>(
    ["server", id],
    () => api.server(id),
    { refreshInterval: 3000 },
  );
  const { act, remove, pending } = useServerActions(() => mutate());
  const [liveProgress, setLiveProgress] = React.useState<Progress | null>(null);

  // Drop stale live progress once the install/update finishes.
  React.useEffect(() => {
    if (server && !BUSY.has(server.status)) setLiveProgress(null);
  }, [server]);

  const base = `/servers/${id}`;

  async function onDelete() {
    const ok = await remove({ id, name: server?.name } as Server);
    if (ok) router.push("/servers");
  }

  if (error) {
    return (
      <div className="mx-auto max-w-5xl">
        <ErrorState
          message={error instanceof ApiError ? error.message : "Server unreachable"}
          onRetry={() => mutate()}
        />
      </div>
    );
  }

  if (isLoading || !server) {
    return (
      <div className="mx-auto max-w-5xl">
        <Skeleton className="mb-4 h-9 w-64" />
        <Skeleton className="mb-6 h-10 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const installing = BUSY.has(server.status);

  return (
    <ServerCtx.Provider value={{ server, mutate, liveProgress, setLiveProgress, pending, act, del: onDelete }}>
      <div className="mx-auto max-w-5xl">
        {/* Header */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{server.name}</h1>
            <StatusBadge status={server.status} />
          </div>
          <div className="flex items-center gap-2">
            {!installing && <ServerActions server={server} pendingAction={pending[server.id]} onAct={act} />}
            <Button variant="danger" size="sm" onClick={onDelete} disabled={!!pending[server.id]}>
              <Trash2 className="size-4" /> Delete
            </Button>
          </div>
        </div>

        {installing && (
          <div className="mb-5">
            <ProgressBar
              progress={liveProgress ?? server.progress}
              label={server.status === "updating" ? "Updating" : "Installing"}
            />
          </div>
        )}

        {/* Sub-navigation — the Workshop tab only shows for workshop-capable games. */}
        <div className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
          {SERVER_NAV.filter(
            (item) => item.segment !== "workshop" || server.workshop_app_id != null,
          ).map((item) => {
            const href = item.segment ? `${base}/${item.segment}` : base;
            const active = item.segment
              ? pathname === href || pathname.startsWith(`${href}/`)
              : pathname === base;
            return (
              <Link
                key={item.segment || "overview"}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
                {item.soon && (
                  <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] font-semibold uppercase text-muted-foreground">
                    soon
                  </span>
                )}
              </Link>
            );
          })}
        </div>

        {children}
      </div>
    </ServerCtx.Provider>
  );
}
