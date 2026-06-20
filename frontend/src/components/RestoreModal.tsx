"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Snapshot } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Phase = "confirm" | "restoring" | "done" | "error";
type StepState = "pending" | "active" | "done";

interface Step {
  label: string;
  state: StepState;
}

interface Props {
  snap: Snapshot | null;
  serverId: string;
  onClose: (serverMutated: boolean) => void;
}

export function RestoreModal({ snap, serverId, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("confirm");
  const [startAfter, setStartAfter] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const didStart = useRef(false);

  useEffect(() => {
    if (snap) {
      setPhase("confirm");
      setStartAfter(true);
      setErrorMsg(null);
      setSteps([]);
      didStart.current = false;
    }
  }, [snap?.id]);

  function buildSteps(withStart: boolean): Step[] {
    const base: Step[] = [
      { label: "Stopping server", state: "active" },
      { label: "Restoring files", state: "pending" },
    ];
    if (withStart) base.push({ label: "Starting server", state: "pending" });
    return base;
  }

  async function startRestore() {
    if (!snap || didStart.current) return;
    didStart.current = true;

    const initialSteps = buildSteps(startAfter);
    setPhase("restoring");
    setSteps(initialSteps);

    // Simulate step 1 → 2 transition
    const timer = setTimeout(() => {
      setSteps((prev) =>
        prev.map((s, i) => ({
          ...s,
          state: i === 0 ? "done" : i === 1 ? "active" : "pending",
        })),
      );
    }, 1500);

    try {
      await api.restoreBackup(serverId, snap.id, startAfter);
      clearTimeout(timer);
      setSteps((prev) => prev.map((s) => ({ ...s, state: "done" })));
      setPhase("done");
    } catch (e) {
      clearTimeout(timer);
      setErrorMsg(e instanceof ApiError ? e.message : String(e));
      setPhase("error");
    }
  }

  if (!snap) return null;

  const canClose = phase !== "restoring";

  function handleOverlayClick() {
    if (canClose) onClose(phase === "done");
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 animate-fade-in"
      onMouseDown={handleOverlayClick}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="w-full max-w-sm animate-zoom-in rounded-xl border border-border bg-popover p-6 shadow-2xl"
      >
        {phase === "confirm" && (
          <>
            <h2 className="mb-1 text-lg font-semibold">Restore backup</h2>
            <div className="mb-4 mt-3 rounded-md border border-border bg-muted/40 px-4 py-3 text-sm">
              <p className="font-medium">
                {snap.created_at ? new Date(snap.created_at).toLocaleString() : snap.id}
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                {snap.id} · {formatBytes(snap.size)}
              </p>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              Current server data will be{" "}
              <span className="font-medium text-foreground">permanently replaced</span>. This
              cannot be undone.
            </p>
            <label className="mb-5 flex cursor-pointer items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                checked={startAfter}
                onChange={(e) => setStartAfter(e.target.checked)}
                className="size-4 cursor-pointer accent-primary"
              />
              Start server automatically after restore
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => onClose(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={startRestore}>
                Restore
              </Button>
            </div>
          </>
        )}

        {phase === "restoring" && (
          <>
            <h2 className="mb-4 text-lg font-semibold">Restoring backup</h2>
            <div className="mb-4 flex flex-col gap-4">
              {steps.map((step) => (
                <div key={step.label} className="flex items-center gap-3">
                  <div className="flex size-5 shrink-0 items-center justify-center">
                    {step.state === "done" ? (
                      <span className="flex size-5 items-center justify-center rounded-full bg-green-500/20 text-green-400">
                        <Check className="size-3" strokeWidth={3} />
                      </span>
                    ) : step.state === "active" ? (
                      <Loader2 className="size-4 animate-spin text-primary" />
                    ) : (
                      <span className="size-4 rounded-full border border-border opacity-40" />
                    )}
                  </div>
                  <span
                    className={
                      step.state === "done"
                        ? "text-sm text-green-400"
                        : step.state === "active"
                          ? "text-sm text-foreground"
                          : "text-sm text-muted-foreground/40"
                    }
                  >
                    {step.label}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Do not close this window during restore.</p>
          </>
        )}

        {phase === "done" && (
          <>
            <h2 className="mb-4 text-lg font-semibold">Restore complete</h2>
            <div className="mb-5 flex flex-col gap-4">
              {steps.map((step) => (
                <div key={step.label} className="flex items-center gap-3">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-green-500/20 text-green-400">
                    <Check className="size-3" strokeWidth={3} />
                  </span>
                  <span className="text-sm text-green-400">{step.label}</span>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <Button onClick={() => onClose(true)}>Close</Button>
            </div>
          </>
        )}

        {phase === "error" && (
          <>
            <h2 className="mb-2 text-lg font-semibold">Restore failed</h2>
            <p className="mb-5 text-sm text-destructive">{errorMsg}</p>
            <div className="flex justify-end">
              <Button variant="ghost" onClick={() => onClose(false)}>
                Close
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
