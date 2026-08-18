"""Full data export.

The app must never become a place data can only go into. That is both user-hostile and
insurance against losing interest in the project.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.schemas.common import Schema


class ExportMeta(Schema):
    generated_at: dt.datetime
    account_count: int
    snapshot_count: int
    transaction_count: int


class ExportRead(Schema):
    meta: ExportMeta
    accounts: list[dict[str, Any]]
    ownership_stakes: list[dict[str, Any]]
    balance_snapshots: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    categorization_rules: list[dict[str, Any]]
