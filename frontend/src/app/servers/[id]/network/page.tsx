"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Cable, ExternalLink, Plug, Plus, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Integration, IntegrationTunnel } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { TunnelStatusBadge } from "@/components/integrations/status";
import { useServerCtx } from "../server-context";

const selectClass =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export default function ServerNetworkPage() {
  const { server } = useServerCtx();

  // Find a connected, tunnel-capable integration (Playit today).
  const { data: integrations, isLoading: loadingIntegrations } = useSWR<Integration[]>(
    "integrations",
    () => api.integrations.list(),
  );
  const provider =
    integrations?.find(
      (i) => i.capabilities.includes("tunnels") && i.status === "connected" && i.id,
    ) ?? null;
  const integrationId = provider?.id ?? null;

  const { data: allTunnels, error, isLoading, mutate } = useSWR<IntegrationTunnel[]>(
    integrationId ? ["tunnels", integrationId] : null,
    () => api.integrations.tunnels(integrationId as string),
    { refreshInterval: (d) => (d?.some((t) => t.status === "pending") ? 2000 : 0) },
  );
  const tunnels = (allTunnels ?? []).filter((t) => t.server_id === server.id);

  // Create form (server is fixed to this one).
  const primary = server.ports.find((p) => p.is_primary) ?? server.ports[0];
  const [localPort, setLocalPort] = useState<string>(primary ? String(primary.host_port) : "");
  const [protocol, setProtocol] = useState<string>(
    primary && (primary.protocol === "tcp" || primary.protocol === "udp") ? primary.protocol : "udp",
  );
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  // Keep the port default in sync once the server data arrives.
  useEffect(() => {
    if (primary && !localPort) setLocalPort(String(primary.host_port));
  }, [primary, localPort]);

  function onPickPort(value: string) {
    setLocalPort(value);
    const p = server.ports.find((pp) => String(pp.host_port) === value);
    if (p && (p.protocol === "tcp" || p.protocol === "udp")) setProtocol(p.protocol);
  }

  async function createTunnel() {
    if (!integrationId) return;
    const port = Number(localPort);
    if (!port || port < 1 || port > 65535) {
      toast.error("Enter a valid port (1–65535)");
      return;
    }
    setCreating(true);
    try {
      await api.integrations.createTunnel(integrationId, {
        server_id: server.id,
        local_port: port,
        protocol,
        name: name || null,
      });
      toast.success("Tunnel requested", { description: "Provisioning — it will appear shortly." });
      setName("");
      await mutate();
    } catch (e) {
      toast.error("Could not create tunnel", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setCreating(false);
    }
  }

  async function removeTunnel(t: IntegrationTunnel) {
    if (!integrationId) return;
    if (!confirm(`Delete tunnel "${t.name}"? This cannot be undone.`)) return;
    try {
      await api.integrations.deleteTunnel(integrationId, t.id);
      toast.success("Tunnel deleted");
      await mutate();
    } catch (e) {
      toast.error("Delete failed", { description: e instanceof ApiError ? e.message : String(e) });
    }
  }

  // Not linked yet → prompt to connect the integration.
  if (!loadingIntegrations && !provider) {
    return (
      <EmptyState
        icon={Plug}
        title="No tunnel provider connected"
        hint="Connect Playit.gg to expose this server to the internet without port forwarding."
        action={
          <Link href="/settings/integrations" className={buttonVariants({ variant: "default" })}>
            <Plug className="size-4" /> Go to Integrations
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Plus className="size-4 text-muted-foreground" /> New tunnel
            {provider && (
              <span className="ml-auto text-xs font-normal text-muted-foreground">
                via {provider.name}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-4">
          <div>
            <Label htmlFor="port">Local port</Label>
            {server.ports.length > 0 ? (
              <select id="port" className={selectClass} value={localPort} onChange={(e) => onPickPort(e.target.value)}>
                {server.ports.map((p) => (
                  <option key={`${p.host_port}/${p.protocol}`} value={p.host_port}>
                    {p.host_port} ({p.name})
                  </option>
                ))}
              </select>
            ) : (
              <Input
                id="port"
                type="number"
                min={1}
                max={65535}
                value={localPort}
                onChange={(e) => setLocalPort(e.target.value)}
                placeholder="27015"
              />
            )}
          </div>
          <div>
            <Label htmlFor="protocol">Protocol</Label>
            <select id="protocol" className={selectClass} value={protocol} onChange={(e) => setProtocol(e.target.value)}>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="name">Name (optional)</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`${server.name}-${protocol}-${localPort || "port"}`}
            />
          </div>
          <div className="flex items-end sm:col-span-4">
            <Button onClick={createTunnel} disabled={creating || !localPort}>
              <Plus className="size-4" /> {creating ? "Creating…" : "Create tunnel"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load tunnels"}
          onRetry={() => mutate()}
        />
      ) : isLoading || loadingIntegrations ? (
        <div className="flex flex-col gap-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : tunnels.length === 0 ? (
        <EmptyState
          icon={Cable}
          title="No tunnels for this server"
          hint="Create a tunnel above to get a public address for this server."
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Tunnel</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Public address</th>
                <th className="px-4 py-2.5 font-medium">Local</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tunnels.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-medium">{t.name}</div>
                    {t.error_message && <div className="text-xs text-danger">{t.error_message}</div>}
                  </td>
                  <td className="hidden px-4 py-3 md:table-cell">
                    {t.remote_domain ? (
                      <a
                        href={`http://${t.remote_domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-mono text-xs text-info hover:underline"
                      >
                        {t.remote_domain} <ExternalLink className="size-3" />
                      </a>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {t.local_port}/{t.protocol}
                  </td>
                  <td className="px-4 py-3">
                    <TunnelStatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <Button variant="danger" size="icon" onClick={() => removeTunnel(t)} aria-label="Delete tunnel">
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
