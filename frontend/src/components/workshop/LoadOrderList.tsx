"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  GripVertical,
  Map as MapIcon,
  Save,
  Search,
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
  /** Search text: hides non-matching rows (reordering still uses full-list positions). */
  query?: string;
  onSaved: () => Promise<unknown>;
  /** Open the Workshop item's details (clicking a row). */
  onOpenItem?: (itemId: string) => void;
  /** Look up a required mod that isn't installed (search it in Browse). */
  onSearchMissing?: (modId: string) => void;
}

/** A load-order problem of one mod, computed live while editing. */
interface Issue {
  kind: "missing" | "disabled" | "after";
  req: string;
}
type Row = LoadOrderEntry & { issues: Issue[] };

function matches(q: string, values: (string | null | undefined)[]): boolean {
  return !q || values.some((v) => v?.toLowerCase().includes(q));
}

/** Pointer drag (the wheel and edge auto-scroll keep working mid-drag) + keyboard. */
function useDragSensors() {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
}

/** Moves `activeId` to `overId`'s place in the FULL list, even if rows are filtered out. */
function reorder<T>(list: T[], idOf: (t: T) => string, { active, over }: DragEndEvent): T[] {
  if (!over || active.id === over.id) return list;
  const from = list.findIndex((t) => idOf(t) === active.id);
  const to = list.findIndex((t) => idOf(t) === over.id);
  return from < 0 || to < 0 ? list : arrayMove(list, from, to);
}

/**
 * Per-mod-id load order (what the game's mod list receives on start): drag the
 * grip or use the arrows to reorder, switch to enable/disable each mod, click a
 * row for the item's details. Warnings are recomputed locally while editing.
 */
export function LoadOrderList({
  serverId,
  entries,
  maps,
  sandboxPath,
  query = "",
  onSaved,
  onOpenItem,
  onSearchMissing,
}: LoadOrderListProps) {
  const q = query.trim().toLowerCase();
  const [rows, setRows] = useState(entries);
  const [mapRows, setMapRows] = useState(maps);
  const [saving, setSaving] = useState(false);
  const sensors = useDragSensors();
  // Stable ids keep dnd-kit's generated aria attributes equal on server and client.
  const dndId = useId();

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
  const itemByMod = new Map(rows.map((r) => [r.mod_id, r.item_id]));
  const shown = withIssues(rows);
  const enabledCount = rows.filter((r) => r.enabled).length;
  const isMatch = (r: LoadOrderEntry) => matches(q, [r.mod_id, r.name, r.item_title, r.item_id]);
  const visible = shown.filter(isMatch);

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length || from === to) return;
    setRows((prev) => arrayMove(prev, from, to));
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
          {q && ` · showing ${visible.length} matching`}
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

      <DndContext
        id={`${dndId}-mods`}
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={(e) => setRows((prev) => reorder(prev, (r) => r.id, e))}
      >
        <SortableContext items={visible.map((r) => r.id)} strategy={verticalListSortingStrategy}>
          <ol className="flex flex-col divide-y divide-border rounded-lg border border-border" aria-label="Load order">
            {visible.length === 0 && (
              <li className="px-3 py-3 text-xs text-muted-foreground">No mods match “{query.trim()}”.</li>
            )}
            {visible.map((r) => {
              // Position in the FULL list: numbering and arrows stay right while filtered.
              const i = rows.findIndex((x) => x.id === r.id);
              return (
                <SortableRow
                  key={r.id}
                  id={r.id}
                  label={r.mod_id}
                  onOpen={onOpenItem ? () => onOpenItem(r.item_id) : undefined}
                  className={cn(!r.enabled && "opacity-60")}
                  controls={
                    <>
                      <Button variant="ghost" size="icon" onClick={() => move(i, i - 1)} disabled={i === 0} aria-label={`Move ${r.mod_id} up`}>
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
                    </>
                  }
                  footer={
                    r.issues.length > 0 && (
                      <IssueList issues={r.issues} onSearchMissing={onSearchMissing} />
                    )
                  }
                >
                  <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-x-2 text-sm">
                      <span className="font-mono font-medium">{r.mod_id}</span>
                      {r.name && r.name !== r.mod_id && <span className="text-muted-foreground">{r.name}</span>}
                      {r.maps.length > 0 && (
                        <span className="inline-flex items-center gap-1 text-xs text-info" title={r.maps.join(", ")}>
                          <MapIcon className="size-3" /> {r.maps.length} map{r.maps.length > 1 ? "s" : ""}
                        </span>
                      )}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground" title={r.item_title ?? r.item_id}>
                      {r.item_title ?? r.item_id}
                    </span>
                  </span>
                </SortableRow>
              );
            })}
          </ol>
        </SortableContext>
      </DndContext>

      <MapOrder
        dndId={`${dndId}-maps`}
        rows={mapRows}
        setRows={setMapRows}
        isActive={mapActive}
        query={q}
        onOpenMap={
          onOpenItem
            ? (m) => {
                const itemId = m.mod_ids.map((id) => itemByMod.get(id)).find(Boolean);
                if (itemId) onOpenItem(itemId);
              }
            : undefined
        }
      />

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

/**
 * A reorderable row. Dragging starts ONLY from the grip; clicking the rest of the
 * row (outside `controls` and `footer`) calls `onOpen`.
 */
