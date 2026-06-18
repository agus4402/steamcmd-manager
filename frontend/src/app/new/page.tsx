"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { CircleCheck, Users, UserCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Server, Template } from "@/lib/types";
import PageHeader from "@/components/common/PageHeader";
import { ErrorState } from "@/components/common/states";
import { Card, CardContent } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const STEPS = ["Template", "Configure", "Done"];

export default function NewServer() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selected, setSelected] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<Server | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .templates()
      .then(setTemplates)
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "could not load templates"));
  }, []);

  function pick(t: Template) {
    setSelected(t);
    setVars(Object.fromEntries(t.variables.map((v) => [v.key, v.default])));
    setStep(2);
  }

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    try {
      const server = await api.create({ template_id: selected.id, name, variables: vars });
      setCreated(server);
      setStep(3);
      toast.success(`Created ${server.name}`);
    } catch (e) {
      toast.error("Failed to create server", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="New server" description="Create a game server from a template" />

      {/* Stepper */}
      <div className="mb-6 flex items-center gap-2">
        {STEPS.map((label, i) => {
          const n = (i + 1) as 1 | 2 | 3;
          const done = step > n;
          const active = step === n;
          return (
            <div key={label} className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full text-xs font-semibold",
                  active && "bg-primary text-primary-foreground",
                  done && "bg-primary/15 text-primary",
                  !active && !done && "bg-secondary text-muted-foreground",
                )}
              >
                {done ? <CircleCheck className="size-4" /> : n}
              </span>
              <span className={cn("text-sm", active ? "font-medium" : "text-muted-foreground")}>{label}</span>
              {i < STEPS.length - 1 && <span className="mx-1 h-px w-8 bg-border" />}
            </div>
          );
        })}
      </div>

      {loadError && <ErrorState message={loadError} />}

      {/* Step 1: choose template */}
      {step === 1 && !loadError && (
        <div className="grid gap-3">
          {templates === null
            ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)
            : templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => pick(t)}
                  className="cursor-pointer rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/50"
                >
                  <div className="flex items-center justify-between">
                    <div className="font-medium">{t.name}</div>
                    <Badge variant={t.anonymous_login ? "info" : "warning"}>
                      {t.anonymous_login ? <Users className="size-3" /> : <UserCheck className="size-3" />}
                      {t.anonymous_login ? "Anonymous" : "Login"}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    app {t.app_id} · {t.ports.map((p) => `${p.default}/${p.protocol}`).join(", ")}
                  </div>
                </button>
              ))}
        </div>
      )}

      {/* Step 2: configure */}
      {step === 2 && selected && (
        <Card>
          <CardContent className="grid gap-4 pt-5">
            <div>
              <Label htmlFor="server-name">Server name</Label>
              <Input
                id="server-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-cs2-server"
              />
              <p className="mt-1 text-xs text-muted-foreground">Letters, numbers, - and _ only.</p>
            </div>

            {selected.variables.map((v) => (
              <div key={v.key}>
                <Label htmlFor={`var-${v.key}`}>{v.key}</Label>
                <Input
                  id={`var-${v.key}`}
                  value={vars[v.key] ?? ""}
                  onChange={(e) => setVars({ ...vars, [v.key]: e.target.value })}
                  placeholder={v.key.toUpperCase().endsWith("PASSWORD") ? "(auto-generated if empty)" : ""}
                />
              </div>
            ))}

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button onClick={submit} disabled={!name || submitting}>
                {submitting ? "Creating…" : "Create server"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: success */}
      {step === 3 && created && (
        <Card className="border-primary/30">
          <CardContent className="pt-5">
            <div className="flex items-center gap-2 font-medium text-primary">
              <CircleCheck className="size-5" /> Server created
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{created.name}</p>

            <p className="mt-4 text-xs uppercase tracking-wider text-muted-foreground">Assigned ports (host)</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {created.ports.map((p) => (
                <span
                  key={`${p.protocol}-${p.host_port}`}
                  className="rounded bg-secondary px-2.5 py-1 font-mono text-sm"
                >
                  {p.host_port}/{p.protocol}
                </span>
              ))}
            </div>

            {Object.entries(created.variables).length > 0 && (
              <div className="mt-4 grid gap-1 text-xs text-muted-foreground">
                {Object.entries(created.variables).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-foreground">{k}</span> = {v || "—"}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-5 flex gap-2">
              <Button onClick={() => router.push(`/servers/${created.id}`)}>Open & install</Button>
              <Link href="/servers" className={buttonVariants({ variant: "outline" })}>
                All servers
              </Link>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
