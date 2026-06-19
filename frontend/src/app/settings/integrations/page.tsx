"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Plug, RefreshCw, Settings2, Link2, Link2Off } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Integration } from "@/lib/types";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { IntegrationStatusBadge, providerIcon } from "@/components/integrations/status";
import ConnectModal from "@/components/integrations/ConnectModal";

export default function IntegrationsPage() {
  const { data, error, isLoading, mutate } = useSWR<Integration[]>(
    "integrations",
    () => api.integrations.list(),
    { refreshInterval: 5000 },
  );
  const [connecting, setConnecting] = useState<{ provider: string; name: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function disconnect(it: Integration) {
    if (!it.id) return;
    if (!confirm(`Disconnect ${it.name}? Its tunnels will be removed.`)) return;
    setBusy(it.provider);
    try {
      await api.integrations.disconnect(it.id);
      toast.success(`${it.name} disconnected`);
      await mutate();
    } catch (e) {
      toast.error("Disconnect failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function sync(it: Integration) {
    if (!it.id) return;
    setBusy(it.provider);
    try {
      await api.integrations.sync(it.id);
      toast.success("Synced");
      await mutate();
    } catch (e) {
      toast.error("Sync failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  const integrations = data ?? [];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Integrations"
        description="Connect external services to expose servers and extend the panel."
      />

      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load integrations"}
          onRetry={() => mutate()}
        />
      ) : isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 w-full" />
          ))}
        </div>
      ) : integrations.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No integrations available"
          hint="Providers will appear here as they are added to the panel."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {integrations.map((it) => {
            const Icon = providerIcon(it.icon);
            const isBusy = busy === it.provider;
            const connected = it.status === "connected";
            const canConfigure = connected && it.capabilities.includes("tunnels") && it.id;
            return (
              <Card key={it.provider} className="flex flex-col">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2">
                      <Icon className="size-4 text-muted-foreground" /> {it.name}
                    </span>
                    <IntegrationStatusBadge status={it.status} />
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col gap-3">
                  <p className="flex-1 text-sm text-muted-foreground">{it.description}</p>

                  {it.account_label && (
                    <p className="text-xs text-muted-foreground">
                      Account: <span className="text-foreground">{it.account_label}</span>
                    </p>
                  )}
                  {connected && (
                    <p className="text-xs text-muted-foreground">
                      {it.tunnel_count} tunnel{it.tunnel_count === 1 ? "" : "s"}
                      {it.last_sync_at && ` · synced ${new Date(it.last_sync_at).toLocaleString()}`}
                    </p>
                  )}
                  {it.status === "error" && it.error_message && (
                    <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs text-danger">
                      {it.error_message}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {connected ? (
                      <>
                        {canConfigure && (
                          <Link
                            href={`/settings/integrations/${it.provider}`}
                            className={buttonVariants({ variant: "default", size: "sm" })}
                          >
                            <Settings2 className="size-4" /> Configure
                          </Link>
                        )}
                        <Button variant="outline" size="sm" disabled={isBusy} onClick={() => sync(it)}>
                          <RefreshCw className="size-4" /> Sync
                        </Button>
                        <Button variant="danger" size="sm" disabled={isBusy} onClick={() => disconnect(it)}>
                          <Link2Off className="size-4" /> Disconnect
                        </Button>
                      </>
                    ) : it.status === "pending" ? (
                      <Button
                        size="sm"
                        onClick={() => setConnecting({ provider: it.provider, name: it.name })}
                      >
                        <Link2 className="size-4" /> Resume
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        disabled={isBusy}
                        onClick={() => setConnecting({ provider: it.provider, name: it.name })}
                      >
                        <Link2 className="size-4" /> Connect
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {connecting && (
        <ConnectModal
          provider={connecting.provider}
          providerName={connecting.name}
          onClose={() => {
            setConnecting(null);
            mutate();
          }}
          onConnected={() => {
            setConnecting(null);
            mutate();
          }}
        />
      )}
    </div>
  );
}
