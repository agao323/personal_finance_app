# 025 — App shell, navigation, and design tokens
Status: done
Wave: 2   Lane: C
Blocked by: 012
Read first: docs/PRODUCT.md, docs/ARCHITECTURE.md#money

## Goal
The layout every screen sits in: nav, page chrome, typography scale, colour tokens, light and
dark. Establishes the visual system before any chart exists.

## Acceptance criteria
- [x] Sidebar or top nav with Dashboard, Accounts, Transactions, Import, Rules
- [x] Tailwind theme extended with a documented colour and spacing scale
- [x] Light and dark mode both verified
- [x] Loading and error boundary components used by every subsequent page
- [x] A number formatting utility taking **integer cents**: currency, compact, signed, percentage
- [x] A stale-value indicator component, used wherever the API flags a carried-forward balance
- [x] Tests: unit for the formatter covering negative, zero, very large, and rounding-boundary cases; component tests for nav active states and the error boundary

## Files
- `web/src/app/layout.tsx`
- `web/src/components/nav.tsx`
- `web/src/components/states.tsx`
- `web/src/lib/format.ts`
- `web/src/lib/format.test.ts`

## Notes
**Blocks every other Lane C ticket** — do this one first.

The formatter is worth doing properly here. Inconsistent money formatting across screens is the
fastest way to make a finance app feel amateur. It takes integer cents because that's the wire
format; there is no place in `web/` that handles a decimal money value.

Read the `dataviz` skill before establishing the colour scale — the chart palette and the app
palette need to be one system, and retrofitting that is expensive.
