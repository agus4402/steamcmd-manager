"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ExternalLink, Loader2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Phase = "starting" | "awaiting" | "error";

/**
 * Drives the claim-URL connect flow: starts the flow on the backend, shows the
 * claim link for the user to approve in a new tab, then polls until the
 * integration reports connected (or errors).
 */
export default function ConnectModal({
  provider,
  providerName,
  onClose,
  onConnected,
}: {
  provider: string;
  providerName: string;
  onClose: () => void;
  onConnected: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [claimUrl, setClaimUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const integrationId = useRef<string | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (poll.current) {
      clearInterval(poll.current);
      poll.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        const res = await api.integrations.connect(provider);
        if (cancelled) return;
        integrationId.current = res.integration_id;
        setClaimUrl(res.claim_url);
        setPhase("awaiting");
        if (res.claim_url) window.open(res.claim_url, "_blank", "noopener,noreferrer");

        poll.current = setInterval(async () => {
          if (!integrationId.current) return;
          try {
            const st = await api.integrations.connectStatus(integrationId.current);
            if (st.status === "connected") {
              stopPolling();
              toast.success(`${providerName} connected`);
              onConnected();
            } else if (st.status === "error") {
              stopPolling();
              setError(st.error_message ?? "connection failed");
              setPhase("error");
            }
          } catch {
            /* transient; keep polling */
          }
        }, 2500);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
        setPhase("error");
      }
    }

    start();
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [provider, providerName, onConnected, stopPolling]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Connect {providerName}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="size-4" />
          </Button>
        </div>

        {phase === "starting" && (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Starting connection…
          </div>
        )}

        {phase === "awaiting" && (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              Approve the connection in {providerName}. A new tab should have opened — if not, use the
              link below. This dialog updates automatically once approved.
            </p>
            {claimUrl && (
              <a
                href={claimUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 rounded-md border border-border bg-secondary/50 px-3 py-2 text-sm font-medium hover:bg-secondary"
              >
                <ExternalLink className="size-4" /> Open approval page
              </a>
            )}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> Waiting for approval…
            </div>
          </div>
        )}

        {phase === "error" && (
          <div className="flex flex-col gap-4">
            <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-danger">
              {error}
            </p>
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
