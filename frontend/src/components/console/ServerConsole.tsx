"use client";

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowDown,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Download,
  Eraser,
  Maximize2,
  Minimize2,
  Search,
  WrapText,
  X,
} from "lucide-react";
import type { AnsiSegment } from "@/lib/ansi";
import { formatTime, linesToText, type ConsoleLine } from "@/lib/consoleBuffer";
import type { Progress } from "@/lib/types";
import { cn, copyToClipboard } from "@/lib/utils";
import { ConsoleInput } from "./ConsoleInput";
import { useConsoleSocket, type Connection } from "./useConsoleSocket";

type LevelFilter = "all" | "error" | "warn" | "input";
type SourceFilter = "all" | "server" | "install";

const LEVELS: { value: LevelFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "error", label: "Errors" },
  { value: "warn", label: "Warnings" },
  { value: "input", label: "Commands" },
];

const PREFS_KEY = "steamcmd_console_prefs";

interface Match {
  lineId: number;
  start: number;
  end: number;
}

function usePrefs() {
  const [prefs, setPrefs] = useState({ timestamps: true, wrap: true });
  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(PREFS_KEY) ?? "null");
      if (saved && typeof saved === "object") setPrefs((p) => ({ ...p, ...saved }));
    } catch {
      /* storage unavailable */
    }
  }, []);
  const update = useCallback((patch: Partial<typeof prefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      try {
        window.localStorage.setItem(PREFS_KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  }, []);
  return [prefs, update] as const;
}

/**
 * Live server console: the game server's (or SteamCMD's, during installs and
 * updates) output with colors, search, filters, copy/export, and a prompt that
 * sends commands to the server's stdin.
 */
export default function ServerConsole({
  serverId,
  serverName,
  onProgress,
}: {
  serverId: string;
  serverName: string;
  onProgress?: (p: Progress) => void;
}) {
  const { lines, version, connection, target, send, clear } = useConsoleSocket(serverId, onProgress);
  const [prefs, setPrefs] = usePrefs();
  const [level, setLevel] = useState<LevelFilter>("all");
  const [source, setSource] = useState<SourceFilter>("all");
  const [query, setQuery] = useState("");
  const [matchesOnly, setMatchesOnly] = useState(false);
  const [activeMatch, setActiveMatch] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [following, setFollowing] = useState(true);
  const followingRef = useRef(true);
  const lastSeenId = useRef(0);

  const viewportRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const q = query.trim().toLowerCase();
  const hasInstall = useMemo(() => lines.some((l) => l.src === "install"), [lines, version]); // eslint-disable-line react-hooks/exhaustive-deps

  // Lines passing the level/source filters (panel notices always stay visible).
  const filtered = useMemo(
    () =>
      lines.filter((l) => {
        if (source !== "all" && (l.src === "server" || l.src === "install") && l.src !== source) return false;
        if (level === "all") return true;
        if (level === "input") return l.src === "input";
        if (level === "warn") return l.level === "warn" || l.level === "error";
        return l.level === "error";
      }),
    [lines, version, level, source], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const matches = useMemo(() => {
    if (!q) return [] as Match[];
    const out: Match[] = [];
    for (const l of filtered) {
      const text = l.plain.toLowerCase();
      for (let i = text.indexOf(q); i !== -1; i = text.indexOf(q, i + q.length)) {
        out.push({ lineId: l.id, start: i, end: i + q.length });
      }
    }
    return out;
  }, [filtered, q]);

  const matchesByLine = useMemo(() => {
    const map = new Map<number, Match[]>();
    for (const m of matches) {
      const list = map.get(m.lineId);
      if (list) list.push(m);
      else map.set(m.lineId, [m]);
    }
    return map;
  }, [matches]);

  const visible = q && matchesOnly ? filtered.filter((l) => matchesByLine.has(l.id)) : filtered;
  const current = matches[Math.min(activeMatch, matches.length - 1)];
  const unseen = following ? 0 : countAfter(visible, lastSeenId.current);

  // Follow the tail only while the user is at the bottom.
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (el && followingRef.current) el.scrollTop = el.scrollHeight;
  }, [visible.length, version, prefs.wrap, prefs.timestamps, fullscreen]);

  function onScroll() {
    const el = viewportRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom !== followingRef.current) {
      // Leaving the tail: lines newer than the newest one now count as "new".
      if (!atBottom) lastSeenId.current = lines[lines.length - 1]?.id ?? 0;
      followingRef.current = atBottom;
      setFollowing(atBottom);
    }
  }

  function jumpToLatest() {
    const el = viewportRef.current;
    followingRef.current = true;
    setFollowing(true);
    if (el) el.scrollTop = el.scrollHeight;
  }

  // Search navigation: reveal the active match when the query changes or the
  // user steps through matches — not on every incoming line.
  const [navigation, setNavigation] = useState(0);
  useEffect(() => {
    setActiveMatch(0);
    setNavigation((n) => n + 1);
  }, [q]);
  useEffect(() => {
    if (!current) return;
    const row = viewportRef.current?.querySelector(`[data-line="${current.lineId}"]`);
    if (row) {
      if (followingRef.current) lastSeenId.current = lines[lines.length - 1]?.id ?? 0;
      followingRef.current = false;
      setFollowing(false);
      row.scrollIntoView({ block: "center" });
    }
  }, [navigation]); // eslint-disable-line react-hooks/exhaustive-deps

  function step(dir: 1 | -1) {
    if (!matches.length) return;
    setActiveMatch((i) => (Math.min(i, matches.length - 1) + dir + matches.length) % matches.length);
    setNavigation((n) => n + 1);
  }

  async function copyVisible() {
    const text = linesToText(visible, prefs.timestamps);
    if (!text) return toast.info("Nothing to copy");
    if (await copyToClipboard(text)) toast.success(`Copied ${visible.length} line${visible.length === 1 ? "" : "s"}`);
    else toast.error("Could not copy — select the text and copy it manually");
  }

  function exportLog() {
    if (!lines.length) return toast.info("Nothing to export yet");
    const blob = new Blob([linesToText(lines, true) + "\n"], { type: "text/plain;charset=utf-8" });
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${serverName}-console-${stamp}.log`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // Ctrl/Cmd+F searches the console (only while focus is inside it); Esc leaves fullscreen.
  function onKeyDown(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
      e.preventDefault();
      searchRef.current?.focus();
      searchRef.current?.select();
    } else if (e.key === "Escape" && fullscreen && document.activeElement !== searchRef.current) {
      setFullscreen(false);
    }
  }

  const inputDisabled = !target.running || connection !== "live";
  const disabledHint =
    connection !== "live"
      ? "Not connected"
      : target.src === "install"
        ? "SteamCMD is installing/updating — commands are available once the server runs"
        : "Server is not running — start it to send commands";

  return (
    <div
      onKeyDown={onKeyDown}
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border border-border bg-[#07090c] text-[#d4d4d4] shadow-sm",
        fullscreen ? "fixed inset-2 z-50" : "h-[calc(100dvh-16rem)] min-h-[440px]",
      )}
    >
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-[#0b0d10] px-2 py-1.5">
        <div className="relative min-w-[180px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-[#6b7280]" />
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                step(e.shiftKey ? -1 : 1);
              } else if (e.key === "Escape") {
                setQuery("");
              }
            }}
            placeholder="Search  (Ctrl+F)"
            aria-label="Search the console"
            className="h-8 w-full rounded-md border border-white/10 bg-black/40 pl-7 pr-20 font-mono text-xs text-[#e6e6e6] outline-none placeholder:text-[#6b7280] focus:border-primary"
          />
          {q && (
            <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5 text-[11px] text-[#9ca3af]">
              <span className="tabular-nums">
                {matches.length ? `${Math.min(activeMatch, matches.length - 1) + 1}/${matches.length}` : "0/0"}
              </span>
              <IconButton label="Previous match (Shift+Enter)" onClick={() => step(-1)} small>
                <ChevronUp className="size-3.5" />
              </IconButton>
              <IconButton label="Next match (Enter)" onClick={() => step(1)} small>
                <ChevronDown className="size-3.5" />
              </IconButton>
            </div>
          )}
        </div>
        {q && (
          <Toggle active={matchesOnly} onClick={() => setMatchesOnly((v) => !v)} label="Only lines that match">
            Matches only
          </Toggle>
        )}

        <div className="flex items-center rounded-md border border-white/10 p-0.5" role="group" aria-label="Filter by level">
          {LEVELS.map((l) => (
            <button
              key={l.value}
              onClick={() => setLevel(l.value)}
              aria-pressed={level === l.value}
              className={cn(
                "rounded px-2 py-1 text-xs transition-colors",
                level === l.value ? "bg-white/15 text-white" : "text-[#9ca3af] hover:text-white",
              )}
            >
              {l.label}
            </button>
          ))}
        </div>

        {hasInstall && (
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as SourceFilter)}
            aria-label="Filter by source"
            className="h-8 rounded-md border border-white/10 bg-black/40 px-2 text-xs text-[#e6e6e6] outline-none focus:border-primary"
          >
            <option value="all">All output</option>
            <option value="server">Server only</option>
            <option value="install">SteamCMD only</option>
          </select>
        )}

        <div className="ml-auto flex items-center gap-0.5">
          <IconButton label="Show timestamps" active={prefs.timestamps} onClick={() => setPrefs({ timestamps: !prefs.timestamps })}>
            <Clock className="size-4" />
          </IconButton>
          <IconButton label="Wrap long lines" active={prefs.wrap} onClick={() => setPrefs({ wrap: !prefs.wrap })}>
            <WrapText className="size-4" />
          </IconButton>
          <span className="mx-1 h-5 w-px bg-white/10" aria-hidden />
          <IconButton label="Copy visible lines" onClick={copyVisible}>
            <Copy className="size-4" />
          </IconButton>
          <IconButton label="Export as .log" onClick={exportLog}>
            <Download className="size-4" />
          </IconButton>
          <IconButton label="Clear the view (the server log is kept)" onClick={clear}>
            <Eraser className="size-4" />
          </IconButton>
          <IconButton label={fullscreen ? "Exit full screen (Esc)" : "Full screen"} onClick={() => setFullscreen((v) => !v)}>
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </IconButton>
        </div>
      </div>

      {/* Output */}
      <div className="relative min-h-0 flex-1">
        <div
          ref={viewportRef}
          onScroll={onScroll}
          tabIndex={0}
          role="log"
          aria-label="Server console output"
          aria-live="off"
          className="console-scroll absolute inset-0 overflow-auto py-2 font-mono text-[12.5px] leading-[1.45] outline-none"
        >
          {visible.length === 0 ? (
            <p className="px-3 text-[#6b7280]">
              {lines.length === 0
                ? connection === "live"
                  ? "Waiting for output…"
                  : "Connecting to the console…"
                : "No lines match the current filters."}
            </p>
          ) : (
            visible.map((l) => (
              <Line
                key={l.id}
                line={l}
                showTs={prefs.timestamps}
                wrap={prefs.wrap}
                matches={matchesByLine.get(l.id)}
                activeStart={current?.lineId === l.id ? current.start : -1}
              />
            ))
          )}
        </div>
        {!following && (
          <button
            onClick={jumpToLatest}
            className="absolute bottom-3 right-4 flex items-center gap-1.5 rounded-full border border-white/15 bg-[#1f2937]/95 px-3 py-1.5 text-xs text-white shadow-lg transition-colors hover:bg-[#374151]"
          >
            <ArrowDown className="size-3.5" />
            {unseen > 0 ? `${unseen} new line${unseen === 1 ? "" : "s"}` : "Jump to latest"}
          </button>
        )}
      </div>

      <ConsoleInput
        ref={inputRef}
        serverId={serverId}
        disabled={inputDisabled}
        disabledHint={disabledHint}
        onSend={(cmd) => {
          const ok = send(cmd);
          if (ok) jumpToLatest();
          return ok;
        }}
      />

      {/* Status bar */}
      <div className="flex items-center gap-3 border-t border-white/10 bg-[#0b0d10] px-3 py-1 text-[11px] text-[#9ca3af]">
        <ConnectionBadge connection={connection} />
        <span>
          {target.src === "install"
            ? "SteamCMD install / update"
            : target.src === "server"
              ? `Server · ${target.status}`
              : "No container"}
        </span>
        <span className="ml-auto tabular-nums">
          {visible.length !== lines.length ? `${visible.length.toLocaleString()} of ` : ""}
          {lines.length.toLocaleString()} lines
        </span>
      </div>
    </div>
  );
}

function countAfter(lines: ConsoleLine[], id: number): number {
  let n = 0;
  for (let i = lines.length - 1; i >= 0 && lines[i].id > id; i--) n++;
  return n;
}

const Line = memo(function Line({
  line,
  showTs,
  wrap,
  matches,
  activeStart,
}: {
  line: ConsoleLine;
  showTs: boolean;
  wrap: boolean;
  matches?: Match[];
  activeStart: number;
}) {
  const levelColor =
    line.src === "input"
      ? "text-[#7dd3fc]"
      : line.src === "panel"
        ? "text-[#8b95a5] italic"
        : line.level === "error"
          ? "text-[#ff7b72]"
          : line.level === "warn"
            ? "text-[#e3b341]"
            : undefined;
  return (
    <div
      data-line={line.id}
      className={cn(
        "flex gap-3 border-l-2 px-3 hover:bg-white/[0.04] [content-visibility:auto] [contain-intrinsic-size:auto_18px]",
        line.src === "install" ? "border-l-[#e5c07b]/50" : "border-l-transparent",
        line.level === "error" && line.src !== "panel" && "bg-[#ff7b72]/[0.06]",
      )}
    >
      {showTs && (
        <span className="shrink-0 select-none text-[#5c6370] tabular-nums">{formatTime(line.ts) || " ".repeat(8)}</span>
      )}
      <span className={cn("min-w-0 flex-1", wrap ? "whitespace-pre-wrap break-all" : "whitespace-pre", levelColor)}>
        {line.src === "input" && <span className="select-none text-[#8bc34a]">&gt; </span>}
        {renderSegments(line.segments, matches, activeStart)}
        {line.plain === "" && " "}
      </span>
    </div>
  );
});

/** Styled ANSI segments, with search matches (offsets in plain text) highlighted. */
function renderSegments(segments: AnsiSegment[], matches: Match[] | undefined, activeStart: number) {
  const out: React.ReactNode[] = [];
  let offset = 0;
  let key = 0;
  for (const seg of segments) {
    const style: React.CSSProperties = {
      color: seg.style.fg,
      backgroundColor: seg.style.bg,
      fontWeight: seg.style.bold ? 600 : undefined,
      opacity: seg.style.dim ? 0.7 : undefined,
      fontStyle: seg.style.italic ? "italic" : undefined,
      textDecoration: seg.style.underline ? "underline" : undefined,
    };
    const segStart = offset;
    const segEnd = offset + seg.text.length;
    offset = segEnd;
    // Cut the segment at every match boundary that falls inside it.
    let pos = segStart;
    for (const m of matches ?? []) {
      if (m.end <= pos || m.start >= segEnd) continue;
      const from = Math.max(m.start, pos);
      const to = Math.min(m.end, segEnd);
      if (from > pos) out.push(<span key={key++} style={style}>{seg.text.slice(pos - segStart, from - segStart)}</span>);
      out.push(
        <mark
          key={key++}
          style={style}
          className={cn(
            "rounded-[2px] text-inherit",
            m.start === activeStart ? "bg-[#f59e0b] !text-black" : "bg-[#f59e0b]/35",
          )}
        >
          {seg.text.slice(from - segStart, to - segStart)}
        </mark>,
      );
      pos = to;
    }
    if (pos < segEnd) out.push(<span key={key++} style={style}>{seg.text.slice(pos - segStart)}</span>);
  }
  return out;
}

function IconButton({
  label,
  onClick,
  active,
  small,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  small?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={cn(
        "flex items-center justify-center rounded transition-colors",
        small ? "size-6" : "size-8",
        active ? "bg-white/15 text-white" : "text-[#9ca3af] hover:bg-white/10 hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

function Toggle({
  active,
  onClick,
  label,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={label}
      className={cn(
        "h-8 rounded-md border px-2 text-xs transition-colors",
        active ? "border-primary/60 bg-primary/15 text-white" : "border-white/10 text-[#9ca3af] hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

function ConnectionBadge({ connection }: { connection: Connection }) {
  const map: Record<Connection, { label: string; dot: string }> = {
    connecting: { label: "Connecting…", dot: "bg-[#e3b341]" },
    live: { label: "Live", dot: "bg-[#8bc34a]" },
    reconnecting: { label: "Reconnecting…", dot: "bg-[#e3b341] animate-pulse" },
    offline: { label: "Offline", dot: "bg-[#ff7b72]" },
  };
  const { label, dot } = map[connection];
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", dot)} aria-hidden />
      {label}
    </span>
  );
}
