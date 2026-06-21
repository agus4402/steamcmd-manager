"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Bell, CheckCheck, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { NotificationIcon, timeAgo } from "@/components/notifications/shared";

export default function NotificationsPage() {
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const { data, error, isLoading, mutate } = useSWR<Notification[]>(
    ["notifications", filter],
    () => api.notifications.list(filter === "unread", 200),
    { refreshInterval: 30000 },
  );

  const list = data ?? [];

  async function markAll() {
    try {
      await api.notifications.markAllRead();
      await mutate();
      toast.success("All marked as read");
    } catch (e) {
      toast.error("Failed", { description: e instanceof ApiError ? e.message : String(e) });
    }
  }

  async function clearAll() {
    if (!confirm("Delete all notifications? This cannot be undone.")) return;
    try {
      await api.notifications.clearAll();
      await mutate();
    } catch (e) {
      toast.error("Failed", { description: e instanceof ApiError ? e.message : String(e) });
    }
  }

  async function markRead(n: Notification) {
    if (n.read) return;
    await api.notifications.markRead(n.id);
    mutate();
  }

  async function remove(n: Notification) {
    await api.notifications.remove(n.id);
    mutate();
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Notifications"
        description="Alerts on crashes, failed installs, backups and scheduled tasks"
        actions={
          list.length > 0 ? (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={markAll}>
                <CheckCheck className="size-4" /> Mark all read
              </Button>
              <Button variant="ghost" size="sm" onClick={clearAll}>
                <Trash2 className="size-4" /> Clear
              </Button>
            </div>
          ) : undefined
        }
      />

      {/* Filter */}
      <div className="mb-4 flex w-fit items-center gap-1 rounded-md border border-border bg-card p-1">
        {(["all", "unread"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "cursor-pointer rounded px-3 py-1.5 text-sm font-medium capitalize transition-colors",
              filter === f ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load notifications"}
          onRetry={() => mutate()}
        />
      ) : isLoading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={Bell}
          title={filter === "unread" ? "No unread notifications" : "No notifications"}
          hint="You'll see alerts here when something needs your attention."
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          {list.map((n) => (
            <div
              key={n.id}
              className={cn(
                "group flex items-start gap-3 border-b border-border px-4 py-3 last:border-0 transition-colors hover:bg-card/60",
                !n.read && "bg-primary/5",
              )}
            >
              <NotificationIcon level={n.level} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium">{n.title}</p>
                  {!n.read && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                </div>
                {n.message && <p className="mt-0.5 text-sm text-muted-foreground">{n.message}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  {n.server_id ? (
                    <Link href={`/servers/${n.server_id}`} className="hover:text-foreground">
                      {n.server_name ?? n.server_id}
                    </Link>
                  ) : null}
                  {n.server_id ? " · " : ""}
                  {timeAgo(n.created_at)}
                </p>
              </div>
              <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                {!n.read && (
                  <button
                    onClick={() => markRead(n)}
                    className="cursor-pointer rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    aria-label="Mark as read"
                    title="Mark as read"
                  >
                    <CheckCheck className="size-4" />
                  </button>
                )}
                <button
                  onClick={() => remove(n)}
                  className="cursor-pointer rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-danger"
                  aria-label="Delete notification"
                  title="Delete"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
