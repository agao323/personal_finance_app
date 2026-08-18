"""Pydantic schemas — the API contract.

These models *are* the contract. `make types` turns them into
`web/src/lib/api-types.ts`, and CI fails if the committed file drifts. Never
hand-write a response type on the frontend.
"""
