"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import {
  Search,
  Users,
  Clock,
  Download,
  Check,
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  List,
  Rows3,
  type LucideIcon,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ModSummary } from "@/lib/types";
import { cn, formatCount, timeAgo } from "@/lib/utils";
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

type View = "grid" | "list" | "compact";
const VIEWS: { value: View; label: string; icon: LucideIcon }[] = [
  { value: "grid", label: "Cards", icon: LayoutGrid },
  { value: "list", label: "List", icon: List },
  { value: "compact", label: "Compact", icon: Rows3 },
];
const VIEW_KEY = "steamcmd_ws_browse_view";

interface Props {
  gameId: number;
  installedIds: Set<string>;
  busyId: string | null;
  onOpenItem: (itemId: string) => void;
  onInstall: (itemId: string) => void;
  /** Search to run on mount (e.g. a missing dependency from Load order). */
  initialQuery?: string;
}

interface ItemProps {
  mod: ModSummary;
  installed: boolean;
  busy: boolean;
  onOpen: () => void;
  onInstall: () => void;
}

export function WorkshopBrowse({
  gameId,
  installedIds,
  busyId,
  onOpenItem,
  onInstall,
  initialQuery = "",
}: Props) {
  const [text, setText] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [view, setView] = useState<View>("grid");

  // Remembered per browser; read after mount (no localStorage while rendering on the server).
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_KEY);
      if (saved === "grid" || saved === "list" || saved === "compact") setView(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  function changeView(next: View) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }
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
        <div className="flex rounded-md border border-border p-0.5" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button
              key={v.value}
              onClick={() => changeView(v.value)}
              aria-pressed={view === v.value}
              aria-label={`${v.label} view`}
              title={`${v.label} view`}
              className={cn(
                "flex size-8 items-center justify-center rounded transition-colors",
                view === v.value
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <v.icon className="size-4" />
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <ErrorState
          message={
            error instanceof ApiError ? error.message : "Could not search the Workshop"
          }
        />
      ) : isLoading ? (
        <div className={view === "grid" ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3" : "flex flex-col gap-2"}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton
              key={i}
              className={cn("w-full", view === "grid" ? "h-56" : view === "list" ? "h-20" : "h-10")}
            />
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
          <div
            className={cn(
              view === "grid" && "grid gap-3 sm:grid-cols-2 lg:grid-cols-3",
              view === "list" && "flex flex-col gap-2",
              view === "compact" &&
                "flex flex-col divide-y divide-border rounded-lg border border-border",
            )}
          >
            {items.map((m) => {
              const Item =
                view === "grid" ? BrowseCard : view === "list" ? BrowseRow : BrowseCompactRow;
              return (
                <Item
                  key={m.item_id}
                  mod={m}
                  installed={installedIds.has(m.item_id)}
                  busy={busyId === m.item_id}
                  onOpen={() => onOpenItem(m.item_id)}
                  onInstall={() => onInstall(m.item_id)}
                />
              );
            })}
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

function Thumb({ mod, className }: { mod: ModSummary; className: string }) {
  return mod.preview_url ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={mod.preview_url} alt="" loading="lazy" className={cn("object-cover", className)} />
  ) : (
    <div className={cn("flex items-center justify-center bg-muted", className)}>
      <Boxes className="size-4 text-muted-foreground" />
    </div>
  );
}

function Meta({ mod }: { mod: ModSummary }) {
  return (
    <>
      <span className="flex items-center gap-1" title="Subscribers">
        <Users className="size-3" /> {formatCount(mod.subscribers)}
      </span>
      {mod.time_updated && (
        <span className="flex items-center gap-1" title="Last updated">
          <Clock className="size-3" /> {timeAgo(mod.time_updated)}
        </span>
      )}
    </>
  );
}

/** List view: medium thumbnail, title, author and stats in one row. */
function BrowseRow({ mod, installed, busy, onOpen, onInstall }: ItemProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card/40 p-2 transition-colors hover:border-primary/40">
      <button onClick={onOpen} className="shrink-0" aria-label="Mod details">
        <Thumb mod={mod} className="aspect-video w-28 rounded-md border border-border" />
      </button>
      <div className="min-w-0 flex-1">
        <button onClick={onOpen} className="line-clamp-2 text-left text-sm font-medium hover:underline">
          {mod.title || `Item ${mod.item_id}`}
        </button>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {mod.author_name && <span className="truncate">by {mod.author_name}</span>}
          <Meta mod={mod} />
        </div>
      </div>
      {installed ? (
        <Button variant="secondary" size="sm" disabled className="shrink-0">
          <Check className="size-4" /> Installed
        </Button>
      ) : (
        <Button size="sm" disabled={busy} onClick={onInstall} className="shrink-0">
          <Download className="size-4" /> Install
        </Button>
      )}
    </div>
  );
}

/** Compact view: one dense line per item, to scan many results quickly. */
function BrowseCompactRow({ mod, installed, busy, onOpen, onInstall }: ItemProps) {
  return (
    <div className="flex items-center gap-3 px-2 py-1.5 transition-colors hover:bg-accent/50">
      <button onClick={onOpen} className="shrink-0" aria-label="Mod details">
        <Thumb mod={mod} className="size-8 rounded border border-border" />
      </button>
      <button onClick={onOpen} className="min-w-0 flex-1 truncate text-left text-sm hover:underline">
        {mod.title || `Item ${mod.item_id}`}
      </button>
      <div className="hidden shrink-0 items-center gap-3 text-xs text-muted-foreground sm:flex">
        <Meta mod={mod} />
      </div>
      {installed ? (
        <span className="flex size-9 shrink-0 items-center justify-center text-success" title="Installed">
          <Check className="size-4" />
          <span className="sr-only">Installed</span>
        </span>
      ) : (
        <Button
          size="icon"
          variant="secondary"
          disabled={busy}
          onClick={onInstall}
          aria-label={`Install ${mod.title ?? mod.item_id}`}
          title="Install"
          className="shrink-0"
        >
          <Download className="size-4" />
        </Button>
      )}
    </div>
  );
}

function BrowseCard({ mod, installed, busy, onOpen, onInstall }: ItemProps) {
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
