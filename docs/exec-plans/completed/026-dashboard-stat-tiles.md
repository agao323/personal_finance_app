# 026 — Dashboard stat tiles: net worth and runway
Status: done
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 014, 016
Read first: docs/PRODUCT.md#burn-and-runway

## Goal
The top of the dashboard: current net worth with period delta, and months of runway with burn
rate.

## Acceptance criteria
- [x] Net worth tile with value, absolute and percentage change vs. prior month
- [x] Runway tile with months remaining and trailing gross burn
- [x] Assets and liabilities subtotals
- [x] **Mine / Household toggle**, persisted across navigation
- [x] Loading skeletons and error states — not spinners over blank space
- [x] Values typed from `api-types.ts`. No hand-written response shapes.
- [x] Tests: component tests against MSW fixtures covering loaded, loading, error, empty-history, and household-vs-mine states

## Files
- `web/src/app/(dashboard)/page.tsx`
- `web/src/components/stat-tile.tsx`
- `web/src/components/tiles/net-worth.tsx`
- `web/src/components/tiles/runway.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

Read the `dataviz` skill before writing the stat tile component — it covers stat tiles and KPI
rows specifically, and getting the visual system consistent from the first tile is much cheaper
than retrofitting it.

The burn figure is gross spend and the tile copy should say so. A runway number whose definition
is ambiguous is worse than no runway number.
