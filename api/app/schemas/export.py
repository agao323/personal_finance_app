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
    """Every table. **Not a selection** — see the guard test.

    It used to be a selection, and the selection went stale: `institutions`, `card_perks`,
    `perk_redemptions` and `import_mappings` were all missing, because the export was
    written before the cards feature and nobody extended it while the ticket went on
    claiming "the full dataset". A test now fails when a mapped table is absent from here.
    """

    meta: ExportMeta
    institutions: list[dict[str, Any]]
    accounts: list[dict[str, Any]]
    ownership_stakes: list[dict[str, Any]]
    balance_snapshots: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    categorization_rules: list[dict[str, Any]]
    import_mappings: list[dict[str, Any]]
    card_perks: list[dict[str, Any]]
    perk_redemptions: list[dict[str, Any]]
    users: list[dict[str, Any]]
    data_marker: list[dict[str, Any]]
    # The advisor's tables (ticket 095). Transcripts expire after 30 days, so a backup
    # holds at most that much — and a conversation deleted today survives in any backup
    # file written before today, which the delete confirmation says.
    advisor_conversations: list[dict[str, Any]]
    advisor_turns: list[dict[str, Any]]
    advisor_messages: list[dict[str, Any]]
    advisor_tool_calls: list[dict[str, Any]]
    advisor_usage: list[dict[str, Any]]
