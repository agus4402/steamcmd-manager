"use client";

import * as React from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Server as ServerIcon, Plus, LayoutDashboard, Settings, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Server } from "@/lib/types";

interface PaletteCtx {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const Ctx = React.createContext<PaletteCtx | null>(null);

export function useCommandPalette() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useCommandPalette must be used within CommandPaletteProvider");
  return ctx;
}

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const { data: servers = [] } = useSWR<Server[]>(open ? "servers" : null, () => api.servers());

  // Global Cmd/Ctrl-K shortcut.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const go = React.useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href);
    },
    [router],
  );

  return (
    <Ctx.Provider value={{ open, setOpen }}>
      {children}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[15vh] animate-fade-in"
          onMouseDown={() => setOpen(false)}
        >
          <div
            onMouseDown={(e) => e.stopPropagation()}
            className="w-full max-w-lg animate-zoom-in overflow-hidden rounded-lg border border-border bg-popover shadow-2xl"
          >
            <Command className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground">
              <div className="flex items-center gap-2 border-b border-border px-3">
                <Search className="size-4 text-muted-foreground" />
                <Command.Input
                  autoFocus
                  placeholder="Search servers and actions…"
                  className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>
              <Command.List className="max-h-80 overflow-y-auto p-2">
                <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
                  No results found.
                </Command.Empty>

                <Command.Group heading="Actions">
                  <PaletteItem onSelect={() => go("/")} icon={<LayoutDashboard className="size-4" />}>
                    Go to Dashboard
                  </PaletteItem>
                  <PaletteItem onSelect={() => go("/new")} icon={<Plus className="size-4" />}>
                    Create new server
                  </PaletteItem>
                  <PaletteItem onSelect={() => go("/settings")} icon={<Settings className="size-4" />}>
                    Open Settings
                  </PaletteItem>
                </Command.Group>

                {servers.length > 0 && (
                  <Command.Group heading="Servers">
                    {servers.map((s) => (
                      <PaletteItem
                        key={s.id}
                        value={`server ${s.name} ${s.template_id}`}
                        onSelect={() => go(`/servers/${s.id}`)}
                        icon={<ServerIcon className="size-4" />}
                      >
                        <span className="flex-1">{s.name}</span>
                        <span className="text-xs text-muted-foreground">{s.status}</span>
                      </PaletteItem>
                    ))}
                  </Command.Group>
                )}
              </Command.List>
            </Command>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

function PaletteItem({
  children,
  icon,
  onSelect,
  value,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  onSelect: () => void;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm aria-selected:bg-accent aria-selected:text-accent-foreground"
    >
      {icon}
      {children}
    </Command.Item>
  );
}
