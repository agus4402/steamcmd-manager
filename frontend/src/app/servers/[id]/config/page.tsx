"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { ConfigFilesList } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { FilesBrowser } from "@/components/config/FilesBrowser";
import { RawEditor } from "@/components/config/RawEditor";
import { StructuredEditor } from "@/components/config/StructuredEditor";
import { cn } from "@/lib/utils";
import { useServerCtx } from "../server-context";

const VARIABLES = "variables";
const FILES = "files";

export default function ServerConfigPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <ConfigTabs />
    </Suspense>
  );
}

/**
 * Config tab: panel variables + the game's own config files declared by the
 * template (form or raw), and a raw browser for config dirs (mods' configs).
 * `?file=<path|variables|files>&section=<name>` deep-links into a sub-tab.
 */
function ConfigTabs() {
  const { server } = useServerCtx();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data, error, isLoading, mutate } = useSWR<ConfigFilesList>(
    ["config-files", server.id],
    () => api.configFiles(server.id),
    { revalidateOnFocus: false },
  );

  const tab = params.get("file") ?? VARIABLES;
  const section = params.get("section");
  const running = server.status === "running";

  function select(next: string) {
    const qs = new URLSearchParams({ file: next });
    router.replace(`${pathname}?${qs}`, { scroll: false });
  }

  const tabs = [
    { id: VARIABLES, label: "Variables" },
    ...(data?.files ?? []).map((f) => ({ id: f.path, label: f.label })),
    ...(data && data.dirs.length > 0 ? [{ id: FILES, label: "Files" }] : []),
  ];
  const file = data?.files.find((f) => f.path === tab);

  return (
    <div className="flex flex-col gap-5">
      <div role="tablist" aria-label="Config" className="flex gap-1 overflow-x-auto border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => select(t.id)}
            className={cn(
              "shrink-0 border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t.id
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === VARIABLES ? (
        <VariablesEditor />
      ) : isLoading ? (
        <Skeleton className="h-[60vh] w-full" />
      ) : error || !data ? (
        <ErrorState
          message={error instanceof ApiError ? error.message : "Could not load config files"}
          onRetry={() => mutate()}
        />
      ) : tab === FILES ? (
        <FilesBrowser
          serverId={server.id}
          tree={data.tree}
          dirs={data.dirs}
          running={running}
          onSaved={() => mutate()}
        />
      ) : !file ? (
        <EmptyState title="Unknown file" hint="Pick one of the tabs above." />
      ) : file.format === "text" ? (
        file.exists ? (
          <RawEditor
            serverId={server.id}
            path={file.path}
            running={running}
            hasBackup={file.has_backup}
            onSaved={() => mutate()}
          />
        ) : (
          <EmptyState
            title="File not generated yet"
            hint="Start the server once so the game creates it, then come back to edit it."
          />
        )
      ) : (
        <StructuredEditor
          key={file.path}
          serverId={server.id}
          file={file}
          running={running}
          initialSection={section}
          onSaved={() => mutate()}
        />
      )}
    </div>
  );
}

/** Panel-level template variables (startup flags + values the prestart hook writes). */
function VariablesEditor() {
  const { server, mutate } = useServerCtx();
  const [vars, setVars] = useState<Record<string, string>>(server.variables);
  const [saving, setSaving] = useState(false);

  // Re-seed if the server's variables change underneath us (e.g. first load).
  useEffect(() => {
    setVars(server.variables);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [server.id]);

  const keys = Object.keys(vars);

  async function save() {
    setSaving(true);
    try {
      await api.patch(server.id, { variables: vars });
      toast.success("Configuration saved", { description: "Changes apply on next start." });
      await mutate();
    } catch (e) {
      toast.error("Failed to save", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  if (keys.length === 0) {
    return <EmptyState title="No variables" hint="This template doesn't expose any editable variables." />;
  }

  return (
    <Card className="max-w-2xl">
      <CardContent className="grid gap-4 pt-5">
        {keys.map((k) => (
          <div key={k}>
            <Label htmlFor={`var-${k}`}>{k}</Label>
            <Input
              id={`var-${k}`}
              value={vars[k]}
              onChange={(e) => setVars({ ...vars, [k]: e.target.value })}
            />
          </div>
        ))}
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
          <p className="text-xs text-muted-foreground">Changes apply on next start.</p>
        </div>
      </CardContent>
    </Card>
  );
}
