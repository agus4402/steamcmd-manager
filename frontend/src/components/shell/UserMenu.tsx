"use client";

import useSWR from "swr";
import { useRouter } from "next/navigation";
import { User, LogOut, Settings } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { DropdownMenu } from "@/components/ui/dropdown-menu";

export default function UserMenu() {
  const router = useRouter();
  const { data } = useSWR<{ username: string }>("me", () => api.me(), {
    shouldRetryOnError: false,
  });
  const username = data?.username ?? "Account";

  return (
    <DropdownMenu
      align="end"
      trigger={
        <span className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-sm transition-colors hover:bg-accent">
          <span className="flex size-6 items-center justify-center rounded-full bg-primary/15 text-primary">
            <User className="size-3.5" />
          </span>
          <span className="hidden max-w-28 truncate sm:inline">{username}</span>
        </span>
      }
      items={[
        { label: "Settings", icon: <Settings className="size-4" />, href: "/settings" },
        {
          label: "Sign out",
          icon: <LogOut className="size-4" />,
          danger: true,
          separatorBefore: true,
          onSelect: () => {
            setToken(null);
            router.push("/login");
          },
        },
      ]}
    />
  );
}
