"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";

export interface StatPoint {
  t: number;
  cpu: number;
  mem: number;
  memPct: number;
}

const MAX_POINTS = 40;

/**
 * Polls /api/servers/{id}/stats and keeps a short client-side history so charts
 * can render a live time series (the backend returns point-in-time snapshots).
 * Polling pauses when `enabled` is false (e.g. server not running).
 */
export function useServerStats(serverId: string, enabled = true, intervalMs = 2500) {
  const { data, error, isLoading } = useSWR<Stats>(
    enabled ? ["stats", serverId] : null,
    () => api.stats(serverId),
    { refreshInterval: intervalMs, dedupingInterval: 1000, shouldRetryOnError: false },
  );

  const [history, setHistory] = useState<StatPoint[]>([]);
  const lastT = useRef(0);

  useEffect(() => {
    if (!data || !data.running) return;
    const now = Date.now();
    // Guard against duplicate appends from re-renders with the same snapshot.
    if (now - lastT.current < intervalMs * 0.5) return;
    lastT.current = now;
    setHistory((prev) =>
      [...prev, { t: now, cpu: data.cpu_pct, mem: data.mem_used, memPct: data.mem_pct }].slice(-MAX_POINTS),
    );
  }, [data, intervalMs]);

  // Reset history when switching servers or pausing.
  useEffect(() => {
    setHistory([]);
  }, [serverId, enabled]);

  return { stats: data ?? null, history, error, isLoading };
}
