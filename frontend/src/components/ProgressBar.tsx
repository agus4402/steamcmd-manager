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
        <span className="text-amber-400">{label}…</span>
        <span className="text-neutral-400">
          {hasBytes
            ? `${fmtGB(progress!.downloaded)} / ${fmtGB(progress!.total)} GB · ${pct.toFixed(1)}%`
            : "preparing…"}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-neutral-800">
        <div
          className={`h-full bg-amber-500 transition-all duration-500 ${hasBytes ? "" : "animate-pulse w-1/3"}`}
          style={hasBytes ? { width: `${pct}%` } : undefined}
        />
      </div>
    </div>
  );
}
