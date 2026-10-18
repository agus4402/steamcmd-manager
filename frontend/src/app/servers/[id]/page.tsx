"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import useSWR from "swr";
import { Copy, Cpu, Gamepad2, Globe, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { copyToClipboard } from "@/lib/utils";
import type { PanelTunnel } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import MiniMetrics from "@/components/servers/MiniMetrics";
import { useServerCtx } from "./server-context";

export default function ServerOverview() {
  const { server } = useServerCtx();

  async function copyPort(port: number) {
    if (await copyToClipboard(String(port))) toast.success(`Copied port ${port}`);
    else toast.error("Could not copy — select the port and copy it manually");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="flex flex-col gap-6 lg:col-span-2">
        {server.status === "errored" && server.error_message && (
          <pre className="max-h-40 overflow-auto rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-xs text-danger">
            {server.error_message}
          </pre>
        )}

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Details</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            <Detail label="Template" value={server.template_id} />
            <Detail label="Steam App ID" value={String(server.app_id)} />
            <Detail label="Login" value={server.anonymous_login ? "Anonymous" : "Account required"} />
            <Detail label="Update on start" value={server.update_on_start ? "Yes" : "No"} />
            <Detail label="Created" value={new Date(server.created_at).toLocaleString()} />
            <Detail label="ID" value={server.id} mono />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Cpu className="size-4 text-muted-foreground" /> Live metrics
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MiniMetrics
              serverId={server.id}
              running={server.status === "running"}
              href={`/servers/${server.id}/metrics`}
            />
          </CardContent>
        </Card>
      </div>

      <div className="flex h-fit flex-col gap-6">
      {/* Ports */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Connection ports</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {server.ports.length === 0 && <p className="text-sm text-muted-foreground">No ports allocated.</p>}
          {server.ports.map((p) => (
            <button
              key={`${p.protocol}-${p.host_port}`}
              onClick={() => copyPort(p.host_port)}
              className="flex cursor-pointer items-center justify-between rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-accent"
              title="Copy port"
            >
              <span className="text-muted-foreground">
                {p.name}
                {!p.is_primary && <span className="text-muted-foreground/60"> (extra)</span>}
              </span>
              <span className="flex items-center gap-2 font-mono">
                {p.host_port}/{p.protocol}
                <Copy className="size-3.5 text-muted-foreground" />
              </span>
            </button>
          ))}
          <Link
            href={`/servers/${server.id}/console`}
            className="mt-1 text-center text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Open console →
          </Link>
        </CardContent>
      </Card>

      {"SERVER_PASSWORD" in server.variables && (
        <ControlLinkCard serverId={server.id} enabled={!!server.variables.SERVER_PASSWORD} />
      )}
      </div>
    </div>
  );
}

/** Links to the public control page (/control/<id>), unlocked with the server password. */
function ControlLinkCard({ serverId, enabled }: { serverId: string; enabled: boolean }) {
  // Built after mount: window is unknown during server rendering.
  const [url, setUrl] = useState("");
  useEffect(() => setUrl(`${window.location.origin}/control/${serverId}`), [serverId]);
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Gamepad2 className="size-4 text-muted-foreground" /> Player control page
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {enabled ? (
          <>
            <p className="text-xs text-muted-foreground">
              Anyone with the server password can start, stop and restart it from this page.
            </p>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Local network</span>
              <CopyLink url={url} />
            </div>
            <PublicLink serverId={serverId} />
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            Set a server password in{" "}
            <Link href={`/servers/${serverId}/config`} className="text-info hover:underline">
              Config → Variables
            </Link>{" "}
            to enable a page where players can start, stop and restart the server.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CopyLink({ url }: { url: string }) {
  return (
    <button
      onClick={async () => {
        if (await copyToClipboard(url)) toast.success("Copied control page link");
        else toast.error("Could not copy — select the link and copy it manually");
      }}
      className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left transition-colors hover:bg-accent"
      title="Copy link"
    >
      <span className="truncate font-mono text-xs">{url}</span>
      <Copy className="size-3.5 shrink-0 text-muted-foreground" />
    </button>
  );
}

/**
 * Internet link through the panel tunnel (Playit, plain TCP to the panel port).
 * One tunnel serves every server's control page; the admin API stays private
 * (only /api/control is reachable through it).
 */
function PublicLink({ serverId }: { serverId: string }) {
  const { data, mutate } = useSWR<PanelTunnel>("panel-tunnel", () => api.integrations.panelTunnel(), {
    // Poll while the provider is still allocating the address.
    refreshInterval: (d) =>
      d?.tunnel && (!d.tunnel.remote_domain || d.tunnel.status === "pending") ? 4000 : 0,
  });
  const [port, setPort] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    const localPort = Number(port || data?.default_port);
    if (!localPort) return;
    setBusy(true);
    try {
      await api.integrations.createPanelTunnel(localPort);
      toast.success("Creating public link", { description: "The address shows up in a few seconds." });
      await mutate();
    } catch (e) {
      toast.error("Could not create the public link", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!data?.integration_id || !data.tunnel) return;
    if (!confirm("Remove the public link? Links already shared stop working.")) return;
    setBusy(true);
    try {
      await api.integrations.deleteTunnel(data.integration_id, data.tunnel.id);
      toast.success("Public link removed");
      await mutate();
    } catch (e) {
      toast.error("Could not remove the public link", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }

  if (!data) return null;
  const tunnel = data.tunnel;

  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Globe className="size-3.5" /> Internet{data.provider_name ? ` (${data.provider_name})` : ""}
      </span>
      {!data.integration_id ? (
        <p className="text-xs text-muted-foreground">
          <Link href="/settings/integrations" className="text-info hover:underline">
            Connect Playit.gg
          </Link>{" "}
          to get a link that works outside your network.
        </p>
      ) : !tunnel ? (
        <>
          <div className="flex gap-2">
            <Input
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder={data.default_port ? String(data.default_port) : "Panel port"}
              aria-label="Panel port"
              className="h-8 w-24 font-mono text-xs"
            />
            <Button size="sm" onClick={create} disabled={busy || !(port || data.default_port)}>
              {busy ? "Creating…" : "Create public link"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Opens a tunnel to the panel&apos;s port (the one in your browser&apos;s address bar).
            Only the control pages work through it; the admin panel stays private.
          </p>
        </>
      ) : tunnel.status === "error" ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-danger">{tunnel.error_message ?? "Tunnel error"}</p>
          <Button size="sm" variant="secondary" onClick={remove} disabled={busy}>
            Remove
          </Button>
        </div>
      ) : !tunnel.remote_domain ? (
        <p className="text-xs text-muted-foreground">Allocating the public address…</p>
      ) : (
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <CopyLink url={`http://${tunnel.remote_domain}/control/${serverId}`} />
          </div>
          <Button
            size="icon"
            variant="ghost"
            onClick={remove}
            disabled={busy}
            aria-label="Remove public link"
            title="Remove public link"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className={`mt-0.5 ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
