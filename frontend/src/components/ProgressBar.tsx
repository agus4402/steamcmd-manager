import type { Progress } from "@/lib/types";

function fmtGB(bytes: number): string {
  return (bytes / 1e9).toFixed(2);
}

/**
 * Install/download progress. `progress` may be null while the install container
 * is starting (before steamcmd emits its first progress line) — we still show
 * an indeterminate "preparing…" state so the user gets feedback immediately.
 */
export default function ProgressBar({
  progress,
  label = "Installing",
}: {
  progress: Progress | null;
  label?: string;
}) {
  const pct = progress ? Math.min(100, Math.max(0, progress.percent)) : 0;
  const hasBytes = progress && progress.total > 0;

  return (
    <div className="w-full">
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-medium text-warning">{label}…</span>
        <span className="font-mono text-muted-foreground">
          {hasBytes
            ? `${fmtGB(progress!.downloaded)} / ${fmtGB(progress!.total)} GB · ${pct.toFixed(1)}%`
            : "preparing…"}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={`h-full rounded-full bg-warning transition-all duration-500 ${hasBytes ? "" : "w-1/3 animate-pulse"}`}
          style={hasBytes ? { width: `${pct}%` } : undefined}
        />
      </div>
    </div>
  );
}
