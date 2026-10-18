"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Renders Steam Workshop BBCode ([h1], [b], [url=…], [list][*]…) as React
 * elements. Parsed into a tree — never injected as HTML — and unknown or
 * unbalanced tags are shown as plain text, so a malformed description degrades
 * to what Steam would show instead of breaking the page.
 */

type Node = string | Element;
interface Element {
  tag: string;
  arg: string | null;
  children: Node[];
}

const TAGS = new Set([
  "h1", "h2", "h3", "b", "i", "u", "strike", "spoiler", "hr", "noparse", "code",
  "quote", "list", "olist", "*", "url", "img", "table", "tr", "th", "td", "previewyoutube",
]);
// Tags whose content is kept verbatim (no nested tag parsing).
const RAW = new Set(["noparse", "code"]);
// Block-level tags: whitespace-only text right after them is dropped, so the
// source's own newlines don't add extra blank lines around headings and lists.
const BLOCK = new Set([
  "h1", "h2", "h3", "hr", "code", "quote", "list", "olist", "*", "table", "tr", "th", "td",
]);
// [*] items and table cells end at the next sibling or the parent's close.
const IMPLICIT_CLOSE: Record<string, string[]> = { "*": ["*"], td: ["td", "th"], th: ["td", "th"] };

const TOKEN = /\[(\/?)([a-z0-9*]+)(?:=([^\]]*))?\]/gi;

export function parseBBCode(source: string): Node[] {
  const root: Element = { tag: "root", arg: null, children: [] };
  const stack: Element[] = [root];
  const top = () => stack[stack.length - 1];
  let last = 0;

  const text = (s: string) => {
    if (s) top().children.push(s);
  };

  TOKEN.lastIndex = 0;
  for (let m = TOKEN.exec(source); m; m = TOKEN.exec(source)) {
    const [raw, slash, name] = m;
    const tag = name.toLowerCase();
    const current = top();

    // Inside [noparse]/[code] only its own closing tag counts.
    if (RAW.has(current.tag) && !(slash && tag === current.tag)) continue;
    if (!TAGS.has(tag)) continue;

    text(source.slice(last, m.index));
    last = m.index + raw.length;

    if (slash) {
      const at = stack.map((e) => e.tag).lastIndexOf(tag);
      if (at <= 0) {
        text(raw); // stray closing tag
        continue;
      }
      // Unclosed tags inside it are closed implicitly.
      stack.length = at;
      continue;
    }

    const closes = IMPLICIT_CLOSE[tag];
    if (closes) {
      let at = -1;
      for (let s = stack.length - 1; s > 0 && at < 0; s--) if (closes.includes(stack[s].tag)) at = s;
      // Only close a sibling still open inside the same list/row.
      if (at > 0 && stack.slice(at + 1).every((e) => !BLOCK.has(e.tag) || closes.includes(e.tag))) {
        stack.length = at;
      }
    }

    const el: Element = { tag, arg: m[3] ?? null, children: [] };
    top().children.push(el);
    if (tag !== "hr") stack.push(el);
  }
  text(source.slice(last));

  return root.children;
}

function safeUrl(url: string | null | undefined): string | null {
  const value = (url ?? "").trim();
  return /^https?:\/\//i.test(value) ? value : null;
}

function textOf(nodes: Node[]): string {
  return nodes.map((n) => (typeof n === "string" ? n : textOf(n.children))).join("");
}

function Spoiler({ children }: { children: React.ReactNode }) {
  const [shown, setShown] = React.useState(false);
  return (
    <span
      role="button"
      tabIndex={0}
      onClick={() => setShown(true)}
      onKeyDown={(e) => e.key === "Enter" && setShown(true)}
      className={cn(
        "rounded bg-muted px-1 transition",
        !shown && "cursor-pointer select-none text-transparent [text-shadow:0_0_8px_hsl(var(--muted-foreground))]",
      )}
      title={shown ? undefined : "Show spoiler"}
    >
      {children}
    </span>
  );
}

const isBlock = (n: Node | undefined) => n !== undefined && typeof n !== "string" && BLOCK.has(n.tag);
// Containers where loose text is invalid markup (whitespace between rows/items).
const NO_TEXT = new Set(["list", "olist", "table", "tr"]);

