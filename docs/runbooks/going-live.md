# Going live

Everything that needs an account, a dashboard, or a payment method — in the order it
has to happen. All the code is written and merged; none of the steps below can be done
from a script.

Each ticket's own file has the reasoning. This is the sequence.

**Rules that apply throughout:**

- Never paste a secret into a chat, a commit, or a log. Every command below either
  reads a value you already hold or generates one in your shell.
- Verify each step before moving on. Half of these are security boundaries, and the
  failure mode of an unverified one is that it looks fine.

---

## A · Make the deployed app match the code

**Why first:** `pfa-web` is suspended and `pfa-api` is running a build from before
passkeys existed. Nothing else can be verified against a stale deployment.

### A1. Set the three missing API secrets

```bash
fly secrets set -a pfa-api \
  SESSION_SECRET="$(openssl rand -base64 32)" \
  RP_ID=allofmymoney.com \
  WEB_ORIGIN=https://allofmymoney.com
```

`RP_ID` **must be the apex**, not a subdomain. A passkey scoped to
`app.allofmymoney.com` stops working permanently the moment anything moves — and you
already moved to the apex once, which was only free because no passkey existed yet.

`SESSION_SECRET` is generated in your shell and never printed. The API now refuses to
start on the development default when the origin is https, so a missing value fails the
deploy loudly instead of signing cookies with a key that is in the repo.

### A2. Deploy both apps

```bash
make deploy-api
make deploy-web
```

API first — the web app reaches it over the private network and a deploy against a
missing API is a broken health check.

### A3. Verify

```bash
fly ips list -a pfa-api          # expect NO v4 or v6 entry. private_v6 is correct.
curl -fsS https://allofmymoney.com/api/ready
```

`fly ips list` returning no public address is most of the security posture in one
command. If a public IP appears, stop and fix that before anything else.

---

## B · Ticket 036 · Cloudflare Access

**Why now:** the app is currently readable by anyone who knows the hostname. This is
the ticket that closes that, and it gates ticket 024.

### B1. Create the Access application

Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → Add an
application → **Self-hosted**.

- **Application domain:** `allofmymoney.com`, path `*`
- **Session duration:** 24 hours is reasonable; it is independent of the app's own
  session.

### B2. Add the policy

- **Action:** Allow
- **Rule type:** **Emails** — list your address explicitly. Add your partner's when
  they join.

Not an **Emails ending in** rule. `@gmail.com` is not a household, and that is the
single most common way an Access policy ends up allowing the internet.

### B3. Copy the Application Audience tag

On the application's **Overview** tab. Then:

```bash
fly secrets set -a pfa-web CF_ACCESS_AUD=<the aud tag>
```

Setting a secret restarts the app, so this deploys itself.

Check the team domain too — `fly.web.toml` assumes
`allofmymoney.cloudflareaccess.com`. If Cloudflare gave you a different one, edit that
file and redeploy. Both variables must be present: an audience with no issuer accepts a
token from any Access tenant, and an issuer with no audience accepts one minted for a
different application.

### B4. Verify — all six checks

Run every step in [`access-verification.md`](access-verification.md). Steps 3 and 4 are
the ones that actually prove the lock; the rest are confirmation.

Use a **different browser or a fresh profile** for the unauthenticated check. A private
window is not enough if you are signed in to Cloudflare in that profile.

### B5. Record the results

Fill in the table at the bottom of [`../adr/0002-auth.md`](../adr/0002-auth.md). "It
should be private" is not the same as having checked, and in six months the table is
the only evidence either way.

### B6. Register your passkey

Visit `https://allofmymoney.com/login` and choose **Register a passkey**.

This works only while no passkey exists. The window closes permanently on the first
registration — after that, sign in from a device you have already registered. Behind
Access the whole time, so the window is not an exposure.

---

## C · Ticket 017 · Backups and a tested restore

**Why now:** moving out of Google Sheets is a durability *downgrade* until a restore has
actually been performed. This gates 024 for that reason.

### C1. Create the R2 bucket

Cloudflare dashboard → **R2** → Create bucket → name it `pfa-backups`.

Then **Manage API tokens** → Create token, scoped to that bucket, **Object Read &
Write**. Note the **account ID** — the endpoint URL is
`https://<account-id>.r2.cloudflarestorage.com`.

### C2. Generate the encryption key

```bash
cd api && uv run python scripts/backup.py --print-key
```

**Put it in your password manager and nowhere else.** Losing it loses every backup —
that is the deliberate trade in [ADR 0004](../adr/0004-backups.md). Do not commit it,
do not email it to yourself, do not leave it in shell history you sync.

### C3. Create the dead-man's switch

