"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { ConfigWriteResult } from "@/lib/types";

/** Shared save/restore plumbing for a config file (toasts, conflict handling). */
export function useConfigSave(
  serverId: string,
  path: string,
  onDone: () => Promise<unknown> | void,
) {
  const [saving, setSaving] = useState(false);

  async function run(label: string, fn: () => Promise<ConfigWriteResult>) {
    setSaving(true);
    try {
      const res = await fn();
      toast.success(label, {
        description: res.restarted ? "Server restarted with the new config." : undefined,
      });
      await onDone();
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast.error("The file changed on the server", {
          description: "Someone (or the game) modified it since you opened it. Reload and re-apply.",
        });
      } else {
        toast.error("Could not save", { description: e instanceof ApiError ? e.message : String(e) });
      }
      return false;
    } finally {
      setSaving(false);
    }
  }

  return {
    saving,
    save: (
      body: { content?: string; changes?: Record<string, string>; base_mtime?: number },
      restart: boolean,
    ) => run("Saved", () => api.writeConfigFile(serverId, { path, ...body, restart })),
    restore: (restart: boolean) => {
      if (!confirm("Replace this file with the version before your last save?")) {
        return Promise.resolve(false);
      }
      return run("Previous version restored", () => api.restoreConfigFile(serverId, path, restart));
    },
  };
}
