/**
 * Minimal ANSI SGR parser for the console: turns "\x1b[31mred\x1b[0m" into
 * styled segments. Only colors/bold/dim/italic/underline are kept; any other
 * escape sequence (cursor moves, erase line, titles…) is dropped.
 */

export interface AnsiStyle {
  fg?: string;
  bg?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

export interface AnsiSegment {
  text: string;
  style: AnsiStyle;
}

// xterm's default 16-color palette, tuned for a near-black background.
const BASE = [
  "#3b3b3b", "#ef5350", "#8bc34a", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#d4d4d4",
  "#7f7f7f", "#ff6e6e", "#b5e48c", "#ffd866", "#82b1ff", "#e1a6ff", "#7fdbe6", "#ffffff",
];

function color256(n: number): string | undefined {
  if (n < 0 || n > 255) return undefined;
  if (n < 16) return BASE[n];
  if (n < 232) {
    const v = n - 16;
    const c = (x: number) => (x === 0 ? 0 : 55 + x * 40);
    return `rgb(${c(Math.floor(v / 36))},${c(Math.floor(v / 6) % 6)},${c(v % 6)})`;
  }
  const g = 8 + (n - 232) * 10;
  return `rgb(${g},${g},${g})`;
}

// CSI ... final byte, OSC ... BEL/ST, or a lone two-char escape.
const ESCAPE = /\x1b(?:\[([0-9;?]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])/g;

function applySgr(style: AnsiStyle, params: string): AnsiStyle {
  const codes = params === "" ? [0] : params.split(";").map((p) => Number(p) || 0);
  let s = { ...style };
  for (let i = 0; i < codes.length; i++) {
    const c = codes[i];
    if (c === 0) s = {};
    else if (c === 1) s.bold = true;
    else if (c === 2) s.dim = true;
    else if (c === 3) s.italic = true;
    else if (c === 4) s.underline = true;
    else if (c === 22) s.bold = s.dim = false;
    else if (c === 23) s.italic = false;
    else if (c === 24) s.underline = false;
    else if (c >= 30 && c <= 37) s.fg = BASE[c - 30];
    else if (c >= 90 && c <= 97) s.fg = BASE[c - 90 + 8];
    else if (c === 39) s.fg = undefined;
    else if (c >= 40 && c <= 47) s.bg = BASE[c - 40];
    else if (c >= 100 && c <= 107) s.bg = BASE[c - 100 + 8];
    else if (c === 49) s.bg = undefined;
    else if (c === 38 || c === 48) {
      const key = c === 38 ? "fg" : "bg";
      if (codes[i + 1] === 5) {
        s[key] = color256(codes[i + 2]);
        i += 2;
      } else if (codes[i + 1] === 2) {
        const [r, g, b] = codes.slice(i + 2, i + 5);
        s[key] = `rgb(${r ?? 0},${g ?? 0},${b ?? 0})`;
        i += 4;
      }
    }
  }
  return s;
}

export function parseAnsi(input: string): AnsiSegment[] {
  const out: AnsiSegment[] = [];
  let style: AnsiStyle = {};
  let last = 0;
  ESCAPE.lastIndex = 0;
  for (let m = ESCAPE.exec(input); m; m = ESCAPE.exec(input)) {
    if (m.index > last) out.push({ text: input.slice(last, m.index), style });
    last = m.index + m[0].length;
    if (m[2] === "m") style = applySgr(style, m[1] ?? "");
  }
  if (last < input.length) out.push({ text: input.slice(last), style });
  return out;
}

export function stripAnsi(input: string): string {
  return input.replace(ESCAPE, "");
}
