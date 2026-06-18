"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Plus, Search, Server as ServerIcon } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Server, ServerStatus } from "@/lib/types";
import { useServerActions } from "@/lib/useServerActions";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import ServerTable from "@/components/servers/ServerTable";

const FILTERS: { value: "all" | ServerStatus; label: string }[] = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "stopped", label: "Stopped" },
  { value: "errored", label: "Errored" },
];

export default function ServersPage() {
  const { data: servers, error: swrError, isLoading, mutate } = useSWR<Server[]>(
    "servers",
    () => api.servers(),
    { refreshInterval: 3000 },
  );
  const { act, remove, pending } = useServerActions(() => mutate());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | ServerStatus>("all");

  const list = servers ?? [];
  const filtered = list.filter((s) => {
    const matchesQuery = `${s.name} ${s.template_id}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = filter === "all" || s.status === filter;
    return matchesQuery && matchesStatus;
  });

  const newButton = (
    <Link href="/new" className={buttonVariants()}>
      <Plus className="size-4" /> New server
    </Link>
  );

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Servers" description="All your game servers" actions={newButton} />

      {/* Toolbar */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search servers…"
            className="pl-9"
            aria-label="Search servers"
          />
        </div>
        <div className="flex items-center gap-1 rounded-md border border-border bg-card p-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`cursor-pointer rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                filter === f.value ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {swrError ? (
        <ErrorState
          message={swrError instanceof ApiError ? swrError.message : "Backend unreachable"}
          onRetry={() => mutate()}
        />
      ) : isLoading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
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
      ) : filtered.length === 0 ? (
        <EmptyState icon={Search} title="No matches" hint="Try a different search or filter." />
      ) : (
        <ServerTable servers={filtered} pending={pending} onAct={act} onDelete={remove} />
      )}
    </div>
  );
}
