"""Nightly encrypted backup of the production database to Cloudflare R2.

Runs from GitHub Actions rather than inside the API image: the job needs `pg_dump`,
`boto3`, and an encryption key, none of which the runtime image should carry, and a
scheduled workflow is one file against a Fly cron machine's several.

**The dead-man's-switch is not garnish.** A backup job that silently stops working is
worse than no backup, because it is trusted. The job pings a healthcheck URL on
success; if that ping stops arriving, the monitor raises an alert. Nothing else would
notice — a failing cron is invisible by construction.

**Encryption happens before upload, with a key held outside both Neon and R2.** The
threat this addresses is the object store itself, listed second in the threat model:
backups at rest are a complete financial picture in a single file. Losing the key
means losing the backups, which is the trade — see docs/adr/0004-backups.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass

import boto3
from cryptography.fernet import Fernet

#: Backups older than this are deleted on each run.
RETENTION_DAYS = 30

#: Object keys look like `pfa-2026-08-18T03-00-00Z.sql.enc`.
KEY_PREFIX = "pfa-"
KEY_SUFFIX = ".sql.enc"


@dataclass(frozen=True)
class Config:
    database_url: str
    bucket: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    encryption_key: str
    healthcheck_url: str | None

    @classmethod
    def from_env(cls) -> Config:
        """Read configuration, failing loudly on anything missing.

        A backup that runs with a missing setting and silently does nothing is the
        exact failure this whole script is defending against.
        """
        required = {
            "DATABASE_URL": None,
            "R2_BUCKET": None,
            "R2_ENDPOINT_URL": None,
            "R2_ACCESS_KEY_ID": None,
            "R2_SECRET_ACCESS_KEY": None,
            "BACKUP_ENCRYPTION_KEY": None,
        }
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise SystemExit(f"backup: missing required environment: {', '.join(missing)}")

        return cls(
            database_url=os.environ["DATABASE_URL"],
            bucket=os.environ["R2_BUCKET"],
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            encryption_key=os.environ["BACKUP_ENCRYPTION_KEY"],
            healthcheck_url=os.environ.get("BACKUP_HEALTHCHECK_URL") or None,
        )


def object_key(now: dt.datetime) -> str:
    """A sortable, collision-free key. Lexical order matches chronological order."""
    return f"{KEY_PREFIX}{now.strftime('%Y-%m-%dT%H-%M-%SZ')}{KEY_SUFFIX}"


def parse_key_date(key: str) -> dt.datetime | None:
    """The timestamp encoded in a key, or ``None`` if it is not one of ours."""
    if not key.startswith(KEY_PREFIX) or not key.endswith(KEY_SUFFIX):
        return None
    stamp = key[len(KEY_PREFIX) : -len(KEY_SUFFIX)]
    try:
        return dt.datetime.strptime(stamp, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def dump(database_url: str) -> bytes:
    """`pg_dump` as a custom-format archive.

    Custom format rather than plain SQL: `pg_restore` can then restore selectively and
    in parallel, and it compresses on the way out. `--no-owner` and `--no-acl` because
    a restore into a Neon branch has different role names and would otherwise fail on
    ownership statements that have nothing to do with the data.
    """
    # SQLAlchemy's +psycopg suffix is not a libpq URL scheme.
    libpq_url = database_url.replace("postgresql+psycopg://", "postgresql://")

    result = subprocess.run(
        ["pg_dump", "--format=custom", "--no-owner", "--no-acl", libpq_url],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.decode(errors='replace')}")
    if not result.stdout:
        raise RuntimeError("pg_dump produced an empty archive")
    return result.stdout


def encrypt(payload: bytes, key: str) -> bytes:
    return Fernet(key.encode()).encrypt(payload)


def decrypt(payload: bytes, key: str) -> bytes:
    return Fernet(key.encode()).decrypt(payload)


def _client(config: Config):  # type: ignore[no-untyped-def]
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
    )


def prune(client, bucket: str, now: dt.datetime) -> list[str]:  # type: ignore[no-untyped-def]
    """Delete backups older than the retention window. Returns the keys removed.

    Keys that do not parse are left alone rather than deleted — this job should never
    be the reason something unexpected in the bucket disappears.
    """
    cutoff = now - dt.timedelta(days=RETENTION_DAYS)
    removed: list[str] = []

    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            stamp = parse_key_date(key)
            if stamp is not None and stamp < cutoff:
                client.delete_object(Bucket=bucket, Key=key)
                removed.append(key)

    return removed


def ping(url: str | None, *, failed: bool = False) -> None:
    """Check in with the dead-man's-switch.

    A failure ping goes to `<url>/fail`, so the monitor alerts immediately rather than
    waiting for the next missed window.
    """
    if not url:
        return
    target = f"{url.rstrip('/')}/fail" if failed else url
    try:
        urllib.request.urlopen(target, timeout=10)
    except OSError as error:
        # Never let the monitor take the backup down with it.
        print(f"backup: healthcheck ping failed: {error}", file=sys.stderr)


def run(config: Config, now: dt.datetime | None = None) -> str:
    """Dump, encrypt, upload, prune. Returns the key written."""
    now = now or dt.datetime.now(dt.UTC)

    archive = encrypt(dump(config.database_url), config.encryption_key)
    key = object_key(now)

    client = _client(config)
    client.put_object(Bucket=config.bucket, Key=key, Body=archive)
    removed = prune(client, config.bucket, now)

    print(f"backup: wrote {key} ({len(archive):,} bytes encrypted)")
    if removed:
        print(f"backup: pruned {len(removed)} beyond {RETENTION_DAYS} days")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-key",
        action="store_true",
        help="generate a new encryption key and exit (does not touch the database)",
    )
    args = parser.parse_args()

    if args.print_key:
        print(Fernet.generate_key().decode())
        return

    config = Config.from_env()
    try:
        run(config)
    except Exception as error:
        ping(config.healthcheck_url, failed=True)
        raise SystemExit(f"backup: FAILED: {error}") from error

    ping(config.healthcheck_url)


if __name__ == "__main__":
    main()
