"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, setToken } from "@/lib/api";
import { promptSteamCreds } from "@/lib/creds";
import type { Server } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import ProgressBar from "@/components/ProgressBar";

const BUSY = new Set(["installing", "updating"]);

export default function Dashboard() {
  const [servers, setServers] = useState<Server[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setServers(await api.servers());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "backend unreachable");
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  async function act(s: Server, action: string) {
    const creds = promptSteamCreds(s, action);
    setBusyId(s.id);
    try {
      await api.action(s.id, action, creds);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(s: Server) {
    if (!confirm(`Delete "${s.name}"? This removes its container, data volume and frees its ports.`))
      return;
    setBusyId(s.id);
    try {
      await api.remove(s.id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Game Servers</h1>
          <p className="text-sm text-neutral-500">SteamCMD Server Manager</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/new"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            + New server
          </Link>
          <button
            onClick={() => {
              setToken(null);
              window.location.href = "/login";
            }}
            className="text-sm text-neutral-500 hover:text-neutral-300"
          >
            Sign out
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {servers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 py-16 text-center text-neutral-500">
          No servers yet. Create one to get started.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {servers.map((s) => {
            const busy = busyId === s.id || BUSY.has(s.status);
            return (
              <div
                key={s.id}
                className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5"
              >
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <Link href={`/servers/${s.id}`} className="font-medium hover:underline">
                      {s.name}
                    </Link>
                    <div className="text-xs text-neutral-500">
                      {s.template_id} · app {s.app_id}
                    </div>
                  </div>
                  <StatusBadge status={s.status} />
                </div>

                <div className="mb-4 flex flex-wrap gap-1.5">
                  {s.ports.map((p) => (
                    <span
                      key={`${p.protocol}-${p.host_port}`}
                      className="rounded bg-neutral-800 px-2 py-0.5 font-mono text-xs text-neutral-300"
                    >
                      {p.host_port}/{p.protocol}
                    </span>
                  ))}
                </div>

                {BUSY.has(s.status) ? (
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <ProgressBar
                        progress={s.progress}
                        label={s.status === "updating" ? "Updating" : "Installing"}
                      />
                    </div>
                    <Link
                      href={`/servers/${s.id}`}
                      className="rounded bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700"
                    >
                      Console
                    </Link>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2 text-sm">
                    {s.status === "running" ? (
                      <button
                        onClick={() => act(s, "stop")}
                        disabled={busy}
                        className="rounded bg-neutral-700 px-3 py-1.5 hover:bg-neutral-600 disabled:opacity-40"
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        onClick={() => act(s, "start")}
                        disabled={busy}
                        className="rounded bg-emerald-700 px-3 py-1.5 hover:bg-emerald-600 disabled:opacity-40"
                      >
                        Start
                      </button>
                    )}
                    <button
                      onClick={() => act(s, "install")}
                      disabled={busy}
                      className="rounded bg-sky-800 px-3 py-1.5 hover:bg-sky-700 disabled:opacity-40"
                    >
                      Install
                    </button>
                    <Link
                      href={`/servers/${s.id}`}
                      className="rounded bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700"
                    >
                      Console
                    </Link>
                    <button
                      onClick={() => remove(s)}
                      disabled={busy}
                      className="ml-auto rounded px-3 py-1.5 text-red-400 hover:bg-red-500/10 disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
