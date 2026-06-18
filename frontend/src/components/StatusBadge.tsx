import type { ServerStatus } from "@/lib/types";

const STYLES: Record<ServerStatus, string> = {
  running: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  stopped: "bg-neutral-500/15 text-neutral-300 border-neutral-500/30",
  installing: "bg-amber-500/15 text-amber-400 border-amber-500/30 animate-pulse",
  updating: "bg-amber-500/15 text-amber-400 border-amber-500/30 animate-pulse",
  errored: "bg-red-500/15 text-red-400 border-red-500/30",
  created: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

export default function StatusBadge({ status }: { status: ServerStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STYLES[status] ?? STYLES.created}`}
    >
      {status}
    </span>
  );
}
