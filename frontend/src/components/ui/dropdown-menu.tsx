"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface MenuItem {
  label: string;
  icon?: React.ReactNode;
  onSelect?: () => void;
  href?: string;
  danger?: boolean;
  disabled?: boolean;
  separatorBefore?: boolean;
}

interface DropdownMenuProps {
  trigger: React.ReactNode;
  items: MenuItem[];
  align?: "start" | "end";
  className?: string;
}

/**
 * Lightweight dropdown: a trigger that toggles an absolutely-positioned menu.
 * Closes on outside click or Escape. Sufficient for the user menu and row actions
 * without pulling in a headless primitive library.
 */
function DropdownMenu({ trigger, items, align = "end", className }: DropdownMenuProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex cursor-pointer items-center"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={cn(
            "absolute z-50 mt-1 min-w-44 animate-fade-in rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-xl",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {items.map((item, i) => {
            const content = (
              <span className="flex items-center gap-2">
                {item.icon}
                {item.label}
              </span>
            );
            const itemClass = cn(
              "flex w-full cursor-pointer items-center rounded-sm px-2.5 py-1.5 text-left text-sm transition-colors",
              item.danger
                ? "text-danger hover:bg-destructive/10"
                : "hover:bg-accent hover:text-accent-foreground",
              item.disabled && "pointer-events-none opacity-40",
            );
            return (
              <React.Fragment key={i}>
                {item.separatorBefore && <div className="my-1 h-px bg-border" />}
                {item.href ? (
                  <a href={item.href} className={itemClass} role="menuitem" onClick={() => setOpen(false)}>
                    {content}
                  </a>
                ) : (
                  <button
                    type="button"
                    role="menuitem"
                    className={itemClass}
                    onClick={() => {
                      setOpen(false);
                      item.onSelect?.();
                    }}
                  >
                    {content}
                  </button>
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

export { DropdownMenu, type MenuItem };
