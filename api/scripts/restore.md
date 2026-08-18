# Restoring from a backup

Written to be runnable by someone who did not write it, on the worst day. Every command
is literal; nothing is left as an exercise.

**An untested backup is not a backup.** Run this end to end at least once before the
database holds anything you would miss, and again after any change to `backup.py`.

## What you need

| | Where it lives |
|---|---|
| `BACKUP_ENCRYPTION_KEY` | Your password manager. **Not** in Neon, R2, Fly, or this repo. |
| R2 credentials | Cloudflare dashboard → R2 → Manage API tokens |
| A scratch database | A Neon **branch** of the real project — see below |

If the encryption key is gone, the backups are gone. That is the trade recorded in
[ADR 0004](../../docs/adr/0004-backups.md).

## 1. Create a scratch target

Never restore over the real database, including when the real database is the thing
that is broken. A Neon branch is instant, free, and isolated:

```
Neon console → your project → Branches → New branch
  name: restore-test
  parent: production
```

Copy its **pooled** connection string.

## 2. Fetch the most recent backup

```bash
export R2_BUCKET=pfa-backups
export R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
export AWS_ACCESS_KEY_ID=<r2 access key>
export AWS_SECRET_ACCESS_KEY=<r2 secret>

# Keys sort chronologically, so the last line is the newest.
aws s3 ls "s3://$R2_BUCKET/" --endpoint-url "$R2_ENDPOINT_URL" | sort | tail -5

aws s3 cp "s3://$R2_BUCKET/pfa-2026-08-18T03-00-00Z.sql.enc" ./backup.enc \
  --endpoint-url "$R2_ENDPOINT_URL"
```

## 3. Decrypt

```bash
cd api
BACKUP_ENCRYPTION_KEY='<the key>' uv run python -c "
import os, pathlib
from scripts.backup import decrypt
data = pathlib.Path('../backup.enc').read_bytes()
pathlib.Path('../backup.dump').write_bytes(decrypt(data, os.environ['BACKUP_ENCRYPTION_KEY']))
print('decrypted', len(data), '->', pathlib.Path('../backup.dump').stat().st_size, 'bytes')
"
```

Fernet is authenticated, so a corrupted or tampered archive fails here rather than
producing a subtly wrong database.

## 4. Restore into the branch

```bash
pg_restore \
  --dbname "postgresql://<branch connection string>" \
  --no-owner --no-acl --clean --if-exists \
  ../backup.dump
```

`--no-owner --no-acl` because the branch has different role names than the dump was
taken under. `--clean --if-exists` makes the restore repeatable.

## 5. Verify — this is the step that matters

A restore that completes is not a restore that worked.

```bash
psql "postgresql://<branch connection string>" <<'SQL'
-- Row counts across every table that holds real content.
SELECT 'accounts', count(*) FROM accounts
UNION ALL SELECT 'ownership_stakes', count(*) FROM ownership_stakes
UNION ALL SELECT 'balance_snapshots', count(*) FROM balance_snapshots
UNION ALL SELECT 'transactions', count(*) FROM transactions
UNION ALL SELECT 'categories', count(*) FROM categories;

-- A spot-checked aggregate. Compare against the same query on production.
SELECT sum(balance) AS total_raw_balance,
       max(as_of)   AS most_recent_snapshot
FROM balance_snapshots;

-- The schema arrived, not just the rows.
SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
SQL
```

Run the same three queries against production and compare. Counts and the aggregate
must match, allowing for anything written since the backup was taken.

## 6. Point the app at it, briefly

The strongest check is the app itself:

```bash
fly secrets set -a pfa-api DATABASE_URL='<branch pooled connection string>'
curl -fsS https://allofmymoney.com/api/ready
curl -fsS https://allofmymoney.com/api/net-worth
```

Net worth should match what production showed. **Then put the real connection string
back** — this step is the one you must not forget:

```bash
fly secrets set -a pfa-api DATABASE_URL='<production pooled connection string>'
```

## 7. Clean up

```bash
rm -f ../backup.enc ../backup.dump
```

Delete the `restore-test` branch in the Neon console. A branch holding a full copy of
your finances is a second thing to protect.

## Recording the drill

Add a line to the table in [ADR 0004](../../docs/adr/0004-backups.md) with the date,
the backup restored, and whether the counts matched. A restore nobody wrote down is a
restore nobody can prove happened.
