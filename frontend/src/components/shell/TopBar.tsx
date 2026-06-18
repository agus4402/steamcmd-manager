"use client";

import { Menu, Search } from "lucide-react";
import Breadcrumbs from "./Breadcrumbs";
import HealthBadge from "./HealthBadge";
import UserMenu from "./UserMenu";
import { useCommandPalette } from "./CommandPalette";

export default function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const { setOpen } = useCommandPalette();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur">
      <button
        type="button"
        onClick={onMenuClick}
        className="cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      <div className="min-w-0 flex-1">
        <Breadcrumbs />
      </div>

      {/* Global search trigger */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex cursor-pointer items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent"
        aria-label="Open command palette"
      >
        <Search className="size-4" />
        <span className="hidden md:inline">Search…</span>
        <kbd className="hidden rounded border border-border bg-secondary px-1.5 py-0.5 text-[10px] font-medium md:inline">
          ⌘K
        </kbd>
      </button>

      <HealthBadge />
      <UserMenu />
    </header>
  );
}
