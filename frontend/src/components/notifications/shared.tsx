import { Info, CircleCheck, TriangleAlert, CircleAlert, type LucideIcon } from "lucide-react";
import type { NotificationLevel } from "@/lib/types";
import { cn } from "@/lib/utils";

const LEVEL: Record<NotificationLevel, { icon: LucideIcon; className: string }> = {
  info: { icon: Info, className: "text-info" },
  success: { icon: CircleCheck, className: "text-success" },
  warning: { icon: TriangleAlert, className: "text-warning" },
  error: { icon: CircleAlert, className: "text-danger" },
};

export function NotificationIcon({ level, className }: { level: NotificationLevel; className?: string }) {
  const { icon: Icon, className: tone } = LEVEL[level] ?? LEVEL.info;
  return <Icon className={cn("size-4 shrink-0", tone, className)} />;
}

/** Compact relative time, e.g. "5m ago"; falls back to a date for old items. */
export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
