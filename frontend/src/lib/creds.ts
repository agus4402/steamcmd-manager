import type { Server, SteamCredentials } from "./types";

const NEEDS_CREDS = new Set(["install", "update", "start"]);

/**
 * For non-anonymous templates, prompt for Steam credentials (and an optional
 * Steam Guard code) before a steamcmd-touching action. Returns undefined for
 * anonymous servers or actions that don't need credentials.
 *
 * v1 uses window.prompt — simple but functional; credentials are sent over the
 * API (encrypted at rest) and never persisted in the browser.
 */
export function promptSteamCreds(server: Server, action: string): SteamCredentials | undefined {
  if (server.anonymous_login || !NEEDS_CREDS.has(action)) return undefined;
  const username = window.prompt(`Steam username for "${server.name}"`);
  if (!username) return undefined;
  const password = window.prompt("Steam password") ?? "";
  const guard = window.prompt("Steam Guard code (leave blank if none)") ?? "";
  return { username, password, guard_code: guard || undefined };
}
