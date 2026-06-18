"use client";

import * as React from "react";
import { type KeyedMutator } from "swr";
import type { Progress, Server } from "@/lib/types";

export interface ServerCtxValue {
  server: Server;
  mutate: KeyedMutator<Server>;
  liveProgress: Progress | null;
  setLiveProgress: (p: Progress | null) => void;
  pending: Record<string, string>;
  act: (server: Server, action: string) => void;
  del: () => Promise<void>;
}

export const ServerCtx = React.createContext<ServerCtxValue | null>(null);

export function useServerCtx() {
  const ctx = React.useContext(ServerCtx);
  if (!ctx) throw new Error("useServerCtx must be used within a server detail route");
  return ctx;
}
