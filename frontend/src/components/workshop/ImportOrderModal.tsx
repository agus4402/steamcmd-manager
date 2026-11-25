"use client";

import { useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ListOrdered, Search, Upload } from "lucide-react";
import type { LoadOrderEntry } from "@/lib/types";
import { applyModPreset, parseModPreset } from "@/lib/modPreset";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

interface Props {
  /** The current (possibly edited) load order. */
  rows: LoadOrderEntry[];
  onClose: () => void;
  /** Receives the reordered rows; they stay unsaved until the user saves. */
  onApply: (rows: LoadOrderEntry[]) => void;
  /** Look up a mod from the list that isn't installed. */
  onSearchMissing?: (modId: string) => void;
}

/**
 * Imports a load order from the list the game exports (Project Zomboid's mod
 * manager: `preset:ModA;ModB;…`), a server ini `Mods=` line, or one id per line.
 */
export function ImportOrderModal({ rows, onClose, onApply, onSearchMissing }: Props) {
  const [text, setText] = useState("");
  const [disableOthers, setDisableOthers] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const parsed = useMemo(() => parseModPreset(text), [text]);
  const result = useMemo(
    () => applyModPreset(rows, parsed.ids, { disableOthers }),
    [rows, parsed.ids, disableOthers],
  );
  const hasInput = parsed.ids.length > 0;

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setText(await file.text());
    e.target.value = "";
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 animate-fade-in"
      onMouseDown={onClose}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-lg animate-zoom-in flex-col rounded-xl border border-border bg-popover p-6 shadow-2xl"
      >
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <ListOrdered className="size-5 text-muted-foreground" /> Import load order
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Paste the mod list exported from the game (e.g.{" "}
          <span className="font-mono text-xs">preset:ModA;ModB;…</span>), a server ini{" "}
          <span className="font-mono text-xs">Mods=</span> line, or one mod id per line. The
          listed mods are enabled in that order.
        </p>

        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="myPreset:ModA;ModB;ModC;"
          className="mt-3 w-full resize-y rounded-md border border-border bg-background px-3 py-2 font-mono text-xs outline-none focus:border-primary"
        />

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
            <Upload className="size-4" /> Upload file
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.ini,text/plain"
            className="hidden"
            onChange={onFile}
          />
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <Switch checked={disableOthers} onCheckedChange={setDisableOthers} />
            Disable mods not in the list
          </label>
        </div>

        {hasInput && (
          <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto rounded-lg border border-border p-3 text-sm">
            {parsed.name && (
              <p className="text-xs text-muted-foreground">
                Preset <span className="font-medium text-foreground">{parsed.name}</span> ·{" "}
                {parsed.ids.length} mod{parsed.ids.length === 1 ? "" : "s"}
              </p>
            )}
            <p className="flex items-center gap-1.5">
              <CheckCircle2 className="size-4 shrink-0 text-success" />
              {result.matched.length} mod{result.matched.length === 1 ? "" : "s"} will be enabled
              in this order
            </p>
            {result.unlisted.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {result.unlisted.length} installed mod{result.unlisted.length === 1 ? "" : "s"} not
                in the list {disableOthers ? "will be disabled" : "keep their state"} and go after
                them.
              </p>
            )}
            {result.missing.length > 0 && (
              <div>
                <p className="flex items-center gap-1.5 text-warning">
                  <AlertTriangle className="size-4 shrink-0" />
                  {result.missing.length} not installed (skipped):
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {result.missing.map((id) => (
                    <li key={id}>
                      {onSearchMissing ? (
                        <button
                          type="button"
                          onClick={() => onSearchMissing(id)}
                          className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 font-mono text-xs hover:border-info hover:text-info"
                          title={`Search ${id} in the Workshop`}
                        >
                          {id} <Search className="size-3" />
                        </button>
                      ) : (
                        <span className="rounded border border-border px-1.5 py-0.5 font-mono text-xs">
                          {id}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex items-center justify-end gap-2">
          <p className="mr-auto text-xs text-muted-foreground">You can review it before saving.</p>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onApply(result.rows);
              onClose();
            }}
            disabled={result.matched.length === 0}
          >
            Apply order
          </Button>
        </div>
      </div>
    </div>
  );
}
