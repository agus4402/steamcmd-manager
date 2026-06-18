"use client";

import * as React from "react";
import { Play, Square, RotateCw, Download, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Server } from "@/lib/types";

const BUSY = new Set(["installing", "updating"]);

/**
 * Inline lifecycle action buttons for a server. The available actions depend on
 * status: created/errored → Install; stopped → Start/Restart/Update; running →
 * Stop/Restart/Update. `compact` renders icon-only buttons (used in table rows).
 */
export default function ServerActions({
  server,
  pendingAction,
  onAct,
  compact = false,
}: {
  server: Server;
  pendingAction?: string;
  onAct: (server: Server, action: string) => void;
  compact?: boolean;
}) {
  const busy = !!pendingAction || BUSY.has(server.status);
  const size = compact ? "icon" : "sm";

  function btn(action: string, icon: React.ReactNode, label: string, variant: "default" | "secondary" | "outline" = "secondary") {
    return (
      <Button
        key={action}
        size={size}
        variant={variant}
        disabled={busy}
        onClick={() => onAct(server, action)}
        title={label}
        aria-label={label}
      >
        {icon}
        {!compact && <span>{pendingAction === action ? `${label}…` : label}</span>}
      </Button>
    );
  }

  const buttons: React.ReactNode[] = [];
  if (server.status === "created" || server.status === "errored") {
    buttons.push(btn("install", <Download className="size-4" />, "Install", "default"));
  }
  if (server.status === "stopped") {
    buttons.push(btn("start", <Play className="size-4" />, "Start", "default"));
  }
  if (server.status === "running") {
    buttons.push(btn("stop", <Square className="size-4" />, "Stop"));
  }
  if (server.status === "running" || server.status === "stopped") {
    buttons.push(btn("restart", <RotateCw className="size-4" />, "Restart"));
    buttons.push(btn("update", <RefreshCw className="size-4" />, "Update"));
  }

  return <div className="flex flex-wrap items-center gap-1.5">{buttons}</div>;
}
