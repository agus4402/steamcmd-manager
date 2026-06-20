"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Plus, Trash2, Clock, CircleCheck, CircleAlert } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ScheduledAction, ScheduleActionType } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { useServerCtx } from "../server-context";

const ACTIONS: { value: ScheduleActionType; label: string }[] = [
  { value: "start", label: "Start" },
  { value: "stop", label: "Stop" },
  { value: "restart", label: "Restart" },
  { value: "update", label: "Update" },
  { value: "backup", label: "Backup" },
];

const PRESETS: { label: string; cron: string }[] = [
  { label: "Hourly", cron: "0 * * * *" },
  { label: "Every 6h", cron: "0 */6 * * *" },
  { label: "Daily 4:00", cron: "0 4 * * *" },
  { label: "Weekly Sun 5:00", cron: "0 5 * * 0" },
];

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function ServerSchedulePage() {
  const { server } = useServerCtx();
  const { data, error, isLoading, mutate } = useSWR<ScheduledAction[]>(["schedule", server.id], () =>
    api.schedule(server.id),
  );

  const [action, setAction] = useState<ScheduleActionType>("restart");
  const [cron, setCron] = useState("0 4 * * *");
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function create() {
    if (!cron.trim()) return;
    setSaving(true);
    try {
      await api.createSchedule(server.id, { action, cron: cron.trim() });
      toast.success("Schedule added");
      await mutate();
    } catch (e) {
      toast.error("Could not add schedule", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function toggle(a: ScheduledAction) {
    setBusyId(a.id);
    try {
      await api.updateSchedule(server.id, a.id, { enabled: !a.enabled });
      await mutate();
    } catch (e) {
      toast.error("Could not update", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(a: ScheduledAction) {
    if (!confirm("Delete this scheduled task?")) return;
    setBusyId(a.id);
    try {
      await api.deleteSchedule(server.id, a.id);
      toast.success("Schedule deleted");
      await mutate();
    } catch (e) {
      toast.error("Could not delete", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  }

  const list = data ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* Add form */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Clock className="size-4 text-muted-foreground" /> New scheduled task
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="sched-action">Action</Label>
              <select
                id="sched-action"
                value={action}
                onChange={(e) => setAction(e.target.value as ScheduleActionType)}
                className={`${inputCls} cursor-pointer`}
              >
                {ACTIONS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="sched-cron">Schedule (cron, UTC)</Label>
              <Input id="sched-cron" value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 4 * * *" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Presets:</span>
            {PRESETS.map((p) => (
              <button
                key={p.cron}
                type="button"
                onClick={() => setCron(p.cron)}
                className="cursor-pointer rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {p.label}
              </button>
            ))}
            <Button className="ml-auto" onClick={create} disabled={saving || !cron.trim()}>
              <Plus className="size-4" /> {saving ? "Adding…" : "Add task"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* List */}
      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load schedule"}
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
          icon={Clock}
          title="No scheduled tasks"
          hint="Add a task above to automate restarts, updates or backups."
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Task</th>
                <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Last run</th>
                <th className="px-4 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <div className="font-medium capitalize">{a.action}</div>
                    <div className="font-mono text-xs text-muted-foreground">{a.cron}</div>
                  </td>
                  <td className="hidden px-4 py-3 sm:table-cell">
                    {a.last_run_at ? (
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        {a.last_status === "error" ? (
                          <CircleAlert className="size-3.5 text-danger" />
                        ) : (
                          <CircleCheck className="size-3.5 text-success" />
                        )}
                        <span title={a.last_error ?? undefined}>{new Date(a.last_run_at).toLocaleString()}</span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">never</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-3">
                      <Switch
                        checked={a.enabled}
                        disabled={busyId === a.id}
                        onCheckedChange={() => toggle(a)}
                        aria-label={a.enabled ? "Disable task" : "Enable task"}
                      />
                      <Button
                        variant="danger"
                        size="icon"
                        disabled={busyId === a.id}
                        onClick={() => remove(a)}
                        aria-label="Delete task"
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
  );
}
