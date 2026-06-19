"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { RefreshCw, Gauge, ShieldAlert, RotateCcw, Copy } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ComingSoon } from "@/components/common/states";
import { useServerCtx } from "../server-context";

export default function ServerSettingsPage() {
  const router = useRouter();
  const { server, del, act, pending } = useServerCtx();
  const [cloneName, setCloneName] = useState("");
  const [cloning, setCloning] = useState(false);

  const busy = !!pending[server.id];

  function reinstall() {
    if (!confirm("Reinstall this server? Its data volume will be wiped and the game re-downloaded.")) return;
    act(server, "reinstall");
  }

  async function clone() {
    if (!cloneName) return;
    setCloning(true);
    try {
      const created = await api.clone(server.id, cloneName);
      toast.success(`Cloned to ${created.name}`);
      router.push(`/servers/${created.id}`);
    } catch (e) {
      toast.error("Clone failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setCloning(false);
    }
  }

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
          {/* Editing requires PATCH support for `update_on_start` (later phase). */}
          <Switch checked={server.update_on_start} onCheckedChange={() => {}} disabled aria-label="Update on start" />
        </CardContent>
      </Card>

      {/* Clone */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Copy className="size-4 text-muted-foreground" /> Clone server
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Label htmlFor="clone-name">New server name</Label>
            <Input
              id="clone-name"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder={`${server.name}-copy`}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Copies config and data to a new server with fresh ports.
            </p>
          </div>
          <Button onClick={clone} disabled={!cloneName || cloning}>
            {cloning ? "Cloning…" : "Clone"}
          </Button>
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
        <CardContent className="flex flex-col divide-y divide-border">
          <div className="flex items-center justify-between gap-4 pb-4">
            <div>
              <p className="text-sm font-medium">Reinstall server</p>
              <p className="text-xs text-muted-foreground">
                Wipes the data volume and re-downloads the game from scratch.
              </p>
            </div>
            <Button variant="outline" onClick={reinstall} disabled={busy}>
              <RotateCcw className="size-4" /> Reinstall
            </Button>
          </div>
          <div className="flex items-center justify-between gap-4 pt-4">
            <div>
              <p className="text-sm font-medium">Delete this server</p>
              <p className="text-xs text-muted-foreground">
                Removes the container, data volume, backups and frees its ports.
              </p>
            </div>
            <Button variant="destructive" onClick={del} disabled={busy}>
              Delete server
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
