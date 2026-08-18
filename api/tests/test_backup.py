"""Tests for the backup script and the export endpoint.

The backup job runs unattended on a schedule, which means nothing exercises it between
the day it is written and the day it is needed. These tests are the only thing standing
between "we have backups" and "we had backups".
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.balances import record_balance
from app.services.ownership import create_initial_stake
from scripts.backup import (
    RETENTION_DAYS,
    Config,
    decrypt,
    encrypt,
    object_key,
    parse_key_date,
    ping,
    prune,
)

NOW = dt.datetime(2026, 8, 18, 3, 0, 0, tzinfo=dt.UTC)


# ── encryption ────────────────────────────────────────────────────────────────


def test_encryption_round_trips() -> None:
    key = Fernet.generate_key().decode()
    payload = b"PGDMP\x00\x01binary archive bytes\xff"

    assert decrypt(encrypt(payload, key), key) == payload


def test_ciphertext_does_not_contain_the_plaintext() -> None:
    """Obvious, and worth asserting: the point is that R2 never holds readable data."""
    key = Fernet.generate_key().decode()
    payload = b"balance 12345.67"

    assert b"12345.67" not in encrypt(payload, key)


def test_the_wrong_key_cannot_decrypt() -> None:
    payload = encrypt(b"secret", Fernet.generate_key().decode())

    with pytest.raises(InvalidToken):
        decrypt(payload, Fernet.generate_key().decode())


def test_tampered_ciphertext_is_rejected() -> None:
    """Fernet is authenticated, so a corrupted archive fails loudly on restore."""
    key = Fernet.generate_key().decode()
    payload = bytearray(encrypt(b"important", key))
    payload[-5] ^= 0xFF

    with pytest.raises(InvalidToken):
        decrypt(bytes(payload), key)


# ── object keys ───────────────────────────────────────────────────────────────


def test_keys_sort_chronologically() -> None:
    """Lexical order must match time order, or retention picks the wrong files."""
    earlier = object_key(dt.datetime(2026, 8, 9, 3, tzinfo=dt.UTC))
    later = object_key(dt.datetime(2026, 8, 10, 3, tzinfo=dt.UTC))

    assert earlier < later


def test_key_round_trips_through_its_timestamp() -> None:
    assert parse_key_date(object_key(NOW)) == NOW


@pytest.mark.parametrize(
    "key", ["notes.txt", "pfa-nonsense.sql.enc", "pfa-2026-08-18T03-00-00Z.tar", ""]
)
def test_foreign_keys_are_not_parsed(key: str) -> None:
    assert parse_key_date(key) is None


# ── retention ─────────────────────────────────────────────────────────────────


class FakeS3:
    """Enough of the S3 client to exercise pruning without a network."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)
        self.deleted: list[str] = []

    def get_paginator(self, _operation: str) -> FakeS3:
        return self

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"Contents": [{"Key": key} for key in self.keys]}]

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.deleted.append(Key)


def test_prune_deletes_only_what_is_past_retention() -> None:
    fresh = object_key(NOW - dt.timedelta(days=RETENTION_DAYS - 1))
    stale = object_key(NOW - dt.timedelta(days=RETENTION_DAYS + 1))
    client = FakeS3([fresh, stale])

    removed = prune(client, "bucket", NOW)

    assert removed == [stale]
    assert client.deleted == [stale]


def test_prune_leaves_unrecognised_objects_alone() -> None:
    """This job must never be the reason something unexpected disappears."""
    client = FakeS3(["someone-elses-file.txt", "pfa-notes.md"])

    assert prune(client, "bucket", NOW) == []
    assert client.deleted == []


def test_prune_keeps_a_backup_exactly_at_the_boundary() -> None:
    boundary = object_key(NOW - dt.timedelta(days=RETENTION_DAYS))
    client = FakeS3([boundary])

    assert prune(client, "bucket", NOW) == []


# ── configuration ─────────────────────────────────────────────────────────────


def test_missing_configuration_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backup that runs with a missing setting and does nothing is the whole fear."""
    for name in (
        "DATABASE_URL",
        "R2_BUCKET",
        "R2_ENDPOINT_URL",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "BACKUP_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SystemExit, match="missing required environment"):
        Config.from_env()


def test_healthcheck_url_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("DATABASE_URL", "postgresql://u:p@h/d"),
        ("R2_BUCKET", "b"),
        ("R2_ENDPOINT_URL", "https://r2"),
        ("R2_ACCESS_KEY_ID", "k"),
        ("R2_SECRET_ACCESS_KEY", "s"),
        ("BACKUP_ENCRYPTION_KEY", Fernet.generate_key().decode()),
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("BACKUP_HEALTHCHECK_URL", raising=False)

    assert Config.from_env().healthcheck_url is None


def test_a_failing_healthcheck_ping_does_not_break_the_backup() -> None:
    """The monitor must never be able to take the thing it monitors down."""
    ping("http://127.0.0.1:1/nonexistent")  # refused immediately; must not raise


def test_ping_is_a_no_op_without_a_url() -> None:
    ping(None)


# ── export ────────────────────────────────────────────────────────────────────


def test_export_returns_every_table(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("1234.56"))

    body = client.get("/export").json()

    assert body["meta"]["account_count"] == 1
    assert body["meta"]["snapshot_count"] == 1
    assert len(body["ownership_stakes"]) == 1
    assert body["categories"]  # seeded by the migration


def test_export_renders_money_as_a_string_not_a_float(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """A float would quietly round the balances the export exists to preserve."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("1234.56"))

    snapshot = client.get("/export").json()["balance_snapshots"][0]

    assert snapshot["balance"] == "1234.56"
    assert isinstance(snapshot["balance"], str)


def test_export_includes_stake_effective_dates(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    """Balances alone cannot reconstruct net worth without the stakes that scaled them."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1), Decimal("50"))

    stake = client.get("/export").json()["ownership_stakes"][0]

    assert stake["effective_from"] == "2026-01-01"
    assert stake["percentage"] == "50.00"


def test_export_on_an_empty_database(client: TestClient) -> None:
    body = client.get("/export").json()

    assert body["meta"]["account_count"] == 0
    assert body["accounts"] == []
