import { Download, Hourglass } from "lucide-react";
import type { ModProgress, WorkshopProgress } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";

function Bar({
  fraction,
  indeterminate = false,
  tone = "warning",
}: {
  fraction: number;
  indeterminate?: boolean;
  tone?: "warning" | "success" | "danger";
}) {
  const color = { warning: "bg-warning", success: "bg-success", danger: "bg-danger" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          color,
          indeterminate && "w-1/3 animate-pulse",
        )}
        style={indeterminate ? undefined : { width: `${Math.round(fraction * 100)}%` }}
      />
    </div>
  );
}

/** Overall progress of the server's download run, above the mod grid. */
export function RunProgress({ progress }: { progress: WorkshopProgress }) {
  const { total, done, failed, bytes_total, bytes_done } = progress;
  const finished = done + failed;
  const fraction = bytes_total > 0 ? bytes_done / bytes_total : total ? finished / total : 0;
  const Icon = progress.waiting_for_other ? Hourglass : Download;
  const batch = Object.keys(progress.items).length;

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
        <span className="flex items-center gap-2 font-medium">
          <Icon className="size-4 text-warning" />
          {progress.waiting_for_other
            ? "Queued behind another server's downloads"
            : "Downloading mods"}
          <span className="font-normal text-muted-foreground">
            {finished} / {total}
            {failed > 0 && <span className="text-danger"> · {failed} failed</span>}
          </span>
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          {bytes_total > 0 && `${formatBytes(bytes_done)} / ${formatBytes(bytes_total)} · `}
          {Math.floor(fraction * 100)}%
        </span>
      </div>
      <Bar fraction={fraction} />
      {batch > 0 && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Current batch: {batch} mod{batch === 1 ? "" : "s"}
          {progress.attempt > 0 &&
            ` · steamcmd attempt ${progress.attempt}/${progress.max_attempts}`}
          {progress.attempt > 1 && " (resuming the ones Steam cut off)"}
        </p>
      )}
    </div>
  );
}

const STATE_LABEL: Record<ModProgress["state"], string> = {
  starting: "Starting steamcmd…",
  waiting: "Waiting its turn in the batch",
  downloading: "Downloading",
  retrying: "Interrupted, will resume",
  downloaded: "Copying into the server…",
  ok: "Done",
  failed: "Failed",
};

/** One mod's bar while its batch is downloading. */
export function ModProgressBar({ progress }: { progress: ModProgress }) {
  const { state, bytes, total, fraction } = progress;
  const tone = state === "ok" ? "success" : state === "failed" ? "danger" : "warning";
  const showBytes = state === "downloading" || state === "retrying" || state === "waiting";
  return (
    <div className="mt-1.5">
      <div className="mb-0.5 flex justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="truncate">{STATE_LABEL[state]}</span>
        <span className="shrink-0 font-mono">
          {showBytes && bytes > 0 && (total > 0 ? `${formatBytes(bytes)} / ${formatBytes(total)}` : formatBytes(bytes))}
          {showBytes && total > 0 && ` · ${Math.floor(fraction * 100)}%`}
        </span>
      </div>
      <Bar
        fraction={fraction}
        tone={tone}
        indeterminate={state === "starting" || state === "downloaded" || (state === "downloading" && total === 0)}
      />
    </div>
  );
}
