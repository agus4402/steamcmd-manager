"use client";

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useCredentials } from "@/components/CredentialsModal";
import type { Server } from "@/lib/types";

const ACTION_VERB: Record<string, string> = {
  start: "Starting",
  stop: "Stopping",
  restart: "Restarting",
  install: "Installing",
  update: "Updating",
  reinstall: "Reinstalling",
  delete: "Deleting",
};

/**
 * Shared lifecycle-action handling (credentials prompt + toast feedback + pending
 * state) reused across the dashboard, server list and detail views.
 */
export function useServerActions(onChanged?: () => void | Promise<unknown>) {
  const { requestSteamCreds } = useCredentials();
  // serverId -> action currently running (for per-button loading labels)
  const [pending, setPending] = useState<Record<string, string>>({});

  const setBusy = (id: string, action: string | null) =>
    setPending((p) => {
      const next = { ...p };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });

  const act = useCallback(
    async (server: Server, action: string) => {
      const creds = await requestSteamCreds(server, action);
      setBusy(server.id, action);
      const verb = ACTION_VERB[action] ?? action;
      try {
        await api.action(server.id, action, creds);
        toast.success(`${verb} ${server.name}`);
        await onChanged?.();
      } catch (e) {
        toast.error(`Failed to ${action} ${server.name}`, {
          description: e instanceof ApiError ? e.message : String(e),
        });
      } finally {
        setBusy(server.id, null);
      }
    },
    [requestSteamCreds, onChanged],
  );

  const remove = useCallback(
    async (server: Server) => {
      if (
        !confirm(`Delete "${server.name}"? This removes its container, data volume and frees its ports.`)
      )
        return false;
      setBusy(server.id, "delete");
      try {
        await api.remove(server.id);
        toast.success(`Deleted ${server.name}`);
        await onChanged?.();
        return true;
      } catch (e) {
        toast.error(`Failed to delete ${server.name}`, {
          description: e instanceof ApiError ? e.message : String(e),
        });
        return false;
      } finally {
        setBusy(server.id, null);
      }
    },
    [onChanged],
  );

  return { act, remove, pending };
}
