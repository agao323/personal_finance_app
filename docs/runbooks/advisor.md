# The advisor

Switching it on, switching it off, keeping it cheap, and what to do when something looks wrong.
Every step here needs an account, a dashboard or a secret, so none of it can be done from a
script or a session. Ticket 107 has the gates; docs/ADVISOR.md has the design.

**Rules that apply throughout:**

- The model key lives **only** as a Fly secret on `pfa-api`. Never in `pfa-web`, never in either
  demo app, never in a file. `scripts/check_no_model_key_outside_api.sh` fails CI if the name
  appears where it must not.
- Never paste a key into a chat, a commit, a ticket or a log. Commands below read it from your
  shell.
- Evals use the **eval** key (`EVAL_ANTHROPIC_API_KEY`, the `pfa-eval` workspace). Production
  uses the **production** key. Neither is ever the other.

---

## 1 · Before the first switch-on

### 1a. Gates

All three recorded in `docs/DECISIONS.md` before going further:

1. ADR 0008's restore drill, run against production.
2. ADR 0009 accepted — with the eval results from step 1c in hand.
3. Ticket 103 done (it is: Sentry withholds locals and exception messages; logs carry ids only).

### 1b. Two Anthropic workspaces

In the Anthropic Console:

| Workspace | Key goes to | Spend limit |
|---|---|---|
| `pfa-prod` | `pfa-api` as `ANTHROPIC_API_KEY` | **$25 / month** |
| `pfa-eval` | your shell as `EVAL_ANTHROPIC_API_KEY`, for `make eval` only | your choice, e.g. $15 / month |

The provider-side limit is the one that holds if every cap in the code fails. The app's own
monthly cap is $20 (`ADVISOR_MONTHLY_CAP_CENTS=2000`), deliberately under it.

### 1c. A passing eval at what you will deploy

```bash
export EVAL_ANTHROPIC_API_KEY=…   # from the pfa-eval workspace, in this shell only
make eval provider=anthropic n=3
```

About $20 at `n=3`. It prints pass rates against the thresholds and exits non-zero below any of
them. Record the run in docs/ADVISOR.md#eval-runs: date, model and effort, prompt version (the
report has it), cases × repeats, pass rates, ungrounded figures, cost.

Then refresh the demo's recorded examples from that run and review the diff:

```bash
make eval-examples
git diff web/src/lib/advisor-examples.json
```

---

## 2 · Switch on

```bash
fly secrets set -a pfa-api ANTHROPIC_API_KEY="$PFA_PROD_ANTHROPIC_KEY" ADVISOR_ENABLED=true
```

Setting secrets restarts the machines. Then, signed in through Cloudflare, check in order:

1. `https://allofmymoney.com/api/advisor/status` → `"enabled": true`, `"reason": null`.
2. **Streaming through every hop.** Open `https://allofmymoney.com/api/advisor/stream-check`
   in the browser's network tab: three heartbeats about a second apart, not all at once at the
   end. If they arrive together, something between the browser and the app is buffering —
   Cloudflare's "Rocket Loader" or a compression rule on that path are the usual suspects.
   Record the timings in ticket 107.
3. Ask one question on `/advisor`. The answer should stream, its figures should carry the
   dotted "verified" underline, and a source line should sit under it.

---

## 3 · Switch off — the kill switch

```bash
fly secrets set -a pfa-api ADVISOR_ENABLED=false
```

The next question is refused as "switched off" before any model call; nothing is spent. The
Insights panel keeps working — it never calls a model. Nothing else changes, and nothing is
lost: conversations stay until their 30 days run out.

**Drill it once** before relying on it (ticket 107): switch off, confirm a question is refused
and Insights still loads, switch back on. Record how long each restart took.

Switch off first and investigate second whenever anything looks wrong: a spend spike, an answer
that did something it should not, a suspected injection.

---

## 4 · Rotate the key

1. In the `pfa-prod` workspace, create a new key.
2. `fly secrets set -a pfa-api ANTHROPIC_API_KEY="$NEW_KEY"` (restarts the machines).
3. Ask one question to prove the new key works.
4. Delete the old key in the Console.

Rotate on any suspicion the key was exposed, and when anyone who could have seen it no longer
should.

---

## 5 · Spend

- **Month to date:** `/api/advisor/status` → `month_spent_cents` against `month_cap_cents`, or
  the status line on `/advisor`. It is computed from token counts and the price table in
  `api/app/advisor/pricing.py`; the Console's figure is the bill.
- **They should agree to within cents.** If they do not, the price table is out of date — check
  the model that served (`advisor_usage.model`; a refusal fallback can serve a different one)
  against platform.claude.com/docs/en/about-claude/pricing and add an effective-dated entry.
- **When the cap is reached**, questions are refused with the reset date (the first of next
  month, UTC); Insights keeps working. Raising the cap is a secret change:
  `fly secrets set -a pfa-api ADVISOR_MONTHLY_CAP_CENTS=…`.

---

## 6 · Retention and purge

Conversations go 30 days after their last turn; tool-call audit rows after 90 days; usage rows
after 13 months. Production purges at the start of every advisor request, so there is nothing to
schedule. To purge a **local** database by hand: `make advisor-purge`.

Deleting a conversation in the app removes it and its messages at once; its tool-call rows stay,
with the conversation id cleared, because an audit trail its subject can erase is not one.
Copies in backup files written before the delete remain until those files are.

---

## 7 · A suspected prompt injection

A merchant name, memo, rule pattern or note that tries to steer the model.

1. **Switch off** (section 3).
2. **Find the turn.** On `/advisor`, the answer's "show lookups" lists each call and its
   arguments. In the database, `advisor_tool_calls` has every call of that turn by `turn_id`,
   with its validated arguments and `withheld_count`.
3. **Find the source text.** A call with `withheld_count > 0` read at least one value the
   sanitiser withheld as instruction-like. Re-run that lookup's arguments against the data to
   find the row — the planted text is in `transactions.merchant` or `description`, an account or
   institution name, a category, a rule pattern, or a perk note.
4. **Fix or remove it** on the app's own screens: rename, recategorise, edit the note, or delete
   the transaction.
5. **Turn it into an eval case.** Add a synthetic version of the planted string to
   `api/evals/injection.yaml` with a new canary, and a question that reaches it to
   `api/evals/cases/injection.yaml`; run `make eval-fixtures` and the CI tests.
6. Switch back on.

Remember what the design rests on: there is nowhere for the model to send data — no fetch tool,
no server tools, no write tools, and a browser that will not load an outside image. Steering an
answer is the residual risk; leaking data is not the expected outcome.

---

## 8 · The monthly review

Inside the 30-day window, while the transcripts still exist:

1. On `/advisor`, read every answer flagged in the month (the flag and its note are on the
   answer). `advisor_turns.feedback = 'flagged'` lists them.
2. **Name each failure** — wrong tool, missed limitation, unverified figure, bad advice, a
   stale-data miss — and count them. Write the counts in ticket 080 or a dated note.
3. **Re-express each failure as a synthetic eval case** in `api/evals/cases/`, reproducing its
   shape with the eval world's made-up numbers. Never copy a real figure, merchant or account
   name into a case: the golden set grows from real failures without holding real data.
4. **Calibrate the advice grader** now and then: `make eval-label` shows recorded synthetic
   answers one at a time for a pass or fail; the next `make eval` reports how often the rubric
   agreed with you, and marks advice results untrusted below 90%.
5. Re-run `make eval` after any change of model, effort, system prompt or tool schema, and
   record it.
