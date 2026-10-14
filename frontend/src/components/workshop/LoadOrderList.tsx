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
import type { LoadOrderEntry } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/common/states";
import { cn } from "@/lib/utils";

interface LoadOrderListProps {
  serverId: string;
  entries: LoadOrderEntry[];
  /** Config tab link to the sandbox options (mod sections), when the game has one. */
  sandboxPath?: string | null;
  onSaved: () => Promise<unknown>;
}

/**
 * Per-mod-id load order (what the game's mod list receives on start): drag &
 * drop or arrow buttons to reorder, switch to enable/disable each mod.
 * Warnings are recomputed locally while editing.
 */
export function LoadOrderList({ serverId, entries, sandboxPath, onSaved }: LoadOrderListProps) {
  const [rows, setRows] = useState(entries);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => setRows(entries), [entries]);

  const dirty =
    rows.length !== entries.length ||
    rows.some((r, i) => r.id !== entries[i].id || r.enabled !== entries[i].enabled);
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

      <div className="sticky bottom-0 flex items-center gap-2 border-t border-border bg-background/95 py-3 backdrop-blur">
        <p className="mr-auto text-xs text-muted-foreground">
          {dirty ? "Unsaved changes" : "Changes apply on the next start or restart."}
        </p>
        <Button variant="outline" size="sm" onClick={() => setRows(entries)} disabled={!dirty || saving}>
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
