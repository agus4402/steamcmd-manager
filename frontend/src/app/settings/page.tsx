"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { SlidersHorizontal, Network, ShieldCheck, Plug, LogOut, ArrowRight } from "lucide-react";
import { setToken } from "@/lib/api";
import PageHeader from "@/components/common/PageHeader";
import { ComingSoon } from "@/components/common/states";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";

export default function SettingsPage() {
  const router = useRouter();

  const sections = [
    {
      icon: SlidersHorizontal,
      title: "Defaults",
      description: "Default behaviors for new servers (auto-start, auto-update, install-only).",
      backend: "Persist a global settings record applied at server creation.",
    },
    {
      icon: Network,
      title: "Network",
      description: "Port pool range and network configuration.",
      backend: "Expose the backend PORT_POOL_START/END via a settings endpoint.",
    },
    {
      icon: ShieldCheck,
      title: "Security",
      description: "Credential storage, session policy and access controls.",
      backend: "Add a settings/security model; multi-user/roles require an auth overhaul.",
    },
  ];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Settings"
        description="Global panel configuration"
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setToken(null);
              router.push("/login");
            }}
          >
            <LogOut className="size-4" /> Sign out
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="transition-colors hover:border-primary/40">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Plug className="size-4 text-muted-foreground" /> Integrations
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              Connect external services like Playit.gg tunnels, and more.
            </p>
            <Link
              href="/settings/integrations"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              Manage <ArrowRight className="size-4" />
            </Link>
          </CardContent>
        </Card>

        {sections.map((s) => (
          <Card key={s.title}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <s.icon className="size-4 text-muted-foreground" /> {s.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ComingSoon title={s.title} description={s.description} backend={s.backend} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
