/**
 * Mod lists in the format games export them, e.g. Project Zomboid's mod manager
 * preset: `presetName:ModA;ModB;ModC;` (mod ids, in load order). Also accepted:
 * a server ini `Mods=` line (B42 prefixes each id with `\`), or one id per line.
 */

export interface ParsedPreset {
  name: string | null;
  ids: string[];
}

export function parseModPreset(text: string): ParsedPreset {
  let body = text.replace(/^﻿/, "").trim();
  // A pasted/uploaded server ini: only its Mods= line matters.
  const modsLine = body.split(/\r?\n/).find((l) => /^\s*Mods\s*=/i.test(l));
  if (modsLine) body = modsLine.replace(/^\s*Mods\s*=/i, "");

  // "name:ids…" — a preset name sits before the first ":" when that comes
  // before the first ";" (mod ids themselves may contain spaces and dots).
  let name: string | null = null;
  const colon = body.indexOf(":");
  const semi = body.indexOf(";");
  if (colon > 0 && (semi === -1 || colon < semi) && !body.slice(0, colon).includes("\n")) {
    name = body.slice(0, colon).trim() || null;
    body = body.slice(colon + 1);
  }

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const raw of body.split(/[;\r\n]+/)) {
    const id = raw.trim().replace(/^\\+/, "").trim();
    if (id && !seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
  }
  return { name, ids };
}

/** A preset line in the game's format: `name:ModA;ModB;` (enabled mods, in order). */
export function formatModPreset(name: string, modIds: string[]): string {
  const safe = name.replace(/[:;\s]+/g, " ").trim() || "mods";
  return `${safe}:${modIds.map((id) => `${id};`).join("")}`;
}

export interface PresetResult<T> {
  rows: T[];
  /** Ids from the preset found among the installed mods (in preset order). */
  matched: string[];
  /** Ids from the preset that aren't installed. */
  missing: string[];
  /** Installed mods left out of the preset. */
  unlisted: T[];
}

/**
 * Reorders `rows` to follow the preset: listed mods first, in its order and
 * enabled; the rest keep their relative order after them — disabled when
 * `disableOthers`, otherwise with their current toggle. Ids match exactly, or
 * case-insensitively as a fallback.
 */
export function applyModPreset<T extends { mod_id: string; enabled: boolean }>(
  rows: T[],
  ids: string[],
  { disableOthers = true }: { disableOthers?: boolean } = {},
): PresetResult<T> {
  const exact = new Map(rows.map((r) => [r.mod_id, r]));
  const lower = new Map<string, T>();
  for (const r of rows) if (!lower.has(r.mod_id.toLowerCase())) lower.set(r.mod_id.toLowerCase(), r);

  const used = new Set<T>();
  const head: T[] = [];
  const matched: string[] = [];
  const missing: string[] = [];
  for (const id of ids) {
    const row = exact.get(id) ?? lower.get(id.toLowerCase());
    if (!row) missing.push(id);
    else if (!used.has(row)) {
      used.add(row);
      head.push({ ...row, enabled: true });
      matched.push(row.mod_id);
    }
  }
  const unlisted = rows.filter((r) => !used.has(r));
  const tail = unlisted.map((r) => (disableOthers ? { ...r, enabled: false } : r));
  return { rows: [...head, ...tail], matched, missing, unlisted };
}
