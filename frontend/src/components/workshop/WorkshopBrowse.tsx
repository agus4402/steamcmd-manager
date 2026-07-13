"use client";

import { useState } from "react";
import useSWR from "swr";
import { Search, Users, Clock, Download, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ModSummary } from "@/lib/types";
import { formatCount, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Boxes } from "lucide-react";

const SORTS = [
  { value: "popular", label: "Most Popular" },
  { value: "subscribed", label: "Most Subscribed" },
  { value: "trending", label: "Trending" },
  { value: "updated", label: "Recently Updated" },
  { value: "newest", label: "Newest" },
];
const PAGE_SIZE = 30;

interface Props {
  gameId: number;
  installedIds: Set<string>;
  busyId: string | null;
  onOpenItem: (itemId: string) => void;
  onInstall: (itemId: string) => void;
}

export function WorkshopBrowse({ gameId, installedIds, busyId, onOpenItem, onInstall }: Props) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("popular");
  const [page, setPage] = useState(1);

  const { data, error, isLoading } = useSWR(
    ["ws-search", gameId, query, sort, page],
    () => api.searchWorkshop({ gameId, query, sortBy: sort, page, pageSize: PAGE_SIZE }),
    { keepPreviousData: true },
  );

  function submit() {
    setPage(1);
    setQuery(text.trim());
  }

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Search the Workshop…"
            className="pl-8"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
          className="h-9 rounded-md border border-border bg-background px-2 text-sm outline-none focus:border-primary"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <Button onClick={submit}>Search</Button>
      </div>

      {error ? (
        <ErrorState
          message={
            error instanceof ApiError ? error.message : "Could not search the Workshop"
          }
        />
      ) : isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No results"
          hint="Try a different search term or sort order."
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((m) => (
              <BrowseCard
                key={m.item_id}
                mod={m}
                installed={installedIds.has(m.item_id)}
                busy={busyId === m.item_id}
                onOpen={() => onOpenItem(m.item_id)}
                onInstall={() => onInstall(m.item_id)}
              />
            ))}
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="size-4" /> Prev
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function BrowseCard({
  mod,
  installed,
  busy,
  onOpen,
  onInstall,
}: {
  mod: ModSummary;
  installed: boolean;
  busy: boolean;
  onOpen: () => void;
  onInstall: () => void;
}) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-card/40 transition-colors hover:border-primary/40">
      <button onClick={onOpen} className="aspect-video w-full bg-muted" aria-label="Mod details">
        {mod.preview_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={mod.preview_url} alt="" className="size-full object-cover" />
        ) : (
          <div className="flex size-full items-center justify-center">
            <Boxes className="size-8 text-muted-foreground" />
          </div>
        )}
      </button>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <button onClick={onOpen} className="line-clamp-2 text-left text-sm font-medium hover:underline">
          {mod.title || `Item ${mod.item_id}`}
        </button>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Users className="size-3" /> {formatCount(mod.subscribers)}
          </span>
          {mod.time_updated && (
            <span className="flex items-center gap-1">
              <Clock className="size-3" /> {timeAgo(mod.time_updated)}
            </span>
          )}
        </div>
        <div className="mt-auto pt-1">
          {installed ? (
            <Button variant="secondary" size="sm" disabled className="w-full">
              <Check className="size-4" /> Installed
            </Button>
          ) : (
            <Button size="sm" disabled={busy} onClick={onInstall} className="w-full">
              <Download className="size-4" /> Install
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
