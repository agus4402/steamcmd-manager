"use client";

import { useEffect, useRef } from "react";
import { consoleWsUrl } from "@/lib/api";
import type { Progress } from "@/lib/types";
import "@xterm/xterm/css/xterm.css";

// steamcmd: "... downloading, progress: 5.83 (3964799848 / 67960769488)"
const PROGRESS_RE = /progress:\s*([\d.]+)\s*\((\d+)\s*\/\s*(\d+)\)/g;

const BUSY = new Set(["installing", "updating", "running"]);

const MIN_RETRY_MS = 1_500;
const MAX_RETRY_MS = 30_000;
const MAX_RETRIES = 12;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyTerminal = any;

export default function Console({
  serverId,
  serverStatus,
  onProgress,
}: {
  serverId: string;
  serverStatus?: string;
  onProgress?: (p: Progress) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Cross-effect refs — allow the status-watcher effect to trigger a reconnect.
  const termRef = useRef<AnyTerminal>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<{ count: number; delay: number; timer: ReturnType<typeof setTimeout> | null }>({
    count: 0,
    delay: MIN_RETRY_MS,
    timer: null,
  });
  const connectRef = useRef<() => void>(() => {});
  const disposedRef = useRef(false);

  // Keep latest callbacks/state without re-running the WS effect.
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;
  const serverStatusRef = useRef(serverStatus);
  serverStatusRef.current = serverStatus;

  // Main effect: set up xterm once per serverId. connectRef is assigned here so
  // the status-watcher effect can call it without stale closure issues.
  useEffect(() => {
    disposedRef.current = false;

    function connectWs() {
      const term = termRef.current;
      if (disposedRef.current || !term) return;

      // Cancel any pending retry.
      const rs = retryRef.current;
      if (rs.timer !== null) {
        clearTimeout(rs.timer);
        rs.timer = null;
      }

      // Close any existing socket.
      const prevWs = wsRef.current;
      if (prevWs) {
        prevWs.onclose = null;
        prevWs.close();
        wsRef.current = null;
      }

      let progBuf = "";
      const ws = new WebSocket(consoleWsUrl(serverId));
      wsRef.current = ws;

      ws.onopen = () => {
        // Successful connection — reset backoff state.
        retryRef.current.count = 0;
        retryRef.current.delay = MIN_RETRY_MS;
      };

      ws.onmessage = (ev) => {
        const text = typeof ev.data === "string" ? ev.data : "";
        if (!text) return; // ignore keepalive empty frames
        term.write(text);
        if (onProgressRef.current) {
          progBuf = (progBuf + text).slice(-4000);
          let m: RegExpExecArray | null;
          let last: RegExpExecArray | null = null;
          PROGRESS_RE.lastIndex = 0;
          while ((m = PROGRESS_RE.exec(progBuf)) !== null) last = m;
          if (last) {
            onProgressRef.current({
              percent: parseFloat(last[1]),
              downloaded: parseInt(last[2], 10),
              total: parseInt(last[3], 10),
            });
          }
        }
      };

      ws.onclose = () => {
        if (disposedRef.current) return;
        term.writeln("\r\n\x1b[90m[disconnected]\x1b[0m");

        const rs = retryRef.current;
        if (rs.count >= MAX_RETRIES) {
          term.writeln("\x1b[31m[connection lost — reload to reconnect]\x1b[0m");
          return;
        }

        // Reconnect whenever status is BUSY (install/update in progress).
        if (serverStatusRef.current && BUSY.has(serverStatusRef.current)) {
          const jitter = 1 + (Math.random() - 0.5) * 0.6; // ±30%
          const delay = Math.round(Math.min(rs.delay * jitter, MAX_RETRY_MS));
          rs.count += 1;
          rs.delay = Math.min(rs.delay * 2, MAX_RETRY_MS);
          term.writeln(
            `\x1b[90mreconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${rs.count}/${MAX_RETRIES})…\x1b[0m`
          );
          rs.timer = setTimeout(connectWs, delay);
        }
      };

      ws.onerror = () => term.writeln("\r\n\x1b[31m[connection error]\x1b[0m");
    }

    // Expose connectWs so the status-watcher effect can call it.
    connectRef.current = connectWs;

    (async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      if (disposedRef.current || !containerRef.current) return;

      const term = new Terminal({
        convertEol: true,
        fontFamily: "ui-monospace, monospace",
        fontSize: 12,
        theme: { background: "#0a0a0a", foreground: "#d4d4d4" },
        cursorBlink: true,
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(containerRef.current);
      fit.fit();
      termRef.current = term;

      term.writeln("\x1b[90mconnecting to console…\x1b[0m");
      connectWs();

      // Forward typed lines to the server's stdin.
      let line = "";
      term.onData((data: string) => {
        const code = data.charCodeAt(0);
        const ws = wsRef.current;
        if (data === "\r") {
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(line);
          term.write("\r\n");
          line = "";
        } else if (code === 127 || code === 8) {
          if (line.length > 0) {
            line = line.slice(0, -1);
            term.write("\b \b");
          }
        } else {
          line += data;
          term.write(data);
        }
      });

      const onResize = () => fit.fit();
      window.addEventListener("resize", onResize);

      // Store cleanup for resize listener inside term dispose.
      const origDispose = term.dispose.bind(term);
      term.dispose = () => {
        window.removeEventListener("resize", onResize);
        origDispose();
      };
    })();

    return () => {
      disposedRef.current = true;
      const rs = retryRef.current;
      if (rs.timer !== null) { clearTimeout(rs.timer); rs.timer = null; }
      const ws = wsRef.current;
      if (ws) { ws.onclose = null; ws.close(); wsRef.current = null; }
      termRef.current?.dispose();
      termRef.current = null;
    };
  }, [serverId]);

  // Status watcher: when serverStatus transitions to BUSY and the WS is dead,
  // reconnect immediately (reset backoff so it starts fresh for the new operation).
  useEffect(() => {
    if (!serverStatus || !BUSY.has(serverStatus)) return;
    const ws = wsRef.current;
    const isDead =
      !ws ||
      ws.readyState === WebSocket.CLOSED ||
      ws.readyState === WebSocket.CLOSING;
    if (isDead) {
      retryRef.current = { count: 0, delay: MIN_RETRY_MS, timer: null };
      connectRef.current();
    }
  }, [serverStatus]);

  return (
    <div
      ref={containerRef}
      className="h-[480px] w-full overflow-hidden rounded-lg border border-border bg-[#0a0a0a] p-2"
    />
  );
}