function SortableRow({
  id,
  label,
  onOpen,
  className,
  controls,
  footer,
  children,
}: {
  id: string;
  label: string;
  onOpen?: () => void;
  className?: string;
  controls: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(
        "flex items-start gap-2 px-2 py-2 transition-colors",
        onOpen && "hover:bg-accent/40",
        isDragging && "relative z-10 bg-accent opacity-100 shadow-lg ring-1 ring-primary/40",
        className,
      )}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`Drag ${label} to reorder`}
        title="Drag to reorder"
        className="mt-0.5 flex size-7 shrink-0 cursor-grab touch-none items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground active:cursor-grabbing"
      >
        <GripVertical className="size-4" />
      </button>
      <div className="min-w-0 flex-1">
        {onOpen ? (
          <button
            type="button"
            onClick={onOpen}
            className="flex w-full items-start gap-3 rounded py-0.5 text-left"
            title="Show details"
          >
            {children}
          </button>
        ) : (
          <div className="flex w-full items-start gap-3 py-0.5">{children}</div>
        )}
        {footer}
      </div>
      <div className="flex shrink-0 items-center gap-1">{controls}</div>
    </li>
  );
}

function IssueList({
  issues,
  onSearchMissing,
}: {
  issues: Issue[];
  onSearchMissing?: (modId: string) => void;
}) {
  return (
    <div className="ml-9 mt-0.5 flex flex-col gap-0.5">
      {issues.map((w) => (
        <p key={`${w.kind}-${w.req}`} className="flex items-center gap-1 text-xs text-warning">
          <AlertTriangle className="size-3 shrink-0" />
          {w.kind === "missing" && onSearchMissing ? (
            <button
              type="button"
              onClick={() => onSearchMissing(w.req)}
              className="text-left hover:underline"
              title={`Search ${w.req} in the Workshop`}
            >
              requires <span className="font-mono font-medium">{w.req}</span>, which is not installed
              <span className="ml-1.5 inline-flex items-center gap-0.5 text-info">
                <Search className="size-3" /> Search
              </span>
            </button>
          ) : (
            <span>{issueText(w)}</span>
          )}
        </p>
      ))}
    </div>
  );
}

function issueText(w: Issue): string {
  if (w.kind === "missing") return `requires ${w.req}, which is not installed`;
  if (w.kind === "disabled") return `requires ${w.req}, which is disabled`;
  return `requires ${w.req}, which loads after it`;
}

/** Same rules as the backend (load_order_service.compute_warnings), live while editing. */
function withIssues(rows: LoadOrderEntry[]): Row[] {
  const pos = new Map(rows.map((r, i) => [r.mod_id, i]));
  const byId = new Map(rows.map((r) => [r.mod_id, r]));
  return rows.map((r, i) => {
    if (!r.enabled) return { ...r, issues: [] };
    const issues = r.requires.flatMap((req): Issue[] => {
      const dep = byId.get(req);
      if (!dep) return [{ kind: "missing", req }];
      if (!dep.enabled) return [{ kind: "disabled", req }];
      if ((pos.get(req) ?? 0) > i) return [{ kind: "after", req }];
      return [];
    });
    return { ...r, issues };
  });
}

/**
 * The game's map list (PZ Map=): separate from the mod order. Maps listed first
 * take priority where they overlap; the vanilla map is always loaded last.
 */
function MapOrder({
  dndId,
  rows,
  setRows,
  isActive,
  query,
  onOpenMap,
}: {
  dndId: string;
  rows: MapEntry[];
  setRows: React.Dispatch<React.SetStateAction<MapEntry[]>>;
  isActive: (m: MapEntry) => boolean;
  /** Lower-cased search text ("" = show all). */
  query: string;
  onOpenMap?: (m: MapEntry) => void;
}) {
  const sensors = useDragSensors();
  const isMatch = (m: MapEntry) => matches(query, [m.name, ...m.mod_ids]);
  const visible = rows.filter(isMatch);
  const key = (m: MapEntry) => `map:${m.name}`;

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length || from === to) return;
    setRows((prev) => arrayMove(prev, from, to));
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
      <DndContext
        id={dndId}
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={(e) => setRows((prev) => reorder(prev, key, e))}
      >
        <SortableContext items={visible.map(key)} strategy={verticalListSortingStrategy}>
          <ol className="flex flex-col divide-y divide-border rounded-lg border border-border" aria-label="Map order">
            {rows.length === 0 && (
              <li className="px-3 py-3 text-xs text-muted-foreground">
                None of the installed mods add maps. Map mods and spawn-location mods show up here
                once installed, so you can order them.
              </li>
            )}
            {rows.length > 0 && query && visible.length === 0 && (
              <li className="px-3 py-3 text-xs text-muted-foreground">No maps match “{query}”.</li>
            )}
            {visible.map((m) => {
              const i = rows.findIndex((x) => x.name === m.name);
              const active = isActive(m);
              return (
                <SortableRow
                  key={m.name}
                  id={key(m)}
                  label={m.name}
                  onOpen={onOpenMap ? () => onOpenMap(m) : undefined}
                  className={cn((!m.enabled || !active) && "opacity-60")}
                  controls={
                    <>
                      <Button variant="ghost" size="icon" onClick={() => move(i, i - 1)} disabled={i === 0} aria-label={`Move ${m.name} up`}>
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
                    </>
                  }
                >
                  <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{m.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      from {m.mod_ids.join(", ")}
                      {!active && " · its mod is disabled, so it won't load"}
                    </span>
                  </span>
                </SortableRow>
              );
            })}
            <li className="flex items-center gap-2 px-2 py-2.5 text-muted-foreground">
              <span className="size-7 shrink-0" aria-hidden />
              <span className="w-6 shrink-0 text-right font-mono text-xs">{rows.length + 1}</span>
              <div className="ml-1 min-w-0 flex-1">
                <p className="text-sm font-medium">Muldraugh, KY</p>
                <p className="text-xs">Base game map · always loaded last</p>
              </div>
            </li>
          </ol>
        </SortableContext>
      </DndContext>
    </section>
  );
}
