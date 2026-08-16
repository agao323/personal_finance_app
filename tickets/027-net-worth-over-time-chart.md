# 027 — Net worth over time chart
Status: todo
Wave: 2   Lane: C
Blocked by: 026
Integrates with: 014
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The primary chart: ownership-adjusted net worth over time, with range selection and an
assets/liabilities split view.

## Acceptance criteria
- [ ] Line or area chart over `GET /net-worth/series`
- [ ] Range selector: 3M, 6M, 1Y, YTD, All
- [ ] Toggle between total and assets/liabilities split
- [ ] Respects the Mine / Household toggle from 026
- [ ] Accessible tooltip with formatted values and dates; keyboard navigable
- [ ] Handles sparse, empty, and single-point history without breaking layout
- [ ] Renders correctly in light and dark mode
- [ ] Tests: component tests for range switching, empty series, single-point series, and tooltip content

## Files
- `web/src/components/charts/net-worth-chart.tsx`
- `web/src/components/charts/range-selector.tsx`
- `web/src/components/charts/net-worth-chart.test.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

Read the `dataviz` skill first — chart colours, axis treatment, tooltip behaviour, and dark
mode handling are covered there, and this is the chart the whole app is judged on.

The single-point case is not hypothetical: it's what the chart shows on day one, before the
sheet history import runs. It should look deliberate, not broken.
