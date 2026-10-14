"use client";

import { useState } from "react";
import { FileText, Folder } from "lucide-react";
import type { ConfigTreeEntry } from "@/lib/types";
import { EmptyState } from "@/components/common/states";
import { cn, formatBytes } from "@/lib/utils";
import { RawEditor } from "./RawEditor";

interface FilesBrowserProps {
  serverId: string;
  tree: ConfigTreeEntry[];
  dirs: string[];
  running: boolean;
  onSaved: () => void;
}

/** Raw access to every file under the template's config dirs (e.g. mod configs). */
export function FilesBrowser({ serverId, tree, dirs, running, onSaved }: FilesBrowserProps) {
  const files = tree.filter((e) => e.type === "file");
  const [selected, setSelected] = useState<string | null>(files[0]?.path ?? null);
  const current = files.find((f) => f.path === selected);

  if (files.length === 0) {
    return (
      <EmptyState
        title="No config files yet"
        hint={`Files appear here once the game (or its mods) create them in ${dirs.join(", ")}.`}
      />
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <nav aria-label="Config files" className="max-h-[70vh] overflow-auto rounded-lg border border-border p-1">
        {tree.map((e) => {
          const depth = e.path.split("/").length - 1;
          const name = e.path.slice(e.path.lastIndexOf("/") + 1);
          if (e.type === "dir") {
            return (
              <div
                key={e.path}
                className="flex items-center gap-1.5 px-2 py-1 text-xs font-semibold text-muted-foreground"
                style={{ paddingLeft: depth * 10 }}
              >
                <Folder className="size-3.5 shrink-0" />
                <span className="truncate">{name}</span>
              </div>
            );
          }
          return (
            <button
              key={e.path}
              type="button"
              onClick={() => setSelected(e.path)}
              aria-current={selected === e.path}
              className={cn(
                "flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-sm transition-colors hover:bg-accent",
                selected === e.path && "bg-accent text-foreground",
              )}
              style={{ paddingLeft: depth * 10 }}
              title={e.path}
            >
              <FileText className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{name}</span>
              <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{formatBytes(e.size)}</span>
            </button>
          );
        })}
      </nav>
      <div className="min-w-0">
        {current && (
          <>
            <p className="mb-2 truncate font-mono text-xs text-muted-foreground">{current.path}</p>
            <RawEditor
              serverId={serverId}
              path={current.path}
              running={running}
              hasBackup={current.has_backup}
              onSaved={onSaved}
            />
          </>
        )}
      </div>
    </div>
  );
}
