"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import {
  Boxes,
  Plus,
  Trash2,
  Users,
  Clock,
  RotateCw,
  RefreshCw,
  ArrowUpCircle,
  FolderSync,
  Info,
  Search,
  X,
  CalendarPlus,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  WORKSHOP_INFLIGHT,
  type LoadOrder,
  type LoadOrderEntry,
  type Template,
  type WorkshopMod,
} from "@/lib/types";
import { formatCount, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { ModStatusBadge } from "@/components/workshop/ModStatusBadge";
import { ModDetailsDrawer } from "@/components/workshop/ModDetailsDrawer";
import { ImportModsModal } from "@/components/workshop/ImportModsModal";
import { WorkshopBrowse } from "@/components/workshop/WorkshopBrowse";
import { LoadOrderList } from "@/components/workshop/LoadOrderList";
import { cn } from "@/lib/utils";
import { useServerCtx } from "../server-context";

type InstalledSort = "recent" | "oldest" | "name";
const SORTS: { value: InstalledSort; label: string }[] = [
  { value: "recent", label: "Recently added" },
  { value: "oldest", label: "Oldest first" },
  { value: "name", label: "Name (A–Z)" },
];
const SORT_KEY = "steamcmd_ws_installed_sort";

const modName = (m: WorkshopMod) => m.name || m.title || m.item_id;

/** Order added = created_at (every add is its own row/commit); name breaks ties
 * (mods restored together by Sync share one timestamp). */
function sortMods(mods: WorkshopMod[], sort: InstalledSort): WorkshopMod[] {
  const byName = (a: WorkshopMod, b: WorkshopMod) =>
    modName(a).localeCompare(modName(b), undefined, { sensitivity: "base" });
  const added = (m: WorkshopMod) => new Date(m.created_at).getTime();
  return [...mods].sort((a, b) => {
    if (sort === "name") return byName(a, b);
    const diff = sort === "recent" ? added(b) - added(a) : added(a) - added(b);
    return diff || byName(a, b);
  });
}

export default function ServerWorkshopPage() {
  const { server, mutate: mutateServer } = useServerCtx();
  const { data, error, isLoading, mutate } = useSWR<WorkshopMod[]>(
    ["mods", server.id],
    () => api.mods(server.id),
    {
      refreshInterval: (d) =>
        d?.some((m) => WORKSHOP_INFLIGHT.includes(m.status)) ? 2500 : 0,
    },
  );

  const { data: templates } = useSWR<Template[]>("templates", () => api.templates());
  const template = templates?.find((t) => t.id === server.template_id);
  const workshopNote = template?.workshop_note;
  const sandboxPath = template?.config_files.find((f) => f.format === "pz_sandbox")?.path ?? null;

  // Mods inside each item (toggles + load order); refreshed whenever the item
  // list settles, since a finished download adds its mods.
  const { data: loadOrder, mutate: mutateLoadOrder } = useSWR<LoadOrder>(
    ["load-order", server.id],
    () => api.loadOrder(server.id),
    { revalidateOnFocus: false },
  );
  const modsSignature = (data ?? []).map((m) => `${m.id}:${m.status}`).join(",");
  useEffect(() => {
    void mutateLoadOrder();
  }, [modsSignature, mutateLoadOrder]);

  const [tab, setTab] = useState<"installed" | "order" | "browse">("installed");
  // A Browse search requested from elsewhere (missing dependency); the key
  // remounts Browse so it runs even when the same text is requested again.
  const [browseSearch, setBrowseSearch] = useState({ query: "", key: 0 });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [detailItemId, setDetailItemId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const [bulkBusy, setBulkBusy] = useState(false);
  // Filters both the Installed grid and the Load order list.
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<InstalledSort>("recent");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SORT_KEY);
      if (saved && SORTS.some((s) => s.value === saved)) setSort(saved as InstalledSort);
    } catch {
      /* storage unavailable */
    }
  }, []);

  function changeSort(next: InstalledSort) {
    setSort(next);
    try {
      window.localStorage.setItem(SORT_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }

  function searchInBrowse(text: string) {
    setBrowseSearch((s) => ({ query: text, key: s.key + 1 }));
    setTab("browse");
  }

  const mods = data ?? [];
  const q = query.trim().toLowerCase();
  const filteredMods = sortMods(
    q
      ? mods.filter((m) =>
          [m.name, m.title, m.item_id].some((v) => v?.toLowerCase().includes(q)),
        )
      : mods,
    sort,
  );
  const detailMod = mods.find((m) => m.item_id === detailItemId) ?? null;
  const installedIds = new Set(mods.map((m) => m.item_id));
  const updatesAvailable = mods.filter((m) => m.status === "update_available").length;

  async function checkUpdates() {
    setBulkBusy(true);
    try {
      const next = await api.checkModUpdates(server.id);
      const count = next.filter((m) => m.status === "update_available").length;
      toast.success(count ? `${count} update(s) available` : "All mods are up to date");
      await mutate(next, { revalidate: false });
    } catch (e) {
      toast.error("Update check failed", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBulkBusy(false);
    }
  }

  async function updateAll() {
    setBulkBusy(true);
    try {
      const queued = await api.updateAllMods(server.id);
      toast.success(`Updating ${queued.length} mod(s)`);
      await mutate();
    } catch (e) {
      toast.error("Update all failed", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBulkBusy(false);
    }
  }

  async function sync() {
    setBulkBusy(true);
    try {
      const res = await api.syncMods(server.id);
      toast.success(
        `Sync complete — ${res.restored} restored, ${res.missing} missing of ${res.on_disk} on disk`,
      );
      await mutate();
    } catch (e) {
      toast.error("Sync failed", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBulkBusy(false);
    }
  }

  async function setAutoUpdate(mode: string) {
    try {
      await api.setWorkshopAutoUpdate(server.id, mode as never);
      toast.success("Auto-update updated");
      await mutateServer();
    } catch (e) {
      toast.error("Could not change auto-update", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    }
  }

  async function toggleSubmod(entry: LoadOrderEntry, enabled: boolean) {
    try {
      await api.toggleSubmod(server.id, entry.id, enabled);
      await mutateLoadOrder();
    } catch (e) {
      toast.error("Could not change the mod", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    }
  }

  async function install(itemId: string) {
    setBusyId(itemId);
    try {
      await api.addMod(server.id, itemId);
      toast.success("Mod queued for download");
      await mutate();
    } catch (e) {
      toast.error("Could not install mod", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  async function retry(mod: WorkshopMod) {
    setBusyId(mod.id);
    try {
      await api.retryMod(server.id, mod.id);
      toast.success("Retrying download");
      await mutate();
    } catch (e) {
      toast.error("Could not retry", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  async function update(mod: WorkshopMod) {
    setBusyId(mod.id);
    try {
      await api.updateMod(server.id, mod.id);
      toast.success("Update queued");
      await mutate();
    } catch (e) {
      toast.error("Could not update", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(mod: WorkshopMod) {
    if (!confirm("Remove this mod? Its files will be deleted from the server.")) return;
    setBusyId(mod.id);
    try {
      await api.removeMod(server.id, mod.id);
      toast.success("Mod removed");
      setDetailItemId(null);
      await mutate();
    } catch (e) {
      toast.error("Could not remove mod", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {workshopNote && (
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          {workshopNote}
        </p>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-border">
        {(loadOrder?.supported
          ? (["installed", "order", "browse"] as const)
          : (["installed", "browse"] as const)
        ).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "border-b-2 px-4 py-2 text-sm font-medium capitalize transition-colors",
              tab === t
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t === "installed"
              ? `Installed${mods.length ? ` (${mods.length})` : ""}`
              : t === "order"
                ? "Load order"
                : "Browse"}
          </button>
        ))}
      </div>

      {tab !== "browse" && (
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setQuery("")}
              placeholder={tab === "order" ? "Search mods and maps…" : "Search installed mods…"}
              aria-label="Search mods"
              className="pl-9 pr-9"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
                aria-label="Clear search"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          {tab === "installed" && (
            <>
              <select
                value={sort}
                onChange={(e) => changeSort(e.target.value as InstalledSort)}
                aria-label="Sort installed mods"
                className="h-9 rounded-md border border-border bg-background px-2 text-sm outline-none focus:border-primary"
              >
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <Button
                size="icon"
                onClick={() => setImportOpen(true)}
                aria-label="Add mods"
                title="Add mods (item, collection or list of IDs)"
                className="size-9 shrink-0"
              >
                <Plus className="size-4" />
              </Button>
            </>
          )}
        </div>
      )}

      {tab === "order" && loadOrder?.supported ? (
        <LoadOrderList
          serverId={server.id}
          entries={loadOrder.entries}
          maps={loadOrder.maps}
          sandboxPath={sandboxPath}
          query={query}
          onSaved={() => mutateLoadOrder()}
          onOpenItem={setDetailItemId}
          onSearchMissing={searchInBrowse}
        />
      ) : tab === "browse" ? (
        <WorkshopBrowse
          key={browseSearch.key}
          initialQuery={browseSearch.query}
          gameId={server.workshop_app_id as number}
          installedIds={installedIds}
          busyId={busyId}
          onOpenItem={setDetailItemId}
          onInstall={install}
        />
      ) : (
        <>
      {/* Toolbar: updates, sync, auto-update */}
      {mods.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" disabled={bulkBusy} onClick={checkUpdates}>
            <RefreshCw className={cn("size-4", bulkBusy && "animate-spin")} /> Check updates
          </Button>
          {updatesAvailable > 0 && (
            <Button size="sm" disabled={bulkBusy} onClick={updateAll}>
              <ArrowUpCircle className="size-4" /> Update all ({updatesAvailable})
            </Button>
          )}
          <Button variant="secondary" size="sm" disabled={bulkBusy} onClick={sync}>
            <FolderSync className="size-4" /> Sync
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Auto-update</span>
            <select
              value={server.workshop_auto_update}
              onChange={(e) => setAutoUpdate(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2 text-sm outline-none focus:border-primary"
            >
              <option value="disabled">Disabled</option>
              <option value="15min">Every 15 min (restarts only on update)</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="startup">Every startup</option>
            </select>
          </div>
        </div>
      )}

      {/* Installed grid */}
      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load mods"}
          onRetry={() => mutate()}
        />
      ) : isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : mods.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No mods installed"
          hint="Use + to add a Workshop item, a collection or a list of IDs, or find mods in Browse."
          action={
            <Button size="sm" onClick={() => setImportOpen(true)}>
              <Plus className="size-4" /> Add mods
            </Button>
          }
        />
      ) : filteredMods.length === 0 ? (
        <EmptyState
          icon={Search}
          title={`No mods match “${query.trim()}”`}
          hint="Search looks at the mod name and Workshop item ID."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {filteredMods.map((m) => (
            <ModCard
              key={m.id}
              mod={m}
              busy={busyId === m.id}
              onOpen={() => setDetailItemId(m.item_id)}
              onRemove={() => remove(m)}
              onRetry={() => retry(m)}
            />
          ))}
        </div>
      )}
        </>
      )}

      <ModDetailsDrawer
        itemId={detailItemId}
        installedMod={detailMod}
        busy={busyId !== null}
        onClose={() => setDetailItemId(null)}
        onInstall={install}
        onUpdate={update}
        onRemove={remove}
        onOpenItem={setDetailItemId}
        submods={loadOrder?.entries.filter((e) => e.workshop_mod_id === detailMod?.id)}
        onToggleSubmod={loadOrder?.supported ? toggleSubmod : undefined}
      />

      {importOpen && (
        <ImportModsModal
          serverId={server.id}
          onClose={() => setImportOpen(false)}
          onInstalled={() => mutate()}
        />
      )}
    </div>
  );
}

function ModCard({
  mod,
  busy,
  onOpen,
  onRemove,
  onRetry,
}: {
  mod: WorkshopMod;
  busy: boolean;
  onOpen: () => void;
  onRemove: () => void;
  onRetry: () => void;
}) {
  const name = mod.name || mod.title || `Item ${mod.item_id}`;
  const failed = mod.status === "error" || mod.status === "missing_dependency";
  return (
    <div className="flex gap-3 rounded-lg border border-border bg-card/40 p-3 transition-colors hover:border-primary/40">
      <button onClick={onOpen} className="shrink-0" aria-label="Mod details">
        {mod.preview_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mod.preview_url}
            alt=""
            className="size-16 rounded-md border border-border object-cover"
          />
        ) : (
          <div className="flex size-16 items-center justify-center rounded-md border border-border bg-muted">
            <Boxes className="size-6 text-muted-foreground" />
          </div>
        )}
      </button>
      <div className="flex min-w-0 flex-1 flex-col justify-between">
        <div className="min-w-0">
          <button onClick={onOpen} className="block w-full truncate text-left text-sm font-medium hover:underline">
            {name}
            {mod.is_dependency && (
              <span className="ml-1.5 align-middle text-[10px] uppercase tracking-wider text-muted-foreground">
                dependency
              </span>
            )}
          </button>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            {mod.subscribers > 0 && (
              <span className="flex items-center gap-1">
                <Users className="size-3" /> {formatCount(mod.subscribers)}
              </span>
            )}
            {mod.time_updated_remote && (
              <span className="flex items-center gap-1" title="Last updated on Steam">
                <Clock className="size-3" /> {timeAgo(mod.time_updated_remote)}
              </span>
            )}
            <span className="flex items-center gap-1" title={`Added ${new Date(mod.created_at).toLocaleString()}`}>
              <CalendarPlus className="size-3" /> added {timeAgo(mod.created_at)}
            </span>
          </div>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <ModStatusBadge status={mod.status} title={mod.error_message ?? undefined} />
          <div className="flex items-center gap-1.5">
            {failed && (
              <Button
                variant="secondary"
                size="icon"
                disabled={busy}
                onClick={onRetry}
                aria-label="Retry download"
              >
                <RotateCw className="size-4" />
              </Button>
            )}
            <Button
              variant="danger"
              size="icon"
              disabled={busy}
              onClick={onRemove}
              aria-label="Remove mod"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
