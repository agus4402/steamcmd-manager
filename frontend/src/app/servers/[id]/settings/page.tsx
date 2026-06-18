"use client";

import { RefreshCw, Gauge, ShieldAlert } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ComingSoon } from "@/components/common/states";
import { useServerCtx } from "../server-context";

export default function ServerSettingsPage() {
  const { server, del, pending } = useServerCtx();

  return (
    <div className="grid max-w-3xl gap-6">
      {/* Lifecycle */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <RefreshCw className="size-4 text-muted-foreground" /> Lifecycle
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Update on start</p>
            <p className="text-xs text-muted-foreground">
              Run a SteamCMD update before launching. Currently set by the template.
            </p>
          </div>
          {/* Editing requires PATCH support for `update_on_start` (Phase 2). */}
          <Switch checked={server.update_on_start} onCheckedChange={() => {}} disabled aria-label="Update on start" />
        </CardContent>
      </Card>

      {/* Resource limits */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Gauge className="size-4 text-muted-foreground" /> Resource limits
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ComingSoon
            title="Per-server limits"
            description="Override CPU, memory and PID limits for this server."
            backend="Add limit fields to the Server model + per-container overrides in the agent."
          />
        </CardContent>
      </Card>

      {/* Danger zone */}
      <Card className="border-destructive/40">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm text-danger">
            <ShieldAlert className="size-4" /> Danger zone
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Delete this server</p>
            <p className="text-xs text-muted-foreground">
              Removes the container, data volume and frees its ports. This cannot be undone.
            </p>
          </div>
          <Button variant="destructive" onClick={del} disabled={!!pending[server.id]}>
            Delete server
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
