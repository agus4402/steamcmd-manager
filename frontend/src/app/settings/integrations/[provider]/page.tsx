"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowLeft, ExternalLink, Plus, Trash2, Cable } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Integration, IntegrationTunnel, Server } from "@/lib/types";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TunnelStatusBadge } from "@/components/integrations/status";

const selectClass =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export default function IntegrationDetailPage() {
  const params = useParams<{ provider: string }>();
  const provider = params.provider;

  const { data: integrations } = useSWR<Integration[]>("integrations", () =>
    api.integrations.list(),
  );
  const integration = integrations?.find((i) => i.provider === provider) ?? null;
  const integrationId = integration?.id ?? null;

  const {
    data: tunnels,
    error,
    isLoading,
    mutate,
  } = useSWR<IntegrationTunnel[]>(
    integrationId ? ["tunnels", integrationId] : null,
    () => api.integrations.tunnels(integrationId as string),
    { refreshInterval: (d) => (d?.some((t) => t.status === "pending") ? 2000 : 0) },
  );

  const { data: servers } = useSWR<Server[]>("servers", () => api.servers());

  // Create-tunnel form state
  const [serverId, setServerId] = useState<string>("");
  const [localPort, setLocalPort] = useState<string>("");
  const [protocol, setProtocol] = useState<string>("tcp");
  const [name, setName] = useState<string>("");
  const [creating, setCreating] = useState(false);

  const selectedServer = useMemo(
    () => servers?.find((s) => s.id === serverId) ?? null,
    [servers, serverId],
  );

  function onPickServer(id: string) {
    setServerId(id);
    const srv = servers?.find((s) => s.id === id);
    const primary = srv?.ports.find((p) => p.is_primary) ?? srv?.ports[0];
    if (primary) {
      setLocalPort(String(primary.host_port));
      if (primary.protocol === "tcp" || primary.protocol === "udp") setProtocol(primary.protocol);
    }
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
        server_id: serverId || null,
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

  const list = tunnels ?? [];

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        href="/settings/integrations"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Integrations
      </Link>

      <PageHeader
        title={integration?.name ?? provider}
        description={integration?.account_label ? `Account: ${integration.account_label}` : "Manage tunnels"}
      />

      {!integration ? (
        <ErrorState message="Integration not connected." />
      ) : (
        <div className="flex flex-col gap-6">
          {/* Create tunnel */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Plus className="size-4 text-muted-foreground" /> New tunnel
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-4">
              <div className="sm:col-span-2">
                <Label htmlFor="server">Server</Label>
                <select
                  id="server"
                  className={selectClass}
                  value={serverId}
                  onChange={(e) => onPickServer(e.target.value)}
                >
                  <option value="">— none —</option>
                  {servers?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="port">Local port</Label>
                {selectedServer && selectedServer.ports.length > 0 ? (
                  <select
                    id="port"
                    className={selectClass}
                    value={localPort}
                    onChange={(e) => setLocalPort(e.target.value)}
                  >
                    {selectedServer.ports.map((p) => (
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
                <select
                  id="protocol"
                  className={selectClass}
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                >
                  <option value="tcp">TCP</option>
                  <option value="udp">UDP</option>
                </select>
              </div>
              <div className="sm:col-span-3">
                <Label htmlFor="name">Name (optional)</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Auto-generated from server and port"
                />
              </div>
              <div className="flex items-end">
                <Button className="w-full" onClick={createTunnel} disabled={creating || !localPort}>
                  <Plus className="size-4" /> {creating ? "Creating…" : "Create"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Tunnel list */}
          {error ? (
            <ErrorState
              message={error instanceof ApiError ? error.message : "Could not load tunnels"}
              onRetry={() => mutate()}
            />
          ) : isLoading ? (
            <div className="flex flex-col gap-2">
              {[0, 1].map((i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <EmptyState
              icon={Cable}
              title="No tunnels yet"
              hint="Create a tunnel above to expose a server to the internet."
            />
          ) : (
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Tunnel</th>
                    <th className="hidden px-4 py-2.5 font-medium md:table-cell">Domain</th>
                    <th className="px-4 py-2.5 font-medium">Local</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((t) => (
                    <tr key={t.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3">
                        <div className="font-medium">{t.name}</div>
                        {t.error_message && (
                          <div className="text-xs text-danger">{t.error_message}</div>
                        )}
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
                          <Button
                            variant="danger"
                            size="icon"
                            onClick={() => removeTunnel(t)}
                            aria-label="Delete tunnel"
                          >
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
      )}
    </div>
  );
}
