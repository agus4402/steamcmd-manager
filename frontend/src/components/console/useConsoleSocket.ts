"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { consoleWsUrl } from "@/lib/api";
import {
  MAX_LINES,
  makeLine,
  parseProgress,
  type ConsoleLine,
  type LineSource,
} from "@/lib/consoleBuffer";
import type { Progress } from "@/lib/types";

export type Connection = "connecting" | "live" | "reconnecting" | "offline";

export interface TargetState {
  /** Container whose output is shown: the game server or the steamcmd install. */
  src: "server" | "install" | null;
  status: string;
  /** Commands can be sent (the game container is running). */
  running: boolean;
}

type Frame =
  | { t: "reset" }
  | { t: "lines"; src: "server" | "install"; lines: [string | null, string][] }
  | { t: "source"; src: "server" | "install" }
  | { t: "state"; src: "server" | "install" | null; status: string; running: boolean }
  | { t: "ended"; src: "server" | "install"; exit_code: number | null }
  | { t: "info" | "error"; msg: string }
  | { t: "ping" };

const MIN_RETRY_MS = 1_000;
const MAX_RETRY_MS = 8_000;

/**
 * The console WebSocket. One socket per visit; the backend follows the active
 * container and sends each line once, so the client only reconnects when the
 * connection itself drops — and the server's "reset" frame then replaces the
 * buffer instead of appending a second copy.
 */
export function useConsoleSocket(serverId: string, onProgress?: (p: Progress) => void) {
  const linesRef = useRef<ConsoleLine[]>([]);
  const [version, setVersion] = useState(0);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [target, setTarget] = useState<TargetState>({ src: null, status: "unknown", running: false });
  const wsRef = useRef<WebSocket | null>(null);
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;

  // Re-render at most once per frame, however many lines arrive.
  const frameRef = useRef<number | null>(null);
  const bump = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      setVersion((v) => v + 1);
    });
  }, []);

  const push = useCallback(
    (lines: ConsoleLine[]) => {
      const buf = linesRef.current;
      buf.push(...lines);
      if (buf.length > MAX_LINES) buf.splice(0, buf.length - MAX_LINES);
      bump();
    },
    [bump],
  );

  const panel = useCallback(
    (msg: string) => push([makeLine("panel", new Date().toISOString(), msg)]),
    [push],
  );

  useEffect(() => {
    let disposed = false;
    let retryDelay = MIN_RETRY_MS;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (disposed) return;
      const ws = new WebSocket(consoleWsUrl(serverId));
      wsRef.current = ws;

      ws.onopen = () => {
        retryDelay = MIN_RETRY_MS;
        setConnection("live");
      };

      ws.onmessage = (ev) => {
        let frame: Frame;
        try {
          frame = JSON.parse(typeof ev.data === "string" ? ev.data : "");
        } catch {
          return;
        }
        switch (frame.t) {
          case "reset":
            linesRef.current = [];
            bump();
            break;
          case "lines": {
            const made = frame.lines.map(([ts, text]) => makeLine(frame.src as LineSource, ts, text));
            push(made);
            if (frame.src === "install" && onProgressRef.current) {
              for (let i = made.length - 1; i >= 0; i--) {
                const p = parseProgress(made[i].plain);
                if (p) {
                  onProgressRef.current(p);
                  break;
                }
              }
            }
            break;
          }
          case "source":
            panel(
              frame.src === "install"
                ? "── SteamCMD install / update started ──"
                : "── Server container started ──",
            );
            break;
          case "state":
            setTarget({ src: frame.src, status: frame.status, running: frame.running && frame.src === "server" });
            break;
          case "ended":
            panel(
              frame.src === "install"
                ? `── SteamCMD finished (exit code ${frame.exit_code ?? "?"}) ──`
                : `── Server stopped (exit code ${frame.exit_code ?? "?"}) ──`,
            );
            break;
          case "info":
            panel(frame.msg);
            break;
          case "error":
            panel(`[error] ${frame.msg}`);
            break;
        }
      };

      ws.onclose = (ev) => {
        if (disposed) return;
        wsRef.current = null;
        if (ev.code === 1008) {
          // Policy violation = invalid token; retrying won't help.
          panel("[error] not authorized — sign in again");
          setConnection("offline");
          return;
        }
        setConnection("reconnecting");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS);
      };
    }

    connect();
    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
      wsRef.current = null;
      linesRef.current = [];
    };
  }, [serverId, bump, push, panel]);

  /** Send a command to the server's stdin; echoed locally as an input line. */
  const send = useCallback(
    (command: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      ws.send(JSON.stringify({ t: "cmd", data: command }));
      push([makeLine("input", new Date().toISOString(), command)]);
      return true;
    },
    [push],
  );

  /** Clear the view only (the server's log is untouched). */
  const clear = useCallback(() => {
    linesRef.current = [];
    bump();
  }, [bump]);

  return { lines: linesRef.current, version, connection, target, send, clear };
}
