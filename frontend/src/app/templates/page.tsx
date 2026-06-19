"use client";

import Link from "next/link";
import useSWR from "swr";
import { Plus, LayoutTemplate, Users, UserCheck, Ban } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Template } from "@/lib/types";
import PageHeader from "@/components/common/PageHeader";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";

export default function TemplatesPage() {
  const { data: templates, error, isLoading } = useSWR<Template[]>("templates", () => api.templates());
  const list = templates ?? [];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Templates"
        description="Game templates available for new servers"
        actions={
          <Link href="/new" className={buttonVariants()}>
            <Plus className="size-4" /> New server
          </Link>
        }
      />

      {error ? (
        <ErrorState message={error instanceof ApiError ? error.message : "Could not load templates"} />
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState icon={LayoutTemplate} title="No templates" hint="No game templates are configured on the server." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((t) => (
            <Card key={t.id} className="flex flex-col">
              <CardContent className="flex flex-1 flex-col gap-3 pt-5">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-medium">{t.name}</h3>
                    <p className="text-xs text-muted-foreground">app {t.app_id}</p>
                  </div>
                  {t.supported ? (
                    <Badge variant={t.anonymous_login ? "info" : "warning"}>
                      {t.anonymous_login ? <Users className="size-3" /> : <UserCheck className="size-3" />}
                      {t.anonymous_login ? "Anonymous" : "Login"}
                    </Badge>
                  ) : (
                    <Badge variant="danger">
                      <Ban className="size-3" /> Not supported
                    </Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {t.ports.map((p) => (
                    <span
                      key={`${p.protocol}-${p.default}`}
                      className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-muted-foreground"
                    >
                      {p.default}/{p.protocol}
                    </span>
                  ))}
                </div>
                {!t.supported && t.unsupported_reason && (
                  <p className="text-xs text-danger">{t.unsupported_reason}</p>
                )}
                {t.supported ? (
                  <Link
                    href="/new"
                    className={`${buttonVariants({ variant: "outline", size: "sm" })} mt-auto`}
                  >
                    Create from template
                  </Link>
                ) : (
                  <span
                    className={`${buttonVariants({ variant: "outline", size: "sm" })} pointer-events-none mt-auto opacity-50`}
                  >
                    Unavailable
                  </span>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
