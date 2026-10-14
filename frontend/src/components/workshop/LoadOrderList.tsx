"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  GripVertical,
  Map as MapIcon,
  Save,
  SlidersHorizontal,
  Undo2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { LoadOrderEntry, MapEntry } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/common/states";
import { cn } from "@/lib/utils";

interface LoadOrderListProps {
  serverId: string;
  entries: LoadOrderEntry[];
  /** Game maps the mods add (PZ Map=), with their own order. */
  maps: MapEntry[];
  /** Config tab link to the sandbox options (mod sections), when the game has one. */
  sandboxPath?: string | null;
  onSaved: () => Promise<unknown>;
}

/**
 * Per-mod-id load order (what the game's mod list receives on start): drag &
 * drop or arrow buttons to reorder, switch to enable/disable each mod.
 * Warnings are recomputed locally while editing.
 */
export function LoadOrderList({
  serverId,
  entries,
  maps,
  sandboxPath,
  onSaved,
}: LoadOrderListProps) {
  const [rows, setRows] = useState(entries);
  const [mapRows, setMapRows] = useState(maps);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => setRows(entries), [entries]);
  useEffect(() => setMapRows(maps), [maps]);

  const modsDirty =
    rows.length !== entries.length ||
    rows.some((r, i) => r.id !== entries[i].id || r.enabled !== entries[i].enabled);
  const mapsDirty =
    mapRows.length !== maps.length ||
    mapRows.some((m, i) => m.name !== maps[i].name || m.enabled !== maps[i].enabled);
  const dirty = modsDirty || mapsDirty;
  // A map is loaded only if some enabled mod (in the edited state) provides it.
  const enabledMods = new Set(rows.filter((r) => r.enabled).map((r) => r.mod_id));
  const mapActive = (m: MapEntry) => m.mod_ids.some((id) => enabledMods.has(id));
  const shown = withWarnings(rows);
  const enabledCount = rows.filter((r) => r.enabled).length;

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length || from === to) return;
    setRows((prev) => {
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  async function save() {
    setSaving(true);
    try {
      await api.setLoadOrder(
        serverId,
        rows.map((r) => ({ id: r.id, enabled: r.enabled })),
        mapRows.map((m) => ({ name: m.name, enabled: m.enabled })),
      );
      toast.success("Load order saved", { description: "Applied on the next start or restart." });
      await onSaved();
    } catch (e) {
      toast.error("Could not save the load order", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setSaving(false);
    }
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={SlidersHorizontal}
        title="No mods to order yet"
        hint="Install Workshop items; the mods inside each one show up here once downloaded."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {enabledCount} of {rows.length} mods enabled · loaded top to bottom
        </span>
        <span className="ml-auto flex gap-2">
          {sandboxPath && (
            <Link
              href={`/servers/${serverId}/config?file=${encodeURIComponent(sandboxPath)}&section=__mods__`}
              className="inline-flex items-center gap-1 text-info hover:underline"
            >
              <SlidersHorizontal className="size-3.5" /> Mod sandbox options
            </Link>
          )}
          <Link
            href={`/servers/${serverId}/config?file=files`}
            className="inline-flex items-center gap-1 text-info hover:underline"
          >
            Mod config files
          </Link>
        </span>
      </div>

      <ol className="flex flex-col divide-y divide-border rounded-lg border border-border" aria-label="Load order">
        {shown.map((r, i) => (
          <li
            key={r.id}
            draggable
            onDragStart={() => setDragIndex(i)}
            onDragOver={(e) => {
              e.preventDefault();
              if (dragIndex !== null && dragIndex !== i) {
                move(dragIndex, i);
                setDragIndex(i);
              }
            }}
            onDragEnd={() => setDragIndex(null)}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5",
              dragIndex === i && "bg-accent",
              !r.enabled && "opacity-60",
            )}
          >
            <GripVertical className="size-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden />
            <span className="w-6 shrink-0 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-x-2 text-sm">
                <span className="font-mono font-medium">{r.mod_id}</span>
                {r.name && r.name !== r.mod_id && <span className="text-muted-foreground">{r.name}</span>}
                {r.maps.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs text-info" title={r.maps.join(", ")}>
                    <MapIcon className="size-3" /> {r.maps.length} map{r.maps.length > 1 ? "s" : ""}
                  </span>
                )}
              </p>
              <p className="truncate text-xs text-muted-foreground" title={r.item_title ?? r.item_id}>
                {r.item_title ?? r.item_id}
              </p>
              {r.warnings.map((w) => (
                <p key={w} className="mt-0.5 flex items-center gap-1 text-xs text-warning">
                  <AlertTriangle className="size-3 shrink-0" /> {w}
                </p>
              ))}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => move(i, i - 1)}
                disabled={i === 0}
                aria-label={`Move ${r.mod_id} up`}
              >
                <ArrowUp />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => move(i, i + 1)}
                disabled={i === rows.length - 1}
                aria-label={`Move ${r.mod_id} down`}
              >
                <ArrowDown />
              </Button>
              <Switch
                checked={r.enabled}
                onCheckedChange={(c) =>
                  setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, enabled: c } : x)))
                }
                aria-label={`Enable ${r.mod_id}`}
              />
            </div>
          </li>
        ))}
      </ol>

      <MapOrder rows={mapRows} setRows={setMapRows} isActive={mapActive} />

      <div className="sticky bottom-0 flex items-center gap-2 border-t border-border bg-background/95 py-3 backdrop-blur">
        <p className="mr-auto text-xs text-muted-foreground">
          {dirty ? "Unsaved changes" : "Changes apply on the next start or restart."}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setRows(entries);
            setMapRows(maps);
          }}
          disabled={!dirty || saving}
        >
          <Undo2 /> Discard
        </Button>
        <Button size="sm" onClick={save} disabled={!dirty || saving}>
          <Save /> {saving ? "Saving…" : "Save order"}
        </Button>
      </div>
    </div>
  );
}

