"use client";

import { History, RotateCw, Save, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SaveBarProps {
  dirty: boolean;
  saving: boolean;
  /** Server is running: offer "Save & restart" so the game can't overwrite the edit. */
  running: boolean;
  hasBackup?: boolean;
  onSave: (restart: boolean) => void;
  onDiscard: () => void;
  onRestore?: () => void;
  summary?: string;
}

/** Sticky footer with the save actions shared by the structured and raw editors. */
export function SaveBar({
  dirty,
  saving,
  running,
  hasBackup,
  onSave,
  onDiscard,
  onRestore,
  summary,
}: SaveBarProps) {
  return (
    <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-2 border-t border-border bg-background/95 px-1 py-3 backdrop-blur">
      <p className="mr-auto text-xs text-muted-foreground">
        {dirty
          ? summary ?? "Unsaved changes"
          : running
            ? "The server is running: changes are applied on restart."
            : "Changes apply on the next start."}
      </p>
      {hasBackup && onRestore && (
        <Button variant="ghost" size="sm" onClick={onRestore} disabled={saving}>
          <History /> Restore previous version
        </Button>
      )}
      <Button variant="outline" size="sm" onClick={onDiscard} disabled={!dirty || saving}>
        <Undo2 /> Discard
      </Button>
      {running ? (
        <>
          <Button variant="outline" size="sm" onClick={() => onSave(false)} disabled={!dirty || saving}>
            <Save /> Save only
          </Button>
          <Button size="sm" onClick={() => onSave(true)} disabled={!dirty || saving}>
            <RotateCw /> {saving ? "Saving…" : "Save & restart"}
          </Button>
        </>
      ) : (
        <Button size="sm" onClick={() => onSave(false)} disabled={!dirty || saving}>
          <Save /> {saving ? "Saving…" : "Save"}
        </Button>
      )}
    </div>
  );
}