/** Text node with the line breaks that only separate it from blocks removed. */
function blockAwareText(nodes: Node[], i: number, parent: string): string {
  let s = nodes[i] as string;
  const containerEdge = BLOCK.has(parent) || parent === "root";
  if (isBlock(nodes[i - 1]) || (i === 0 && containerEdge)) s = s.replace(/^[ \t]*\r?\n/, "");
  if (isBlock(nodes[i + 1]) || (i === nodes.length - 1 && BLOCK.has(parent))) {
    s = s.replace(/\r?\n[ \t]*$/, "");
  }
  return NO_TEXT.has(parent) && !s.trim() ? "" : s;
}

function render(nodes: Node[], parent = "root", keyPrefix = ""): React.ReactNode[] {
  return nodes.map((node, i) => {
    const key = `${keyPrefix}${i}`;
    if (typeof node === "string") {
      const text = blockAwareText(nodes, i, parent);
      return text ? <React.Fragment key={key}>{text}</React.Fragment> : null;
    }
    const kids = () => render(node.children, node.tag, `${key}.`);
    switch (node.tag) {
      case "h1":
        return <span key={key} className="mb-1 mt-3 block text-base font-semibold text-foreground first:mt-0">{kids()}</span>;
      case "h2":
        return <span key={key} className="mb-1 mt-3 block text-sm font-semibold text-foreground first:mt-0">{kids()}</span>;
      case "h3":
        return <span key={key} className="mb-1 mt-2 block text-sm font-medium text-foreground first:mt-0">{kids()}</span>;
      case "b":
        return <strong key={key} className="font-semibold text-foreground">{kids()}</strong>;
      case "i":
        return <em key={key}>{kids()}</em>;
      case "u":
        return <span key={key} className="underline">{kids()}</span>;
      case "strike":
        return <s key={key}>{kids()}</s>;
      case "spoiler":
        return <Spoiler key={key}>{kids()}</Spoiler>;
      case "hr":
        return <hr key={key} className="my-3 border-border" />;
      case "noparse":
        return <React.Fragment key={key}>{textOf(node.children)}</React.Fragment>;
      case "code":
        return (
          <code key={key} className="my-2 block overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 font-mono text-xs">
            {textOf(node.children)}
          </code>
        );
      case "quote":
        return (
          <span key={key} className="my-2 block border-l-2 border-border pl-3 italic">
            {node.arg && <span className="mb-1 block text-xs not-italic">{node.arg} wrote:</span>}
            {kids()}
          </span>
        );
      case "list":
        return <ul key={key} className="my-1 list-disc pl-5">{kids()}</ul>;
      case "olist":
        return <ol key={key} className="my-1 list-decimal pl-5">{kids()}</ol>;
      case "*":
        return <li key={key}>{kids()}</li>;
      case "url": {
        const href = safeUrl(node.arg ?? textOf(node.children));
        if (!href) return <React.Fragment key={key}>{kids()}</React.Fragment>;
        return (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer" className="break-words text-info hover:underline">
            {kids()}
          </a>
        );
      }
      case "img": {
        const src = safeUrl(textOf(node.children));
        if (!src) return null;
        // eslint-disable-next-line @next/next/no-img-element
        return (
          <img
            key={key}
            src={src}
            alt=""
            loading="lazy"
            // Dead image links are common in old descriptions: drop them instead of leaving a gap.
            onError={(e) => (e.currentTarget.style.display = "none")}
            className="my-2 block max-w-full rounded-md"
          />
        );
      }
      case "previewyoutube": {
        const id = (node.arg ?? "").split(";")[0].trim();
        if (!/^[\w-]{6,20}$/.test(id)) return null;
        return (
          <a key={key} href={`https://www.youtube.com/watch?v=${id}`} target="_blank" rel="noopener noreferrer" className="block text-info hover:underline">
            YouTube video ↗
          </a>
        );
      }
      case "table":
        return (
          <span key={key} className="my-2 block overflow-x-auto">
            <table className="text-xs">
              <tbody>{kids()}</tbody>
            </table>
          </span>
        );
      case "tr":
        return <tr key={key}>{kids()}</tr>;
      case "th":
        return <th key={key} className="border border-border px-2 py-1 text-left font-semibold">{kids()}</th>;
      case "td":
        return <td key={key} className="border border-border px-2 py-1">{kids()}</td>;
      default:
        return <React.Fragment key={key}>{kids()}</React.Fragment>;
    }
  });
}

export function SteamBBCode({ text, className }: { text: string; className?: string }) {
  const tree = React.useMemo(() => parseBBCode(text), [text]);
  return <div className={cn("whitespace-pre-line break-words", className)}>{render(tree)}</div>;
}
