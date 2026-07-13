"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, Upload, FileSearch } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ImportPreviewItem } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Props {
  serverId: string;
  onClose: () => void;
  onInstalled: () => void;
}

export function ImportModsModal({ serverId, onClose, onInstalled }: Props) {
  const [input, setInput] = useState("");
  const [items, setItems] = useState<ImportPreviewItem[] | null>(null);
  const [unparsed, setUnparsed] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function preview() {
    if (!input.trim()) return;
    setLoading(true);
    try {
      const res = await api.importPreview(serverId, input);
      setItems(res.items);
      setUnparsed(res.unparsed);
      // Pre-select everything installable (not already installed, not missing).
      setSelected(
        new Set(res.items.filter((i) => !i.installed && !i.missing).map((i) => i.item_id)),
      );
    } catch (e) {
      toast.error("Could not parse import", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setLoading(false);
    }
  }

  async function install() {
    const ids = [...selected];
    if (ids.length === 0) return;
    setInstalling(true);
    try {
      const res = await api.importInstall(serverId, input, ids);
      toast.success(`Queued ${res.queued.length} mod${res.queued.length === 1 ? "" : "s"}`);
      onInstalled();
      onClose();
    } catch (e) {
      toast.error("Import failed", {
        description: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setInstalling(false);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setInput(await file.text());
    setItems(null);
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
        <h2 className="text-lg font-semibold">Import mods</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Paste a collection URL/ID, mod URLs, or a list of Workshop IDs (commas, spaces, or
          new lines). A single collection is expanded automatically.
        </p>

        <textarea
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            setItems(null);
          }}
          rows={5}
          placeholder={"123456789, 987654321\nor https://steamcommunity.com/sharedfiles/filedetails/?id=…"}
          className="mt-3 w-full resize-y rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:border-primary"
        />

        <div className="mt-2 flex items-center gap-2">
          <Button variant="secondary" onClick={() => fileRef.current?.click()}>
            <Upload className="size-4" /> Upload .txt
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            onChange={onFile}
          />
          <Button onClick={preview} disabled={loading || !input.trim()}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : <FileSearch className="size-4" />}
            Preview
          </Button>
        </div>

        {unparsed.length > 0 && (
          <p className="mt-3 text-xs text-warning">
            Could not parse: {unparsed.join(", ")}
          </p>
        )}

        {items && (
          <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-lg border border-border">
            {items.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                No mods found in that input.
              </p>
            ) : (
              <ul>
                {items.map((it) => (
                  <li
                    key={it.item_id}
                    className="flex items-center gap-3 border-b border-border px-3 py-2 last:border-0"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(it.item_id)}
                      disabled={it.installed || it.missing}
                      onChange={() => toggle(it.item_id)}
                      className="size-4 shrink-0 accent-primary"
                    />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {it.preview_url ? (
                      <img
                        src={it.preview_url}
                        alt=""
                        className="size-9 shrink-0 rounded border border-border object-cover"
                      />
                    ) : (
                      <div className="size-9 shrink-0 rounded border border-border bg-muted" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm">{it.title || `Item ${it.item_id}`}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {it.item_id}
                        {it.file_size > 0 && ` · ${formatBytes(it.file_size)}`}
                      </div>
                    </div>
                    {it.installed && <span className="text-xs text-success">Installed</span>}
                    {it.missing && <span className="text-xs text-danger">Not found</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={install} disabled={installing || selected.size === 0}>
            {installing && <Loader2 className="size-4 animate-spin" />}
            Install {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </div>
      </div>
    </div>
  );
}
