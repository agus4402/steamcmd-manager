"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Server } from "@/lib/types";

const LABELS: Record<string, string> = {
  "": "Dashboard",
  servers: "Servers",
  new: "New server",
  templates: "Templates",
  schedule: "Schedule",
  notifications: "Notifications",
  settings: "Settings",
  console: "Console",
  config: "Config",
  metrics: "Metrics",
  workshop: "Workshop",
  backups: "Backups",
  overview: "Overview",
};

interface Crumb {
  label: string;
  href: string;
}

export default function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  // Resolve a server id segment to its name (cached by SWR; harmless elsewhere).
  const serverId = segments[0] === "servers" && segments[1] && segments[1] !== "new" ? segments[1] : null;
  const { data: server } = useSWR<Server>(serverId ? ["server", serverId] : null, () =>
    api.server(serverId as string),
  );

  const crumbs: Crumb[] = [{ label: "Dashboard", href: "/" }];
  let acc = "";
  segments.forEach((seg, i) => {
    acc += `/${seg}`;
    let label = LABELS[seg] ?? seg;
    if (i === 1 && serverId === seg) label = server?.name ?? seg;
    crumbs.push({ label, href: acc });
  });

  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={c.href} className="flex min-w-0 items-center gap-1">
            {i > 0 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />}
            {last ? (
              <span className="truncate font-medium text-foreground">{c.label}</span>
            ) : (
              <Link href={c.href} className="truncate text-muted-foreground transition-colors hover:text-foreground">
                {c.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
