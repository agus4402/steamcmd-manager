"use client";

import { useLayoutEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Users, Star, Clock, Download, Trash2, ArrowUpCircle, ExternalLink } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { LoadOrderEntry, WorkshopMod } from "@/lib/types";
import { formatBytes, formatCount, timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ErrorState } from "@/components/common/states";
import { SteamBBCode } from "@/components/workshop/SteamBBCode";

const STEAM_ITEM_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id=";

interface Props {
  itemId: string | null;
  installedMod: WorkshopMod | null;
  busy: boolean;
  onClose: () => void;
  onInstall: (itemId: string) => void;
  onUpdate: (mod: WorkshopMod) => void;
  onRemove: (mod: WorkshopMod) => void;
  onOpenItem: (itemId: string) => void;
  /** Game-level mods found inside this item (when the game supports toggling them). */
  submods?: LoadOrderEntry[];
  onToggleSubmod?: (entry: LoadOrderEntry, enabled: boolean) => void;
}

export function ModDetailsDrawer({
  itemId,
  installedMod,
  busy,
  onClose,
  onInstall,
  onUpdate,
  onRemove,
  onOpenItem,
  submods,
  onToggleSubmod,
}: Props) {
  const { data, error, isLoading } = useSWR(
    itemId ? ["mod-details", itemId] : null,
    () => api.modDetails(itemId as string),
  );

  return (
    <Drawer open={itemId !== null} onClose={onClose} title={data?.title ?? "Mod details"}>
      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load mod details"}
        />
      ) : isLoading || !data ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="aspect-video w-full" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {data.preview_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={data.preview_url}
              alt={data.title ?? itemId ?? ""}
              className="w-full rounded-lg border border-border object-cover"
            />
          )}

          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <Stat icon={Users} label="Subscribers" value={formatCount(data.subscribers)} />
            <Stat icon={Star} label="Favorites" value={formatCount(data.favorites)} />
            <Stat icon={Clock} label="Updated" value={timeAgo(data.time_updated)} />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{itemId}</span>
            {data.file_size > 0 && <span>· {formatBytes(data.file_size)}</span>}
            <a
              href={`${STEAM_ITEM_URL}${itemId}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 hover:text-foreground"
            >
              Steam page <ExternalLink className="size-3" />
            </a>
          </div>

          {data.description && <Description key={itemId} text={data.description} />}

          {installedMod && submods && submods.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Mods in this item ({submods.length})</h3>
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                {submods.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-xs font-medium">{s.mod_id}</p>
                      {s.name && <p className="truncate text-xs text-muted-foreground">{s.name}</p>}
                    </div>
                    <Switch
                      checked={s.enabled}
                      disabled={busy || !onToggleSubmod}
                      onCheckedChange={(c) => onToggleSubmod?.(s, c)}
                      aria-label={`Enable ${s.mod_id}`}
                    />
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Toggle optional parts; the order is set in Load order.
              </p>
            </div>
          )}

          {data.dependencies.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">
                Dependencies ({data.dependencies.length})
              </h3>
              <ul className="flex flex-col gap-1">
                {data.dependencies.map((d) => (
                  <li key={d.item_id}>
                    <button
                      onClick={() => onOpenItem(d.item_id)}
                      className="font-mono text-xs text-info hover:underline"
                    >
                      {d.title || d.item_id}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Dependencies are installed automatically.
              </p>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            {!installedMod ? (
              <Button disabled={busy} onClick={() => itemId && onInstall(itemId)}>
                <Download className="size-4" /> Install
              </Button>
            ) : (
              <>
                {installedMod.status === "update_available" && (
                  <Button disabled={busy} onClick={() => onUpdate(installedMod)}>
                    <ArrowUpCircle className="size-4" /> Update
                  </Button>
                )}
                <Button variant="danger" disabled={busy} onClick={() => onRemove(installedMod)}>
                  <Trash2 className="size-4" /> Remove
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
}

const COLLAPSED_HEIGHT = 320;

/** Steam description (BBCode), collapsed with a fade when it is long. */
function Description({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflows, setOverflows] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el) setOverflows(el.scrollHeight > COLLAPSED_HEIGHT + 40);
  }, [text]);

  const collapsed = overflows && !expanded;
  return (
    <div>
      <div
        ref={ref}
        className="relative overflow-hidden"
        style={collapsed ? { maxHeight: COLLAPSED_HEIGHT } : undefined}
      >
        <SteamBBCode text={text} className="text-sm text-muted-foreground" />
        {collapsed && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-popover to-transparent" />
        )}
      </div>
      {overflows && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs font-medium text-info hover:underline"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-2 py-2">
      <Icon className="mx-auto mb-1 size-4 text-muted-foreground" />
      <div className="font-medium">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}
