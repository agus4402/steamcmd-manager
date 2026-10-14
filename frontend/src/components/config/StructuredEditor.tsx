"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Code2, Lock, RotateCcw, Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ConfigField, ConfigFileContent, ConfigFileInfo } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { EmptyState, ErrorState } from "@/components/common/states";
import { cn } from "@/lib/utils";
import { RawEditor } from "./RawEditor";
import { SaveBar } from "./SaveBar";
import { useConfigSave } from "./useConfigSave";

const ALL = "__all__";
/** Every section added by a mod (deep-linked from the Workshop load order). */
const MODS = "__mods__";
const selectCls =
  "h-9 rounded-md border border-border bg-background px-2 text-sm outline-none focus:border-primary";

interface StructuredEditorProps {
  serverId: string;
  file: ConfigFileInfo;
  running: boolean;
  /** Pre-selected section (e.g. a mod's sandbox table from the Workshop tab). */
  initialSection?: string | null;
  onSaved?: () => void;
}

/** Form generated from the game's own commented config (ini / PZ sandbox). */
export function StructuredEditor({
  serverId,
  file,
  running,
  initialSection,
  onSaved,
}: StructuredEditorProps) {
  const [rawMode, setRawMode] = useState(false);
  const { data, error, isLoading, mutate } = useSWR<ConfigFileContent>(
    ["config-file", serverId, file.path],
    () => api.configFile(serverId, file.path),
    { revalidateOnFocus: false },
  );
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [section, setSection] = useState<string>(initialSection ?? ALL);
  const { saving, save, restore } = useConfigSave(serverId, file.path, async () => {
    await mutate();
    setEdits({});
    onSaved?.();
  });

  useEffect(() => {
    if (initialSection) setSection(initialSection);
  }, [initialSection]);

  const fields = useMemo(() => data?.fields ?? [], [data]);
  const sections = useMemo(() => {
    const seen = new Map<string, boolean>();
    for (const f of fields) if (!seen.has(f.section)) seen.set(f.section, f.mod);
    return [...seen.entries()].map(([name, mod]) => ({ name, mod }));
  }, [fields]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return fields.filter(
      (f) =>
        (section === ALL || (section === MODS ? f.mod : f.section === section)) &&
        (!q ||
          f.path.toLowerCase().includes(q) ||
          (f.description ?? "").toLowerCase().includes(q) ||
          f.enum.some((o) => o.label.toLowerCase().includes(q))),
    );
  }, [fields, query, section]);

  if (rawMode) {
    return (
      <div className="flex flex-col gap-3">
        <div>
          <Button variant="ghost" size="sm" onClick={() => setRawMode(false)}>
            ← Back to form
          </Button>
        </div>
        <RawEditor
          serverId={serverId}
          path={file.path}
          running={running}
          hasBackup={file.has_backup}
          onSaved={() => {
            mutate();
            onSaved?.();
          }}
        />
      </div>
    );
  }

  if (!file.exists) {
    return (
      <EmptyState
        title="File not generated yet"
        hint="Start the server once so the game creates it, then come back to edit it."
      />
    );
  }
  if (isLoading) return <Skeleton className="h-[60vh] w-full" />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof ApiError ? error.message : String(error)}
        onRetry={() => mutate()}
      />
    );
  }

  const changes = Object.fromEntries(
    Object.entries(edits).filter(([p, v]) => fields.find((f) => f.path === p)?.value !== v),
  );
  const changed = Object.keys(changes).length;
  const grouped = new Map<string, ConfigField[]>();
  for (const f of visible) grouped.set(f.section, [...(grouped.get(f.section) ?? []), f]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${fields.length} settings…`}
            className="pl-8"
            aria-label="Search settings"
          />
        </div>
        {sections.length > 1 && (
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className={selectCls}
            aria-label="Section"
          >
            <option value={ALL}>All sections</option>
            {sections.some((s) => s.mod) && <option value={MODS}>All mod sections</option>}
            {sections.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
                {s.mod ? " (mod)" : ""}
              </option>
            ))}
          </select>
        )}
        <Button variant="outline" size="sm" onClick={() => setRawMode(true)}>
          <Code2 /> Edit as text
        </Button>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          title={section === MODS && !query ? "No mod options" : "No settings match"}
          hint={
            section === MODS && !query
              ? "None of the installed mods add sandbox options (they appear here after the server starts with them)."
              : "Try another search or section."
          }
        />
      ) : (
        [...grouped.entries()].map(([name, list]) => (
          <section key={name} className="rounded-lg border border-border">
            <h3 className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold">
              {name}
              {list[0]?.mod && <Badge variant="info">mod</Badge>}
            </h3>
            <div className="divide-y divide-border">
              {list.map((f) => (
                <FieldRow
                  serverId={serverId}
                  key={f.path}
                  field={f}
                  value={edits[f.path] ?? f.value}
                  onChange={(v) => setEdits((e) => ({ ...e, [f.path]: v }))}
                  onReset={() =>
                    setEdits((e) => {
                      const next = { ...e };
                      delete next[f.path];
                      return next;
                    })
                  }
                />
              ))}
            </div>
          </section>
        ))
      )}

      <SaveBar
        dirty={changed > 0}
        saving={saving}
        running={running}
        hasBackup={file.has_backup}
        summary={`${changed} unsaved change${changed === 1 ? "" : "s"}`}
        onSave={(restart) => save({ changes, base_mtime: data.mtime }, restart)}
        onDiscard={() => setEdits({})}
        onRestore={() => restore(running)}
      />
    </div>
  );
}

function FieldRow({
  serverId,
  field: f,
  value,
  onChange,
  onReset,
}: {
  serverId: string;
  field: ConfigField;
  value: string;
  onChange: (v: string) => void;
  onReset: () => void;
}) {
  const id = `cfg-${f.path}`;
  const modified = value !== f.value;
  const key = f.path.includes(".") ? f.path.slice(f.path.lastIndexOf(".") + 1) : f.path;
  const defaultLabel =
    f.default != null ? (f.enum.find((o) => o.value === f.default)?.label ?? f.default) : null;

  let control: React.ReactNode;
  if (f.type === "bool") {
    control = (
      <Switch
        id={id}
        checked={value === "true"}
        onCheckedChange={(c) => onChange(c ? "true" : "false")}
        disabled={f.managed}
        aria-label={key}
      />
    );
  } else if (f.enum.length > 0) {
    control = (
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={f.managed}
        className={cn(selectCls, "w-full sm:w-56")}
      >
        {f.enum.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={f.managed}
        inputMode={f.type === "string" ? undefined : "decimal"}
        className={cn(f.type === "string" ? "w-full sm:w-80" : "w-full sm:w-40")}
      />
    );
  }

  return (
    <div className={cn("grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center", modified && "bg-primary/5")}>
      <div className="min-w-0">
        <label htmlFor={id} className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <span className="font-mono">{key}</span>
          {modified && <Badge variant="warning">modified</Badge>}
          {f.managed && <ManagedBy serverId={serverId} where={f.managed_by} />}
        </label>
        {f.description && <p className="mt-0.5 text-xs text-muted-foreground">{f.description}</p>}
        {(defaultLabel || f.min != null) && (
          <p className="mt-0.5 text-[11px] text-muted-foreground/80">
            {f.min != null && `Range ${f.min} – ${f.max}`}
            {f.min != null && defaultLabel && " · "}
            {defaultLabel && `Default ${defaultLabel}`}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1">
        {control}
        {modified && (
          <Button variant="ghost" size="icon" onClick={onReset} aria-label={`Reset ${key}`}>
            <RotateCcw />
          </Button>
        )}
      </div>
    </div>
  );
}

/** "Managed by the panel" note linking to where the value is actually edited. */
function ManagedBy({ serverId, where }: { serverId: string; where: string | null }) {
  const [kind, variable] = (where ?? "variables").split(":");
  const target =
    kind === "workshop"
      ? { href: `/servers/${serverId}/workshop`, label: "Workshop → Load order" }
      : kind === "network"
        ? { href: `/servers/${serverId}/network`, label: "the server's ports (Network)" }
        : {
            href: `/servers/${serverId}/config?file=variables`,
            label: variable ? `Variables → ${variable}` : "Variables",
          };
  return (
    <span className="inline-flex items-center gap-1 text-xs font-normal text-muted-foreground">
      <Lock className="size-3" /> Managed by the panel ·
      <Link href={target.href} className="text-info hover:underline">
        {target.label}
      </Link>
    </span>
  );
}
