import {
  LayoutDashboard,
  Server,
  LayoutTemplate,
  Clock,
  Bell,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Routes that aren't backed by an API yet — shown with a "soon" hint. */
  soon?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Global (app-level) navigation, grouped for visual hierarchy in the sidebar. */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/", icon: LayoutDashboard },
      { label: "Servers", href: "/servers", icon: Server },
      { label: "Templates", href: "/templates", icon: LayoutTemplate },
    ],
  },
  {
    label: "Automation",
    items: [
      { label: "Schedule", href: "/schedule", icon: Clock, soon: true },
      { label: "Notifications", href: "/notifications", icon: Bell, soon: true },
    ],
  },
  {
    label: "System",
    items: [{ label: "Settings", href: "/settings", icon: Settings }],
  },
];

export interface ServerNavItem {
  /** URL segment appended to /servers/[id] (empty string = overview/index). */
  segment: string;
  label: string;
  soon?: boolean;
}

/** Per-server (detail) sub-navigation. */
export const SERVER_NAV: ServerNavItem[] = [
  { segment: "", label: "Overview" },
  { segment: "console", label: "Console" },
  { segment: "config", label: "Config" },
  { segment: "metrics", label: "Metrics" },
  { segment: "workshop", label: "Workshop", soon: true },
  { segment: "schedule", label: "Schedule", soon: true },
  { segment: "backups", label: "Backups" },
  { segment: "settings", label: "Settings" },
];
