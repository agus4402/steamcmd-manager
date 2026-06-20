"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Archive, Loader2, Minus, Plus, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { BackupJob, ScheduledAction, Snapshot } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { RestoreModal } from "@/components/RestoreModal";
import { useServerCtx } from "../server-context";

export default function ServerBackupsPage() {
  const { server, mutate: mutateServer } = useServerCtx();
  const { data, error, isLoading, mutate } = useSWR<Snapshot[]>(["backups", server.id], () =>
    api.backups(server.id),
  );

  const { data: job, mutate: refreshStatus } = useSWR<BackupJob>(
    ["backup-status", server.id],
    () => api.backupStatus(server.id),
    { refreshInterval: (d) => (d?.status === "creating" ? 1500 : 0) },
  );

  // Backup schedules — used for the summary row
  const { data: schedules } = useSWR<ScheduledAction[]>(
    ["schedules", server.id],
    () => api.schedule(server.id),
  );
  const backupScheduleCount = schedules?.filter((s) => s.action === "backup").length ?? 0;

  // Backup limit — local state kept in sync with server.max_backups
  const [limit, setLimit] = useState(server.max_backups ?? 0);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const saveLimit = useCallback(
    (value: number) => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        try {
          await api.updateBackupConfig(server.id, value);
          await mutateServer();
        } catch (e) {
          toast.error("Could not save backup limit", {
            description: e instanceof ApiError ? e.message : String(e),
          });
        }
      }, 800);
    },
    [server.id, mutateServer],
  );

  function changeLimit(delta: number) {
    setLimit((prev) => {
      const next = Math.max(0, prev + delta);
      saveLimit(next);
      return next;
    });
  }

  const [busyId, setBusyId] = useState<string | null>(null);
  const [restoreSnap, setRestoreSnap] = useState<Snapshot | null>(null);
  const prevStatus = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!job) return;
    if (prevStatus.current === "creating" && job.status === "done") {
      toast.success("Backup created");
      mutate();
    } else if (prevStatus.current === "creating" && job.status === "error") {
      toast.error("Backup failed", { description: job.error ?? undefined });
    }
    prevStatus.current = job.status;
  }, [job, mutate]);

  const creating = job?.status === "creating";

  async function create() {
    try {
      await api.createBackup(server.id);
      await refreshStatus();
    } catch (e) {
      toast.error("Could not start backup", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    }
  }

  async function remove(snap: Snapshot) {
    if (!confirm("Delete this backup? This cannot be undone.")) return;
    setBusyId(snap.id);
    try {
      await api.deleteBackup(server.id, snap.id);
      toast.success("Backup deleted");
      await mutate();
    } catch (e) {
      toast.error("Delete failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  }

  function handleRestoreClose(serverMutated: boolean) {
    setRestoreSnap(null);
    if (serverMutated) mutateServer();
  }

  const snapshots = data ?? [];

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Point-in-time snapshots of this server&apos;s data volume.
        </p>
        <Button onClick={create} disabled={creating}>
          <Plus className="size-4" />
          {creating ? "Creating…" : "Create backup"}
        </Button>
      </div>

      {/* Backup limit control */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
        <div>
          <p className="text-sm font-medium">Backup limit</p>
          <p className="text-xs text-muted-foreground">
            {limit === 0 ? "Unlimited — oldest deleted automatically when a limit is set." : `Keep the last ${limit} backup${limit === 1 ? "" : "s"} — oldest deleted automatically.`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="icon"
            onClick={() => changeLimit(-1)}
            disabled={limit === 0}
            aria-label="Decrease backup limit"
          >
            <Minus className="size-4" />
          </Button>
          <span className="w-7 text-center text-sm font-semibold tabular-nums">{limit}</span>
          <Button
            variant="secondary"
            size="icon"
            onClick={() => changeLimit(1)}
            aria-label="Increase backup limit"
          >
            <Plus className="size-4" />
          </Button>
        </div>
      </div>

      {/* Schedule summary */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
        <div>
          <p className="text-sm font-medium">Automatic backups</p>
          <p className="text-xs text-muted-foreground">
            {backupScheduleCount > 0
              ? `${backupScheduleCount} schedule${backupScheduleCount === 1 ? "" : "s"} active`
              : "No schedule configured"}
          </p>
        </div>
        <Link
          href={`/servers/${server.id}/schedule`}
          className="text-xs text-primary hover:underline"
        >
          {backupScheduleCount > 0 ? "View schedules →" : "Set up →"}
        </Link>
      </div>

      {/* Spinner while creating */}
      {creating && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-8">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Creating backup…</p>
          <p className="text-xs text-muted-foreground">
            Archiving the data volume — this can take a while for large games. You can leave this
            page; the backup keeps running.
          </p>
        </div>
      )}

      {/* Snapshot list */}
      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load backups"}
          onRetry={() => mutate()}
        />
      ) : isLoading ? (
        <div className="flex flex-col gap-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : snapshots.length === 0 ? (
        !creating && (
          <EmptyState
            icon={Archive}
            title="No backups yet"
            hint="Create a backup to snapshot the current server data."
            action={
              <Button onClick={create} disabled={creating}>
                <Plus className="size-4" /> Create backup
              </Button>
            }
          />
        )
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Backup</th>
                <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Size</th>
                <th className="px-4 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 font-medium">
                      <Archive className="size-4 text-muted-foreground" />
                      {s.created_at ? new Date(s.created_at).toLocaleString() : s.id}
                    </div>
                    <div className="pl-6 font-mono text-xs text-muted-foreground">{s.id}</div>
                  </td>
                  <td className="hidden px-4 py-3 font-mono text-muted-foreground sm:table-cell">
                    {formatBytes(s.size)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busyId === s.id}
                        onClick={() => setRestoreSnap(s)}
                      >
                        <RotateCcw className="size-4" /> Restore
                      </Button>
                      <Button
                        variant="danger"
                        size="icon"
                        disabled={busyId === s.id}
                        onClick={() => remove(s)}
                        aria-label="Delete backup"
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

      <RestoreModal
        snap={restoreSnap}
        serverId={server.id}
        onClose={handleRestoreClose}
      />
    </div>
  );
}
