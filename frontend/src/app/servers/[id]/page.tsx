"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Copy, Cpu } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import MiniMetrics from "@/components/servers/MiniMetrics";
import { useServerCtx } from "./server-context";

export default function ServerOverview() {
  const { server } = useServerCtx();

  function copyPort(port: number) {
    navigator.clipboard?.writeText(String(port));
    toast.success(`Copied port ${port}`);
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

      {/* Ports */}
      <Card className="h-fit">
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
