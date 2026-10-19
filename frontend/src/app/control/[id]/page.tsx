"use client";

import { use, useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Boxes, Copy, Lock, LogOut, Play, RotateCw, Square } from "lucide-react";
import { ApiError } from "@/lib/api";
import {
  controlApi,
  getControlToken,
  setControlToken,
  type ControlAction,
  type ControlServer,
} from "@/lib/controlApi";
import { copyToClipboard } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import StatusBadge from "@/components/StatusBadge";
import PlayerList from "@/components/servers/PlayerList";

/**
 * Public control page of one server (no panel login, no sidebar): basic info +
 * start/stop/restart, unlocked with the server's own password (SERVER_PASSWORD).
 */
export default function ServerControlPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  // null = not read yet (avoids a password-form flash before localStorage is read).
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => setSignedIn(!!getControlToken(id)), [id]);

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        {signedIn === null ? null : signedIn ? (
          <ControlPanel
            serverId={id}
            onSignedOut={() => {
              setControlToken(id, null);
              setSignedIn(false);
            }}
          />
        ) : (
          <PasswordForm serverId={id} onSignedIn={() => setSignedIn(true)} />
        )}
      </div>
    </main>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-xl sm:p-8">{children}</div>
  );
}

function Header({ name, subtitle }: { name: string; subtitle: string }) {
  return (
    <div className="mb-6 flex items-center gap-3">
      <Boxes className="size-7 shrink-0 text-primary" />
      <div className="min-w-0">
        <h1 className="truncate font-semibold leading-tight">{name}</h1>
        <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}

function PasswordForm({ serverId, onSignedIn }: { serverId: string; onSignedIn: () => void }) {
  const { data: meta, error: metaError } = useSWR(["control-meta", serverId], () =>
    controlApi.meta(serverId),
  );
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await controlApi.login(serverId, password);
      onSignedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "sign in failed");
    } finally {
      setBusy(false);
    }
  }

  if (metaError) {
    return (
      <Shell>
        <Header name="Server not found" subtitle="Check the link you were given." />
      </Shell>
    );
  }
  if (!meta) {
    return (
      <Shell>
        <Skeleton className="h-32 w-full" />
      </Shell>
    );
  }
  if (!meta.enabled) {
    return (
      <Shell>
        <Header name={meta.name} subtitle={meta.game} />
        <p className="text-sm text-muted-foreground">
          This server has no password set, so its control page is disabled. Ask the server admin to
          set one.
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <form onSubmit={submit}>
        <Header name={meta.name} subtitle={meta.game} />
        {error && (
          <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}
        <div className="mb-6">
          <Label htmlFor="server-password">Server password</Label>
          <Input
            id="server-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
          />
        </div>
        <Button type="submit" disabled={busy || !password} className="w-full">
          <Lock className="size-4" /> {busy ? "Checking…" : "Unlock"}
        </Button>
      </form>
    </Shell>
  );
}

const VERB: Record<ControlAction, string> = {
  start: "Starting",
  stop: "Stopping",
  restart: "Restarting",
};

function ControlPanel({ serverId, onSignedOut }: { serverId: string; onSignedOut: () => void }) {
  const { data: server, error, mutate } = useSWR<ControlServer>(
    ["control-server", serverId],
    () => controlApi.server(serverId),
    { refreshInterval: 5000 },
  );
  const running = server?.status === "running";
  const { data: query } = useSWR(
    server ? ["control-query", serverId, running] : null,
    () => controlApi.query(serverId),
    { refreshInterval: running ? 10000 : 0, shouldRetryOnError: false },
  );
  const [pending, setPending] = useState<ControlAction | null>(null);
  const [host, setHost] = useState("");

  useEffect(() => setHost(window.location.hostname), []);

  // Expired session or password changed by the admin: back to the password form.
  const unauthorized = error instanceof ApiError && error.status === 401;
  useEffect(() => {
    if (unauthorized) onSignedOut();
  }, [unauthorized, onSignedOut]);

  async function act(action: ControlAction) {
    if (action === "stop" && !confirm("Stop the server? Connected players will be disconnected.")) {
      return;
    }
    setPending(action);
    try {
      const next = await controlApi.action(serverId, action);
      toast.success(`${VERB[action]} ${next.name}`);
      await mutate(next, { revalidate: true });
    } catch (e) {
      toast.error(`Could not ${action} the server`, {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setPending(null);
    }
  }

  if (!server) {
    return (
      <Shell>
        {error && !unauthorized ? (
          <p className="text-sm text-danger">
            {error instanceof ApiError ? error.message : "Could not load the server"}
          </p>
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </Shell>
    );
  }

  const busy = pending !== null || server.status === "installing" || server.status === "updating";
  const canStart = server.status === "stopped" || server.status === "errored";
  const canStop = server.status === "running";
  const canRestart = server.status === "running" || server.status === "stopped";

  function label(action: ControlAction, text: string) {
    return pending === action ? `${text}…` : text;
  }

  return (
    <Shell>
      <Header name={server.name} subtitle={server.game} />

      <dl className="mb-6 flex flex-col gap-3 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-muted-foreground">Status</dt>
          <dd>
            <StatusBadge status={server.status} />
          </dd>
        </div>
        {server.ports.map((p) => {
          // The port's own tunnel wins; otherwise this host + port, unless the
          // page was opened through the panel's tunnel (that host has no game
          // traffic), where only the port number is shown.
          const viaPanelTunnel = !!server.panel_public_host && host === server.panel_public_host;
          if (!p.public_address && viaPanelTunnel) {
            return (
              <div key={`${p.protocol}-${p.host_port}`} className="flex items-center justify-between gap-3">
                <dt className="capitalize text-muted-foreground">{p.name}</dt>
                <dd className="font-mono text-xs text-muted-foreground">
                  port {p.host_port}/{p.protocol}
                </dd>
              </div>
            );
          }
          const address = p.public_address ?? `${host}:${p.host_port}`;
          return (
            <div key={`${p.protocol}-${p.host_port}`} className="flex items-center justify-between gap-3">
              <dt className="capitalize text-muted-foreground">{p.name}</dt>
              <dd>
                <button
                  onClick={async () => {
                    if (await copyToClipboard(address)) toast.success(`Copied ${address}`);
                    else toast.error("Could not copy — select the address and copy it manually");
                  }}
                  className="inline-flex items-center gap-2 rounded-md px-2 py-1 font-mono text-xs transition-colors hover:bg-accent"
                  title="Copy address"
                >
                  {address}
                  <span className="text-muted-foreground">/{p.protocol}</span>
                  <Copy className="size-3.5 text-muted-foreground" />
                </button>
              </dd>
            </div>
          );
        })}
      </dl>

      {query?.supported && (
        <div className="mb-6">
          <PlayerList query={query} running={running} compact />
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <Button disabled={busy || !canStart} onClick={() => act("start")}>
          <Play className="size-4" /> {label("start", "Start")}
        </Button>
        <Button variant="secondary" disabled={busy || !canStop} onClick={() => act("stop")}>
          <Square className="size-4" /> {label("stop", "Stop")}
        </Button>
        <Button variant="secondary" disabled={busy || !canRestart} onClick={() => act("restart")}>
          <RotateCw className="size-4" /> {label("restart", "Restart")}
        </Button>
      </div>
      {(server.status === "installing" || server.status === "updating") && (
        <p className="mt-3 text-xs text-muted-foreground">
          The server is {server.status}; the buttons unlock when it finishes.
        </p>
      )}

      <button
        onClick={onSignedOut}
        className="mx-auto mt-6 flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <LogOut className="size-3.5" /> Sign out
      </button>
    </Shell>
  );
}
