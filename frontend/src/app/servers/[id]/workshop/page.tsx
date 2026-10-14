"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import {
  Boxes,
  Plus,
  Trash2,
  Upload,
  Users,
  Clock,
  RotateCw,
  RefreshCw,
  ArrowUpCircle,
  FolderSync,
  Info,
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
import { Input, Label } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { ModStatusBadge } from "@/components/workshop/ModStatusBadge";
import { ModDetailsDrawer } from "@/components/workshop/ModDetailsDrawer";
import { ImportModsModal } from "@/components/workshop/ImportModsModal";
import { WorkshopBrowse } from "@/components/workshop/WorkshopBrowse";
import { LoadOrderList } from "@/components/workshop/LoadOrderList";
import { cn } from "@/lib/utils";
import { useServerCtx } from "../server-context";

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
  const [importInput, setImportInput] = useState<string | undefined>(undefined);
  const [item, setItem] = useState("");
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [detailItemId, setDetailItemId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const [bulkBusy, setBulkBusy] = useState(false);

  const mods = data ?? [];
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

  async function add() {
    if (!item.trim()) return;
    setAdding(true);
    try {
      await api.addMod(server.id, item.trim());
      toast.success("Mod queued for download");
      setItem("");
      await mutate();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.message.startsWith("collection:")) {
        // A collection: preview its members in the import dialog instead.
        setImportInput(item.trim());
        setImportOpen(true);
        setItem("");
        return;
      }
      toast.error("Could not add mod", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setAdding(false);
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

      {tab === "order" && loadOrder?.supported ? (
        <LoadOrderList
          serverId={server.id}
          entries={loadOrder.entries}
          sandboxPath={sandboxPath}
          onSaved={() => mutateLoadOrder()}
        />
      ) : tab === "browse" ? (
        <WorkshopBrowse
          gameId={server.workshop_app_id as number}
          installedIds={installedIds}
          busyId={busyId}
          onOpenItem={setDetailItemId}
          onInstall={install}
        />
      ) : (
        <>
      {/* Add bar */}
      <Card>
        <CardContent className="flex flex-col gap-3 pt-5">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
            <div>
              <Label htmlFor="ws-item">Workshop item ID or URL</Label>
              <Input
                id="ws-item"
                value={item}
                onChange={(e) => setItem(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && add()}
                placeholder="e.g. 2289615…"
              />
            </div>
            <Button onClick={add} disabled={adding || !item.trim()}>
              <Plus className="size-4" /> {adding ? "Adding…" : "Add"}
            </Button>
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Upload className="size-4" /> Import
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Add an item or paste a collection URL (it opens the import preview), or use Import for
            a list of IDs. Mods download via SteamCMD into the server&apos;s data and apply on next
            start.
          </p>
        </CardContent>
      </Card>

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
          hint="Add a Steam Workshop item above to install it on this server."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {mods.map((m) => (
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
          initialInput={importInput}
          onClose={() => {
            setImportOpen(false);
            setImportInput(undefined);
          }}
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
              <span className="flex items-center gap-1">
                <Clock className="size-3" /> {timeAgo(mod.time_updated_remote)}
              </span>
            )}
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
