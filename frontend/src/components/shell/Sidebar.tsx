"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeft, Boxes } from "lucide-react";
import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onMobileClose,
}: {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={onMobileClose}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 flex flex-col border-r border-border bg-sidebar transition-[width,transform] duration-200",
          collapsed ? "w-16" : "w-60",
          "md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Brand */}
        <div className={cn("flex h-14 items-center gap-2 border-b border-border px-4", collapsed && "justify-center px-0")}>
          <Boxes className="size-6 shrink-0 text-primary" />
          {!collapsed && <span className="truncate font-semibold tracking-tight">SteamCMD</span>}
        </div>

        {/* Nav groups */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-4">
              {!collapsed && (
                <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </p>
              )}
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onMobileClose}
                        title={collapsed ? item.label : undefined}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                          collapsed && "justify-center px-0",
                          active
                            ? "bg-primary/15 text-primary"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                        )}
                      >
                        <Icon className="size-5 shrink-0" />
                        {!collapsed && (
                          <span className="flex flex-1 items-center justify-between truncate">
                            {item.label}
                            {item.soon && (
                              <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-[9px] font-semibold uppercase text-muted-foreground">
                                soon
                              </span>
                            )}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Collapse toggle (desktop only) */}
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            "hidden h-12 cursor-pointer items-center gap-3 border-t border-border px-4 text-sm text-muted-foreground transition-colors hover:text-foreground md:flex",
            collapsed && "justify-center px-0",
          )}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeft className="size-5" /> : <PanelLeftClose className="size-5" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </aside>
    </>
  );
}
