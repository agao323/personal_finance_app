# 064 — Icons for actions, and colour that actually appears
Status: done
Wave: 7   Lane: —
Blocked by: none

## The bug found on the way in

`--warning-text` **does not exist.** Three components style urgency with
`text-warning-text`, which resolves to nothing — so the urgent state has been rendering in
inherited body colour this whole time. The colour complaint was a missing token, not a
design choice.

`--critical-text` exists precisely because raw status hues fail contrast as text; warning
never got the same treatment.

## Acceptance criteria
- [x] Define `--warning-text` and `--warning-bg` in all three theme blocks, following the
      `--critical-text` precedent: a darker step of the status hue for light, a lighter one
      for dark. Tuned for 14px text, not for a mark
- [x] Icon buttons for **edit** (pencil) and **remove** (trash, critical hue) in place of
      words. Inline SVG using `currentColor` — no icon library, nothing external to load
- [x] Every icon button carries an `aria-label` and a visible tooltip. An icon-only control
      with no accessible name is unusable with a screen reader and ambiguous with a mouse
- [x] Urgency reads as urgent: warning chip behind the countdown, not a grey glyph
- [x] **Never colour alone** — the ⚠ glyph and the text stay. Colour is the amplifier
- [x] "Past use" keeps its word for now. It was called confusing and an icon would make a
      confusing thing harder to find rather than easier
- [x] Tests: icon buttons are reachable by their accessible name

## Files
- `web/src/app/globals.css`
- `web/src/components/cards/icons.tsx`
- `web/src/components/cards/card-row.tsx`, `upcoming.tsx`

## Done — 2026-09-26

**The colour complaint was a missing token, not a design choice.** `--warning-text` was
never defined, so `text-warning-text` in three components resolved to nothing and every
urgent state rendered in inherited body colour. `--critical-text` exists precisely because
raw status hues fail contrast as text; warning never got the same treatment. Both it and
`--warning-bg` are now defined in all three theme blocks.

Icons are hand-authored inline SVG on `currentColor` — four small shapes do not justify a
dependency, and there is no second palette to keep in step. `IconButton` takes a
**required** label, exposed as both `aria-label` and a tooltip: an icon with no accessible
name is unusable with a screen reader and ambiguous with a mouse. A test reaches every icon
control by that name.

"Past use" kept its word. It was called confusing, and an icon would make a confusing thing
harder to find rather than easier.
