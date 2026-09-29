# 019 — Accounts, stakes, and balances API
Status: done
Wave: 2   Lane: B
Blocked by: 012, 018
Read first: docs/ARCHITECTURE.md#users-and-ownership, docs/ARCHITECTURE.md#data-model

## Goal
The full accounts surface — read and write. The ingestion path that works for every
institution including the ones no aggregator covers.

## Acceptance criteria
- [x] `GET /accounts` with current raw **and** ownership-adjusted balances, grouped by kind, with subtotals
- [x] `GET /accounts/{id}` including stake history and recent transactions
- [x] `GET /accounts/{id}/history` returning the snapshot series
- [x] `POST /accounts`, `PATCH /accounts/{id}` — including setting `closed_at`
- [x] **Creating an account writes its explicit 100% stake row** in the same transaction
- [x] `POST /accounts/{id}/balances` recording a snapshot via `services/balances.record_balance`
- [x] `POST /accounts/{id}/stakes` closing the prior stake and opening the new one atomically
- [x] Money as integer cents in every request and response; structured validation errors
- [x] Stale-flagged balances surfaced in the response so the UI can prompt an update
- [x] Tests: unit for request-model validation; functional for the stake transition, for raw-vs-adjusted values on a 50%-owned account, and for the 100%-stake-row-on-create invariant

## Files
- `api/app/routers/accounts.py`
- `api/app/schemas/account.py`
- `api/tests/test_api_accounts.py`

## Notes
Exposing both raw and ownership-adjusted values is the point — a 50%-owned asset should
visibly show both numbers, since that's the feature that makes this app different from an
off-the-shelf one.

Read and write live in one router file deliberately: Lane B owns `routers/accounts.py`
outright, so there's no lane boundary running through a single file.
