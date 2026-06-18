"use client";

import { useEffect, useRef } from "react";
import { consoleWsUrl } from "@/lib/api";
import type { Progress } from "@/lib/types";
import "@xterm/xterm/css/xterm.css";

// steamcmd: "... downloading, progress: 5.83 (3964799848 / 67960769488)"
const PROGRESS_RE = /progress:\s*([\d.]+)\s*\((\d+)\s*\/\s*(\d+)\)/g;

export default function Console({
  serverId,
  onProgress,
}: {
  serverId: string;
  onProgress?: (p: Progress) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Keep the latest callback without re-running the WS effect.
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;

  useEffect(() => {
    let disposed = false;
    let ws: WebSocket | null = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let term: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fit: any = null;
    let onResize: (() => void) | null = null;

    (async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      if (disposed || !containerRef.current) return;

      term = new Terminal({
        convertEol: true,
        fontFamily: "ui-monospace, monospace",
        fontSize: 12,
        theme: { background: "#0a0a0a", foreground: "#d4d4d4" },
        cursorBlink: true,
      });
      fit = new FitAddon();
      term.loadAddon(fit);
      term.open(containerRef.current);
      fit.fit();

      term.writeln("\x1b[90mconnecting to console…\x1b[0m");

      // Rolling buffer so we can match progress lines split across WS frames.
      let progBuf = "";
      ws = new WebSocket(consoleWsUrl(serverId));
      ws.onmessage = (ev) => {
        const text = typeof ev.data === "string" ? ev.data : "";
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
      ws.onclose = () => term.writeln("\r\n\x1b[90m[disconnected]\x1b[0m");
      ws.onerror = () => term.writeln("\r\n\x1b[31m[connection error]\x1b[0m");

      // Forward typed lines to the server's stdin.
      let line = "";
      term.onData((data: string) => {
        const code = data.charCodeAt(0);
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

      onResize = () => fit && fit.fit();
      window.addEventListener("resize", onResize);
    })();

    return () => {
      disposed = true;
      if (ws) ws.close();
      if (onResize) window.removeEventListener("resize", onResize);
      if (term) term.dispose();
    };
  }, [serverId]);

  return (
    <div
      ref={containerRef}
      className="h-[420px] w-full overflow-hidden rounded-lg border border-neutral-800 bg-[#0a0a0a] p-2"
    />
  );
}
