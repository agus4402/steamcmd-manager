import Link from "next/link";
import { CircleAlert, CircleCheck } from "lucide-react";
import type { Server } from "@/lib/types";

/** Surfaces servers in an `errored` state with their last error message. */
export default function AlertList({ servers }: { servers: Server[] }) {
  const alerts = servers.filter((s) => s.status === "errored");

  if (alerts.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-card/40 px-3 py-6 text-sm text-muted-foreground">
        <CircleCheck className="size-4 text-success" />
        No active alerts.
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {alerts.map((s) => (
        <li key={s.id}>
          <Link
            href={`/servers/${s.id}`}
            className="block rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5 transition-colors hover:bg-destructive/10"
          >
            <div className="flex items-center gap-2 text-sm font-medium text-danger">
              <CircleAlert className="size-4 shrink-0" />
              {s.name}
            </div>
            {s.error_message && (
              <p className="mt-1 line-clamp-2 pl-6 text-xs text-muted-foreground">{s.error_message}</p>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
