"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type { Server, SteamCredentials } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";

// Actions that touch steamcmd and therefore need an account for paid/non-anon apps.
const NEEDS_CREDS = new Set(["install", "update", "start"]);

type Resolver = (value: SteamCredentials | undefined) => void;

interface CredentialsContext {
  /**
   * Resolve Steam credentials for an action. Returns undefined immediately for
   * anonymous servers or actions that don't need credentials; otherwise opens a
   * modal and resolves with the entered credentials (or undefined if cancelled).
   */
  requestSteamCreds: (server: Server, action: string) => Promise<SteamCredentials | undefined>;
}

const Ctx = createContext<CredentialsContext | null>(null);

export function useCredentials(): CredentialsContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCredentials must be used within <CredentialsProvider>");
  return ctx;
}

export function CredentialsProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [serverName, setServerName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [guard, setGuard] = useState("");
  const resolverRef = useRef<Resolver | null>(null);

  const requestSteamCreds = useCallback(
    (server: Server, action: string): Promise<SteamCredentials | undefined> => {
      if (server.anonymous_login || !NEEDS_CREDS.has(action)) {
        return Promise.resolve(undefined);
      }
      setServerName(server.name);
      setUsername("");
      setPassword("");
      setGuard("");
      setOpen(true);
      return new Promise<SteamCredentials | undefined>((resolve) => {
        resolverRef.current = resolve;
      });
    },
    [],
  );

  const settle = useCallback((value: SteamCredentials | undefined) => {
    setOpen(false);
    resolverRef.current?.(value);
    resolverRef.current = null;
  }, []);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username) return;
    settle({ username, password, guard_code: guard || undefined });
  }

  return (
    <Ctx.Provider value={{ requestSteamCreds }}>
      {children}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 animate-fade-in"
          onMouseDown={() => settle(undefined)}
        >
          <form
            onMouseDown={(e) => e.stopPropagation()}
            onSubmit={onSubmit}
            className="w-full max-w-sm animate-zoom-in rounded-xl border border-border bg-popover p-6 shadow-2xl"
          >
            <h2 className="mb-1 text-lg font-semibold">Steam credentials</h2>
            <p className="mb-4 text-xs text-muted-foreground">
              Required to install <span className="text-foreground">{serverName}</span>. Sent over the API
              and encrypted at rest; never stored in the browser.
            </p>

            <div className="mb-3">
              <Label htmlFor="steam-user">Username</Label>
              <Input id="steam-user" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>

            <div className="mb-3">
              <Label htmlFor="steam-pass">Password</Label>
              <Input
                id="steam-pass"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="mb-5">
              <Label htmlFor="steam-guard">
                Steam Guard code <span className="text-muted-foreground/60">(if enabled)</span>
              </Label>
              <Input id="steam-guard" value={guard} onChange={(e) => setGuard(e.target.value)} />
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => settle(undefined)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!username}>
                Continue
              </Button>
            </div>
          </form>
        </div>
      )}
    </Ctx.Provider>
  );
}
