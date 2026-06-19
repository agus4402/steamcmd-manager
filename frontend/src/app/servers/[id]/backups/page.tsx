"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Archive, Plus, RotateCcw, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { BackupJob, Snapshot } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import ProgressBar from "@/components/ProgressBar";
import { EmptyState, ErrorState } from "@/components/common/states";
import { useServerCtx } from "../server-context";

export default function ServerBackupsPage() {
  const { server, mutate: mutateServer } = useServerCtx();
  const { data, error, isLoading, mutate } = useSWR<Snapshot[]>(["backups", server.id], () =>
    api.backups(server.id),
  );

  // Backups run as a background job; poll its status (fast while creating).
  const { data: job, mutate: refreshStatus } = useSWR<BackupJob>(
    ["backup-status", server.id],
    () => api.backupStatus(server.id),
    { refreshInterval: (d) => (d?.status === "creating" ? 1500 : 0) },
  );

  const [busyId, setBusyId] = useState<string | null>(null);
  const prevStatus = useRef<string | undefined>(undefined);

  // Surface job completion exactly once, and refresh the list when a backup lands.
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
      await refreshStatus(); // flip into "creating" and start polling
    } catch (e) {
      toast.error("Could not start backup", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    }
  }

  async function restore(snap: Snapshot) {
    if (!confirm("Restore this backup? The server will be stopped and its current data overwritten.")) return;
    setBusyId(snap.id);
    try {
      await api.restoreBackup(server.id, snap.id);
      toast.success("Backup restored", { description: "The server was stopped; start it to apply." });
      await mutateServer();
    } catch (e) {
      toast.error("Restore failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
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

  const snapshots = data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Point-in-time snapshots of this server&apos;s data volume.
        </p>
        <Button onClick={create} disabled={creating}>
          <Plus className="size-4" /> {creating ? "Creating…" : "Create backup"}
        </Button>
      </div>

      {/* Live progress for an in-flight backup */}
      {creating && (
        <div className="rounded-lg border border-border bg-card p-4">
          <ProgressBar progress={null} label="Creating backup" />
          <p className="mt-2 text-xs text-muted-foreground">
            Archiving the data volume — this can take a while for large games. You can leave this page;
            the backup keeps running.
          </p>
        </div>
      )}

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
                        onClick={() => restore(s)}
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
    </div>
  );
}
