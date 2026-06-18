"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { promptSteamCreds } from "@/lib/creds";
import type { Progress, Server } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import Console from "@/components/Console";
import ProgressBar from "@/components/ProgressBar";

type Tab = "console" | "config" | "ports";

const BUSY = new Set(["installing", "updating"]);

export default function ServerDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [server, setServer] = useState<Server | null>(null);
  const [tab, setTab] = useState<Tab>("console");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [vars, setVars] = useState<Record<string, string>>({});
  // Live progress from the console WS — keeps the bar in sync with the console
  // (vs. the slower 3s poll). Falls back to the polled value when unavailable.
  const [liveProgress, setLiveProgress] = useState<Progress | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.server(id);
      setServer(s);
      setVars((prev) => (Object.keys(prev).length ? prev : s.variables));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "unreachable");
    }
  }, [id]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  // Drop stale live progress once the install/update finishes.
  useEffect(() => {
    if (server && !BUSY.has(server.status)) setLiveProgress(null);
  }, [server]);

  async function act(action: string) {
    const creds = server ? promptSteamCreds(server, action) : undefined;
    setBusy(true);
    setError(null);
    try {
      await api.action(id, action, creds);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveVars() {
    setBusy(true);
    try {
      await api.patch(id, { variables: vars });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete "${server?.name}"? Removes container, data volume and frees ports.`)) return;
    await api.remove(id);
    router.push("/");
  }

  if (!server) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10 text-neutral-500">
        {error ?? "Loading…"}
      </main>
    );
  }

  const installing = BUSY.has(server.status);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← Dashboard
      </Link>

      <header className="mb-6 mt-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{server.name}</h1>
          <StatusBadge status={server.status} />
        </div>
        <div className="text-sm text-neutral-500">
          {server.template_id} · app {server.app_id}
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {server.status === "errored" && server.error_message && (
        <pre className="mb-4 max-h-32 overflow-auto rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-xs text-red-300">
          {server.error_message}
        </pre>
      )}

      {installing ? (
        <div className="mb-6 flex items-center gap-4">
          <div className="flex-1">
            <ProgressBar
              progress={liveProgress ?? server.progress}
              label={server.status === "updating" ? "Updating" : "Installing"}
            />
          </div>
          <button onClick={remove} disabled={busy} className="rounded px-3 py-1.5 text-sm text-red-400 hover:bg-red-500/10 disabled:opacity-40">Delete</button>
        </div>
      ) : (
        <div className="mb-6 flex flex-wrap gap-2 text-sm">
          <button onClick={() => act("install")} disabled={busy} className="rounded bg-sky-800 px-3 py-1.5 hover:bg-sky-700 disabled:opacity-40">Install</button>
          {server.status === "running" ? (
            <button onClick={() => act("stop")} disabled={busy} className="rounded bg-neutral-700 px-3 py-1.5 hover:bg-neutral-600 disabled:opacity-40">Stop</button>
          ) : (
            <button onClick={() => act("start")} disabled={busy} className="rounded bg-emerald-700 px-3 py-1.5 hover:bg-emerald-600 disabled:opacity-40">Start</button>
          )}
          <button onClick={() => act("restart")} disabled={busy} className="rounded bg-neutral-700 px-3 py-1.5 hover:bg-neutral-600 disabled:opacity-40">Restart</button>
          <button onClick={() => act("update")} disabled={busy} className="rounded bg-amber-800 px-3 py-1.5 hover:bg-amber-700 disabled:opacity-40">Update</button>
          <button onClick={remove} disabled={busy} className="ml-auto rounded px-3 py-1.5 text-red-400 hover:bg-red-500/10 disabled:opacity-40">Delete</button>
        </div>
      )}

      <div className="mb-4 flex gap-1 border-b border-neutral-800 text-sm">
        {(["console", "config", "ports"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 capitalize ${tab === t ? "border-b-2 border-emerald-500 text-white" : "text-neutral-500 hover:text-neutral-300"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "console" && <Console serverId={id} onProgress={setLiveProgress} />}

      {tab === "config" && (
        <div className="grid gap-4">
          {Object.keys(vars).length === 0 && (
            <p className="text-sm text-neutral-500">This template has no variables.</p>
          )}
          {Object.entries(vars).map(([k, v]) => (
            <div key={k}>
              <label className="mb-1 block text-sm text-neutral-400">{k}</label>
              <input
                value={v}
                onChange={(e) => setVars({ ...vars, [k]: e.target.value })}
                className="w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-emerald-600"
              />
            </div>
          ))}
          {Object.keys(vars).length > 0 && (
            <div>
              <button onClick={saveVars} disabled={busy} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
                Save
              </button>
              <p className="mt-2 text-xs text-neutral-600">Changes apply on next start.</p>
            </div>
          )}
        </div>
      )}

      {tab === "ports" && (
        <div className="grid gap-2">
          <p className="text-sm text-neutral-400">Connect clients to these host ports:</p>
          {server.ports.map((p) => (
            <div
              key={`${p.protocol}-${p.host_port}`}
              className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900/60 px-4 py-2"
            >
              <span className="text-sm text-neutral-400">{p.name}</span>
              <button
                onClick={() => navigator.clipboard?.writeText(String(p.host_port))}
                className="font-mono text-sm hover:text-emerald-400"
                title="copy"
              >
                {p.host_port}/{p.protocol}
              </button>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
