"use client";

import Link from "next/link";
import { MoreVertical, Terminal, Settings, Trash2 } from "lucide-react";
import type { Server } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import ProgressBar from "@/components/ProgressBar";
import ServerActions from "./ServerActions";
import { DropdownMenu } from "@/components/ui/dropdown-menu";

const BUSY = new Set(["installing", "updating"]);

export default function ServerTable({
  servers,
  pending,
  onAct,
  onDelete,
}: {
  servers: Server[];
  pending: Record<string, string>;
  onAct: (server: Server, action: string) => void;
  onDelete: (server: Server) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Server</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Ports</th>
            <th className="px-4 py-2.5 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {servers.map((s) => {
            const busy = BUSY.has(s.status);
            return (
              <tr key={s.id} className="border-b border-border last:border-0 transition-colors hover:bg-card/60">
                <td className="px-4 py-3">
                  <Link href={`/servers/${s.id}`} className="font-medium transition-colors hover:text-primary">
                    {s.name}
                  </Link>
                  <div className="text-xs text-muted-foreground">
                    {s.template_id} · app {s.app_id}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {busy ? (
                    <div className="max-w-44">
                      <ProgressBar progress={s.progress} label={s.status === "updating" ? "Updating" : "Installing"} />
                    </div>
                  ) : (
                    <StatusBadge status={s.status} />
                  )}
                </td>
                <td className="hidden px-4 py-3 lg:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {s.ports.map((p) => (
                      <span
                        key={`${p.protocol}-${p.host_port}`}
                        className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-muted-foreground"
                      >
                        {p.host_port}/{p.protocol}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1.5">
                    {!busy && <ServerActions server={s} pendingAction={pending[s.id]} onAct={onAct} compact />}
                    <DropdownMenu
                      align="end"
                      trigger={
                        <span className="flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                          <MoreVertical className="size-4" />
                        </span>
                      }
                      items={[
                        { label: "Console", icon: <Terminal className="size-4" />, href: `/servers/${s.id}/console` },
                        { label: "Settings", icon: <Settings className="size-4" />, href: `/servers/${s.id}/settings` },
                        {
                          label: "Delete",
                          icon: <Trash2 className="size-4" />,
                          danger: true,
                          separatorBefore: true,
                          disabled: !!pending[s.id],
                          onSelect: () => onDelete(s),
                        },
                      ]}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
