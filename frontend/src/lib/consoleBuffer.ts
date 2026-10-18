import { parseAnsi, stripAnsi, type AnsiSegment } from "./ansi";

/** Where a console line came from. */
export type LineSource = "server" | "install" | "input" | "panel";
export type LineLevel = "error" | "warn" | "info";

export interface ConsoleLine {
  id: number;
  /** RFC 3339 from Docker (null for panel/input lines without one). */
  ts: string | null;
  src: LineSource;
  level: LineLevel;
  segments: AnsiSegment[];
  /** Text without ANSI codes: search, filters, copy and export. */
  plain: string;
}

export const MAX_LINES = 10_000;

// Game/SteamCMD log conventions: "ERROR:", "[ERROR]", "Error!", Java stack traces…
const ERROR_RE = /\b(ERROR|ERR|FATAL|SEVERE|CRITICAL)\b|\bError!|Exception\b|Traceback \(most recent|^\s+at [\w.$]+\(/;
const WARN_RE = /\bWARN(ING)?\b|\bWarning:/;

let nextId = 1;

/**
 * A carriage return moves the cursor to the start of the line, so whatever is
 * printed after it overwrites what was there (SteamCMD progress redraws).
 * Keep what a terminal would end up showing.
 */
export function collapseCarriageReturns(raw: string): string {
  if (!raw.includes("\r")) return raw;
  let shown = "";
  for (const part of raw.split("\r")) {
    if (!part) continue;
    // Visible width (ANSI codes take no columns) decides how much is overwritten.
    const width = stripAnsi(part).length;
    shown = width >= stripAnsi(shown).length ? part : part + stripAnsi(shown).slice(width);
  }
  return shown;
}

export function makeLine(src: LineSource, ts: string | null, raw: string): ConsoleLine {
  const text = collapseCarriageReturns(raw);
  const plain = stripAnsi(text);
  const level: LineLevel = ERROR_RE.test(plain) ? "error" : WARN_RE.test(plain) ? "warn" : "info";
  return { id: nextId++, ts, src, level, segments: parseAnsi(text), plain };
}

/** Local wall-clock time for the timestamp column. */
export function formatTime(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour12: false });
}

/** Plain-text log, one line each — for copy and the .log export. */
export function linesToText(lines: ConsoleLine[], withTimestamps: boolean): string {
  return lines
    .map((l) => {
      const prefix = l.src === "input" ? "> " : "";
      if (!withTimestamps || !l.ts) return prefix + l.plain;
      return `[${l.ts}] ${prefix}${l.plain}`;
    })
    .join("\n");
}

// steamcmd: "... downloading, progress: 5.83 (3964799848 / 67960769488)"
const PROGRESS_RE = /progress:\s*([\d.]+)\s*\((\d+)\s*\/\s*(\d+)\)/;

export function parseProgress(plain: string) {
  const m = PROGRESS_RE.exec(plain);
  if (!m) return null;
  return { percent: parseFloat(m[1]), downloaded: parseInt(m[2], 10), total: parseInt(m[3], 10) };
}