[healthchecks.io](https://healthchecks.io), free tier. **Period: 1 day. Grace: 6
hours.**

The generous grace is deliberate: GitHub delays scheduled runs under load, and a tight
window would alert on lateness rather than failure — which trains you to ignore it.

Copy the ping URL.

### C4. Add seven GitHub Actions secrets

Repository → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `BACKUP_DATABASE_URL` | The **unpooled** Neon string |
| `R2_BUCKET` | `pfa-backups` |
| `R2_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | From the R2 token |
| `R2_SECRET_ACCESS_KEY` | From the R2 token |
| `BACKUP_ENCRYPTION_KEY` | From step C2 |
| `BACKUP_HEALTHCHECK_URL` | From step C3 |

**Unpooled**, not pooled. `pg_dump` opens one long connection and PgBouncer is the
wrong thing in front of it. The pooled string is the one with `-pooler` in the host;
you want the other one.

### C5. Trigger it once by hand

Actions → **Nightly backup** → Run workflow. Then confirm an object appears in the R2
bucket.

The nightly run has been failing on schedule since the workflow landed, for want of
these secrets. It should go green now.

### C6. Run the restore drill

Follow [`../../api/scripts/restore.md`](../../api/scripts/restore.md) end to end. It
restores into a **Neon branch of the real project** — which is what branches are good
for, and is a different question from the demo's isolation, where a branch is too weak.

Section 5 is the point: row counts and a spot-checked aggregate. A restore that ran
without proving it restored the right data is not a tested restore.

### C7. Record the drill

Fill in the table in [ADR 0004](../adr/0004-backups.md). **This table, not the backup
job, is ticket 017's acceptance criterion.**

---

## D · Ticket 024 · Import your spreadsheet history

**Only after B and C.** This is the step that puts real financial data in, and it needs
authentication in front of it and a proven restore behind it.

### D1. Export and place the file

Export the sheet to CSV, into `data/`. That directory is gitignored and the file never
leaves it.

### D2. Write the mapping

```bash
cp api/config/sheet_mapping.example.toml api/config/sheet_mapping.toml
```

Edit it to match your sheet's column headers. **Column names and account names only.**
A number in that file is a value pasted out of the real sheet — the loader rejects it
outright, because the mapping is committed and `data/` is not.

### D3. Create the accounts first

Through the app at `/accounts/new`. The script records balances; it does not invent
accounts, and it refuses a mapping naming one that does not exist.

### D4. Dry run until it reconciles

```bash
cd api && uv run python scripts/import_sheet_history.py ../data/history.csv
```

Nothing is written without `--write`. Read the output:

- **Unmapped columns** — if any is an account, it is missing from every figure.
- **Mismatches** — each names a date, the sheet's total, what the import computed, and
  the difference. A disagreement is almost always a column mapped to the wrong account.

Fix the mapping and re-run until it reports no mismatches. This is the step that
catches an import which would otherwise produce a complete, plausible, entirely wrong
history.

### D5. Write

```bash
cd api && uv run python scripts/import_sheet_history.py ../data/history.csv --write
```

Every write is an upsert on `(account, date)`, so re-running after a correction is
safe and changes only what actually differs.

### D6. Look at it

Open the app. Check the net worth chart against what the sheet said. **Then stop
updating the sheet** — that is the project's definition of done.

---

## E · Ticket 037 · The public demo

Independent of everything above. Do it whenever.

### E1. Create a second Neon project

**A project, not a branch.** A branch shares an account and credentials with its
parent, and this is the one boundary that must not be weak — see
[ADR 0003](../adr/0003-demo-isolation.md).

Copy its **pooled** connection string.

### E2. Create the Fly apps

```bash
fly apps create pfa-demo-api
fly apps create pfa-demo-web
fly secrets set -a pfa-demo-api \
  DATABASE_URL='<the demo project pooled URL>' \
  SESSION_SECRET="$(openssl rand -base64 32)"
make deploy-demo
fly certs add -a pfa-demo-web demo.allofmymoney.com
```

### E3. Seed it

```bash
fly ssh console -a pfa-demo-api -C "python scripts/seed_synthetic.py"
```

The seed refuses to run against a database whose marker says the data is real, so a
mistyped app name fails rather than overwriting anything.

### E4. DNS and caching

Cloudflare → DNS: a `demo` CNAME to the Fly app, **proxied**.

Cloudflare → Caching → Cache Rules: a rule on `demo.allofmymoney.com` with a long edge
TTL. The dataset is static and read-only, so this is safe — and it does two jobs: keeps
demo compute inside Neon's free allowance when crawlers hit an indexed public site, and
removes the cold start that would otherwise leave a first visitor on a blank page for
several seconds.

**Then confirm no cache rule matches the apex.** The real app must never be
edge-cached.

### E5. Turn the guard on

Add `DEMO_DATABASE_URL` as a GitHub Actions secret. That switches
`.github/workflows/demo-guard.yml` from skipping to enforcing — it asserts the two
databases are different Neon *projects*, on every push and weekly.

### E6. Verify and record

Run the five checks in ADR 0003's table. The two that matter most:

- Connect to the demo database directly and confirm only synthetic data is present.
- Confirm the demo's credentials are **rejected** by the real database.

### E7. Add the demo link to the README

The "Live demo" line in ticket 039 is waiting on this.

---

## F · Ticket 039 · Clean-clone verification

The last open criterion, and the one with teeth.

On a machine with **nothing cached** — no Docker layers, no pnpm store, no uv cache; a
fresh VM or a colleague's laptop — clone the repo and follow the README's "Running it
locally" section **literally**, not from memory.

```bash
git clone https://github.com/agao323/personal_finance_app.git
cd personal_finance_app
make dev
# in another terminal
make seed
```

Then open http://localhost:3000, register a passkey, and confirm the dashboard renders
with data.

A README that drifted from reality is worse than no README — it sends you debugging a
setup that was never going to work. Every path, `make` target and doc link in it has
been checked to exist, but that was checked on a warm machine, which is not the same
test.

Tick the criterion in ticket 039 when it passes, and fix the README where it does not.

---

## Order summary

| | Depends on | Unblocks |
|---|---|---|
| **A** Secrets and deploy | — | everything |
| **B** Cloudflare Access | A | D |
| **C** Backups and restore drill | — | D |
| **D** Sheet import | B, C | done |
| **E** Demo | A | 039's demo link |
| **F** Clean clone | — | — |

C and E can run in parallel with B. D is the only one that waits on two things, and it
waits on them for the same reason: real data needs a lock in front of it and a proven
restore behind it.
