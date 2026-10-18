"use client";

import { forwardRef, useEffect, useRef, useState } from "react";
import { CornerDownLeft } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_HISTORY = 100;
const historyKey = (serverId: string) => `steamcmd_console_history_${serverId}`;

function loadHistory(serverId: string): string[] {
  try {
    const raw = window.localStorage.getItem(historyKey(serverId));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function saveHistory(serverId: string, history: string[]) {
  try {
    window.localStorage.setItem(historyKey(serverId), JSON.stringify(history.slice(-MAX_HISTORY)));
  } catch {
    /* storage unavailable: history lasts for this visit only */
  }
}

/**
 * Server-console prompt: Enter sends, ↑/↓ walk the command history (kept per
 * server in this browser), Esc clears the line.
 */
export const ConsoleInput = forwardRef<
  HTMLInputElement,
  { serverId: string; disabled: boolean; disabledHint: string; onSend: (command: string) => boolean }
>(function ConsoleInput({ serverId, disabled, disabledHint, onSend }, ref) {
  const [value, setValue] = useState("");
  const history = useRef<string[]>([]);
  // Position while browsing history; history.length = the line being typed.
  const cursor = useRef(0);
  const draft = useRef("");

  useEffect(() => {
    history.current = loadHistory(serverId);
    cursor.current = history.current.length;
  }, [serverId]);

  function submit() {
    const command = value.trim();
    if (!command || disabled) return;
    if (!onSend(command)) return;
    const h = history.current;
    if (h[h.length - 1] !== command) h.push(command);
    history.current = h.slice(-MAX_HISTORY);
    saveHistory(serverId, history.current);
    cursor.current = history.current.length;
    draft.current = "";
    setValue("");
  }

  function browse(step: -1 | 1) {
    const h = history.current;
    if (h.length === 0) return;
    if (cursor.current === h.length) draft.current = value;
    const next = Math.min(h.length, Math.max(0, cursor.current + step));
    if (next === cursor.current) return;
    cursor.current = next;
    setValue(next === h.length ? draft.current : h[next]);
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 border-t border-white/10 bg-[#0b0d10] px-3 font-mono text-[13px]",
        disabled && "opacity-60",
      )}
    >
      <span className="select-none text-[#8bc34a]" aria-hidden>
        &gt;
      </span>
      <input
        ref={ref}
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            browse(-1);
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            browse(1);
          } else if (e.key === "Escape") {
            setValue("");
            cursor.current = history.current.length;
          }
        }}
        placeholder={disabled ? disabledHint : "Type a server command and press Enter  (↑/↓ history)"}
        aria-label="Server command"
        spellCheck={false}
        autoComplete="off"
        className="h-10 min-w-0 flex-1 bg-transparent text-[#e6e6e6] caret-[#8bc34a] outline-none placeholder:text-[#6b7280] disabled:cursor-not-allowed"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="flex size-7 items-center justify-center rounded text-[#9ca3af] transition-colors hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-40"
        aria-label="Send command"
        title="Send (Enter)"
      >
        <CornerDownLeft className="size-4" />
      </button>
    </div>
  );
});
