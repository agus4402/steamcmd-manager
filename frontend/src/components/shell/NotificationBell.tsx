"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Bell, CheckCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";
import { NotificationIcon, timeAgo } from "@/components/notifications/shared";

export default function NotificationBell() {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const router = useRouter();

  const { data: countData, mutate: mutateCount } = useSWR(
    "notif-unread",
    () => api.notifications.unreadCount(),
    { refreshInterval: 20000 },
  );
  const unread = countData?.count ?? 0;

  // Load recent notifications only while the panel is open.
  const { data, mutate } = useSWR<Notification[]>(
    open ? "notif-recent" : null,
    () => api.notifications.list(false, 8),
  );

  React.useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function open_(n: Notification) {
    setOpen(false);
    if (!n.read) {
      await api.notifications.markRead(n.id);
      mutateCount();
      mutate();
    }
    if (n.server_id) router.push(`/servers/${n.server_id}`);
    else router.push("/notifications");
  }

  async function markAll() {
    await api.notifications.markAllRead();
    mutateCount();
    mutate();
  }

  const items = data ?? [];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex size-9 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        aria-label="Notifications"
        aria-expanded={open}
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-4 text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1 w-80 animate-fade-in overflow-hidden rounded-md border border-border bg-popover shadow-xl">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={markAll}
                className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">No notifications</p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => open_(n)}
                  className={cn(
                    "flex w-full cursor-pointer items-start gap-2.5 border-b border-border px-3 py-2.5 text-left transition-colors last:border-0 hover:bg-accent",
                    !n.read && "bg-primary/5",
                  )}
                >
                  <NotificationIcon level={n.level} className="mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium">{n.title}</p>
                      {!n.read && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                    </div>
                    {n.message && <p className="truncate text-xs text-muted-foreground">{n.message}</p>}
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {n.server_name ? `${n.server_name} · ` : ""}
                      {timeAgo(n.created_at)}
                    </p>
                  </div>
                </button>
              ))
            )}
          </div>

          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-border px-3 py-2 text-center text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            View all
          </Link>
        </div>
      )}
    </div>
  );
}