/** Same rules as the backend (load_order_service.compute_warnings), live while editing. */
function withWarnings(rows: LoadOrderEntry[]): LoadOrderEntry[] {
  const pos = new Map(rows.map((r, i) => [r.mod_id, i]));
  const byId = new Map(rows.map((r) => [r.mod_id, r]));
  return rows.map((r, i) => {
    if (!r.enabled) return { ...r, warnings: [] };
    const warnings = r.requires.flatMap((req) => {
      const dep = byId.get(req);
      if (!dep) return [`requires ${req}, which is not installed`];
      if (!dep.enabled) return [`requires ${req}, which is disabled`];
      if ((pos.get(req) ?? 0) > i) return [`requires ${req}, which loads after it`];
      return [];
    });
    return { ...r, warnings };
  });
}

/**
 * The game's map list (PZ Map=): separate from the mod order. Maps listed first
 * take priority where they overlap; the vanilla map is always loaded last.
 */
function MapOrder({
  rows,
  setRows,
  isActive,
}: {
  rows: MapEntry[];
  setRows: React.Dispatch<React.SetStateAction<MapEntry[]>>;
  isActive: (m: MapEntry) => boolean;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length || from === to) return;
    setRows((prev) => {
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  return (
    <section className="mt-4 flex flex-col gap-2" aria-labelledby="map-order-title">
      <div>
        <h3 id="map-order-title" className="flex items-center gap-2 text-sm font-semibold">
          <MapIcon className="size-4 text-muted-foreground" /> Map order
        </h3>
        <p className="text-xs text-muted-foreground">
          Maps added by mods (including spawn-location mods). Maps higher in the list take priority
          where they overlap; the base map always loads last.
        </p>
      </div>
      <ol className="flex flex-col divide-y divide-border rounded-lg border border-border" aria-label="Map order">
        {rows.length === 0 && (
          <li className="px-3 py-3 text-xs text-muted-foreground">
            None of the installed mods add maps. Map mods and spawn-location mods show up here
            once installed, so you can order them.
          </li>
        )}
        {rows.map((m, i) => {
          const active = isActive(m);
          return (
            <li
              key={m.name}
              draggable
              onDragStart={() => setDragIndex(i)}
              onDragOver={(e) => {
                e.preventDefault();
                if (dragIndex !== null && dragIndex !== i) {
                  move(dragIndex, i);
                  setDragIndex(i);
                }
              }}
              onDragEnd={() => setDragIndex(null)}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5",
                dragIndex === i && "bg-accent",
                (!m.enabled || !active) && "opacity-60",
              )}
            >
              <GripVertical className="size-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden />
              <span className="w-6 shrink-0 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{m.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  from {m.mod_ids.join(", ")}
                  {!active && " · its mod is disabled, so it won't load"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => move(i, i - 1)}
                  disabled={i === 0}
                  aria-label={`Move ${m.name} up`}
                >
                  <ArrowUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => move(i, i + 1)}
                  disabled={i === rows.length - 1}
                  aria-label={`Move ${m.name} down`}
                >
                  <ArrowDown />
                </Button>
                <Switch
                  checked={m.enabled}
                  onCheckedChange={(c) =>
                    setRows((prev) => prev.map((x) => (x.name === m.name ? { ...x, enabled: c } : x)))
                  }
                  aria-label={`Load map ${m.name}`}
                />
              </div>
            </li>
          );
        })}
        <li className="flex items-center gap-3 px-3 py-2.5 text-muted-foreground">
          <span className="size-4 shrink-0" aria-hidden />
          <span className="w-6 shrink-0 text-right font-mono text-xs">{rows.length + 1}</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Muldraugh, KY</p>
            <p className="text-xs">Base game map · always loaded last</p>
          </div>
        </li>
      </ol>
    </section>
  );
}
