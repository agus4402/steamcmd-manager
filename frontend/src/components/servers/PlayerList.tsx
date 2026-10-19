"use client";

import { Lock, Map as MapIcon, Users } from "lucide-react";
import type { ServerQuery } from "@/lib/types";
import { cn } from "@/lib/utils";

/** "1h 05m" / "12m" / "40s" for a connection time in seconds. */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

/**
 * Live player count + list from the game's query protocol. Renders the states a
 * running server goes through: not answering yet (booting), online, and games
 * that report a count but no names.
 */
export default function PlayerList({
  query,
  running,
  compact = false,
}: {
  query: ServerQuery | undefined;
  running: boolean;
  /** Fewer details (public control page). */
  compact?: boolean;
}) {
  if (!running) {
    return <p className="text-sm text-muted-foreground">Start the server to see who&apos;s online.</p>;
  }
  if (!query) {
    return <p className="text-sm text-muted-foreground">Asking the server…</p>;
  }
  if (!query.online || !query.info) {
    return (
      <div className="flex flex-col gap-1 text-sm text-muted-foreground">
        <p>The game isn&apos;t answering yet; it usually starts responding once it finishes loading.</p>
        {!compact && query.error && (
          <p className="font-mono text-xs text-muted-foreground/70">
            {query.query_port ? `udp/${query.query_port}: ` : ""}
            {query.error}
          </p>
        )}
      </div>
    );
  }

  const { info } = query;
  const humans = Math.max(0, info.players - info.bots);
  const pct = info.max_players ? (humans / info.max_players) * 100 : 0;
  // Players still connecting have no name yet; some games (Valheim) never send names.
  const named = (query.players ?? []).filter((p) => p.name.trim());

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-muted-foreground" />
          <span className="text-2xl font-semibold tabular-nums">{humans}</span>
          <span className="text-sm text-muted-foreground">/ {info.max_players} players</span>
          {info.bots > 0 && <span className="text-xs text-muted-foreground">+{info.bots} bots</span>}
        </div>
        {!compact && info.password && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" title="Password protected">
            <Lock className="size-3.5" /> Password
          </span>
        )}
      </div>

      <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-success transition-all duration-500"
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>

      {!compact && (info.map || info.version) && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {info.map && (
            <span className="flex items-center gap-1">
              <MapIcon className="size-3.5" /> {info.map}
            </span>
          )}
          {info.version && <span className="font-mono">v{info.version}</span>}
        </div>
      )}

      {named.length > 0 ? (
        <ul className={cn("flex flex-col divide-y divide-border rounded-md border border-border", compact && "text-sm")}>
          {named.map((p, i) => (
            <li key={`${p.name}-${i}`} className="flex items-center justify-between gap-3 px-3 py-1.5 text-sm">
              <span className="truncate">{p.name}</span>
              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                {formatDuration(p.duration)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        humans > 0 && (
          <p className="text-xs text-muted-foreground">This game doesn&apos;t report player names.</p>
        )
      )}
    </div>
  );
}
