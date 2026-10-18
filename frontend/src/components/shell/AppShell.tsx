"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { CommandPaletteProvider } from "./CommandPalette";

const COLLAPSE_KEY = "steamcmd_sidebar_collapsed";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  // Restore persisted collapse preference on mount.
  React.useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  const toggleCollapsed = React.useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }, []);

  // The login route and the public server control pages render standalone,
  // outside the panel chrome.
  if (pathname === "/login" || pathname.startsWith("/control/")) {
    return <>{children}</>;
  }

  return (
    <CommandPaletteProvider>
      <div className="min-h-screen">
        <Sidebar
          collapsed={collapsed}
          onToggle={toggleCollapsed}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
        />
        <div className={cn("flex min-h-screen flex-col transition-[padding] duration-200", collapsed ? "md:pl-16" : "md:pl-60")}>
          <TopBar onMenuClick={() => setMobileOpen(true)} />
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </CommandPaletteProvider>
  );
}
