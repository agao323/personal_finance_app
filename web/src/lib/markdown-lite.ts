/**
 * The advisor's answer format: a small, hand-written subset of Markdown.
 *
 * Paragraphs, headings, **bold**, *italics*, lists, tables and `inline code` — and nothing
 * else. **There is no node for a link, an image or raw HTML**, so `![x](https://…)`,
 * `[1]: https://…` and `<img src=…>` come out as the literal characters they are. This is not
 * a Markdown library with its dangerous features switched off: a library's defaults change
 * between versions, and a parser with no code path for `<a>` or `<img>` cannot be configured
 * into one. One of three layers against exfiltration through the browser — the API strips,
 * this cannot draw, the CSP would block (docs/ADVISOR.md#prompt-injection).
 *
 * `[[screen:cards]]` becomes a screen node when the name is in the `Screen` enum, and text
 * otherwise. Figure spans — character offsets into the answer from the grounding check —
 * become figure nodes wherever they fall in plain text, so each figure can carry its status.
 *
 * Pure: text in, a tree out. `components/advisor/answer.tsx` draws the tree.
 */

import { SCREENS, type Screen } from "@/lib/screens";

export type Inline =
  | { type: "text"; text: string }
  | { type: "figure"; text: string; index: number }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "screen"; screen: Screen };

export type Block =
  | { type: "paragraph"; children: Inline[] }
  | { type: "heading"; level: 3 | 4; children: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "table"; header: Inline[][]; rows: Inline[][][] };

/** A figure's place in the answer text: `[start, end)`. */
export type Span = { start: number; end: number };

const KNOWN = new Set<string>(SCREENS);

type Line = { text: string; start: number };

function lines(text: string): Line[] {
  const out: Line[] = [];
  let start = 0;
  for (const piece of text.split("\n")) {
    out.push({ text: piece, start });
    start += piece.length + 1;
  }
  return out;
}

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

/** The text of `line` from `from` onward, with its absolute offset. */
function tail(line: Line, match: RegExpMatchArray): { text: string; start: number } {
  const body = match[match.length - 1] ?? "";
  return { text: body, start: line.start + line.text.length - body.length };
}

function cells(line: Line): { text: string; start: number }[] {
  const out: { text: string; start: number }[] = [];
  const raw = line.text;
  let index = raw.indexOf("|") + 1;
  while (index < raw.length) {
    const next = raw.indexOf("|", index);
    if (next < 0) break;
    const cell = raw.slice(index, next);
    const lead = cell.length - cell.trimStart().length;
    out.push({ text: cell.trim(), start: line.start + index + lead });
    index = next + 1;
  }
  return out;
}

export function parse(text: string, figures: Span[] = []): Block[] {
  const blocks: Block[] = [];
  const all = lines(text);
  const inline = (segment: { text: string; start: number }) =>
    parseInline(segment.text, segment.start, figures);

  let i = 0;
  while (i < all.length) {
    const line = all[i];
    if (line.text.trim() === "" || /^\s*```/.test(line.text)) {
      i += 1; // code fences are not rendered; what they hold reads as plain paragraphs
      continue;
    }
    const heading = line.text.match(HEADING);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length <= 3 ? 3 : 4,
        children: inline(tail(line, heading)),
      });
      i += 1;
      continue;
    }
    if (TABLE_ROW.test(line.text) && i + 1 < all.length && TABLE_RULE.test(all[i + 1].text)) {
      const header = cells(line).map(inline);
      const rows: Inline[][][] = [];
      i += 2;
      while (i < all.length && TABLE_ROW.test(all[i].text)) {
        rows.push(cells(all[i]).map(inline));
        i += 1;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }
    const bullet = line.text.match(BULLET);
    const numbered = line.text.match(NUMBERED);
    if (bullet || numbered) {
      const ordered = !bullet;
      const pattern = ordered ? NUMBERED : BULLET;
      const items: Inline[][] = [];
      while (i < all.length) {
        const match = all[i].text.match(pattern);
        if (!match) break;
        items.push(inline(tail(all[i], match)));
        i += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }
    // A paragraph: consecutive lines until a blank or another block begins.
    const children: Inline[] = [];
    while (i < all.length) {
      const current = all[i];
      if (
        current.text.trim() === "" ||
        HEADING.test(current.text) ||
        BULLET.test(current.text) ||
        NUMBERED.test(current.text) ||
        /^\s*```/.test(current.text)
      ) {
        break;
      }
      if (children.length > 0) children.push({ type: "text", text: " " });
      children.push(...inline({ text: current.text, start: current.start }));
      i += 1;
    }
    blocks.push({ type: "paragraph", children });
  }
  return blocks;
}

/**
 * Inline markup over `text`, which begins at `offset` in the whole answer.
 *
 * Recognised: `[[screen:name]]`, `**bold**`, `*italic*` / `_italic_`, `` `code` ``. Every
 * other character is text — including `!`, `[`, `]`, `(`, `<` and `>`.
 */
export function parseInline(text: string, offset: number, figures: Span[] = []): Inline[] {
  const out: Inline[] = [];
  let plainFrom = 0;
  let i = 0;

  const flush = (until: number) => {
    if (until > plainFrom)
      out.push(...withFigures(text.slice(plainFrom, until), offset + plainFrom, figures));
  };

  while (i < text.length) {
    const rest = text.slice(i);
    const screen = rest.match(/^\[\[screen:([a-z_]+)\]\]/);
    if (screen) {
      flush(i);
      out.push(
        KNOWN.has(screen[1])
          ? { type: "screen", screen: screen[1] as Screen }
          : { type: "text", text: screen[0] },
      );
      i += screen[0].length;
      plainFrom = i;
      continue;
    }
    const strong = rest.match(/^\*\*(?=\S)([\s\S]*?\S)\*\*/);
    if (strong) {
      flush(i);
      out.push({ type: "strong", children: parseInline(strong[1], offset + i + 2, figures) });
      i += strong[0].length;
      plainFrom = i;
      continue;
    }
    const em = rest.match(/^([*_])(?=\S)([\s\S]*?\S)\1(?![*_\w])/);
    if (em && (i === 0 || !/\w/.test(text[i - 1]))) {
      flush(i);
      out.push({ type: "em", children: parseInline(em[2], offset + i + 1, figures) });
      i += em[0].length;
      plainFrom = i;
      continue;
    }
    const code = rest.match(/^`([^`]+)`/);
    if (code) {
      flush(i);
      out.push({ type: "code", text: code[1] });
      i += code[0].length;
      plainFrom = i;
      continue;
    }
    i += 1;
  }
  flush(text.length);
  return out;
}

/** Plain text at absolute `offset`, split wherever a figure span falls wholly inside it. */
function withFigures(text: string, offset: number, figures: Span[]): Inline[] {
  const out: Inline[] = [];
  let cursor = 0;
  const end = offset + text.length;
  figures
    .map((span, index) => ({ ...span, index }))
    .filter((span) => span.start >= offset && span.end <= end && span.end > span.start)
    .sort((a, b) => a.start - b.start)
    .forEach((span) => {
      const from = span.start - offset;
      if (from < cursor) return; // overlapping spans: the first wins
      if (from > cursor) out.push({ type: "text", text: text.slice(cursor, from) });
      out.push({ type: "figure", text: text.slice(from, span.end - offset), index: span.index });
      cursor = span.end - offset;
    });
  if (cursor < text.length) out.push({ type: "text", text: text.slice(cursor) });
  return out;
}
