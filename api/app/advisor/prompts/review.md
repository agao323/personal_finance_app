This turn is the monthly review of {month_label} ({first_day} to {last_day}), asked for by the
person reading it. Look things up before writing; answer from what the lookups return.

Call these, in any order:

- `findings_list` — what the findings engine flags, in this conversation's view.
- `spend_compare` — {month_label} against the month before it: `period_a` `custom`
  {first_day} to {last_day}, `period_b` `custom` {prior_first} to {prior_last}.
- `cashflow_get` — the last few complete months of income, spending and savings rate.
- `cards_value` — credits used and missed this year, and what each card is worth.
- `networth_explain_change` — net worth from {first_day} to {next_first}, and why it moved.
- `runway_get` — how many months the cash would cover.

Then write the review in these sections, in this order, each under its heading in bold on a line
of its own: **Spending**, **Subscriptions**, **Credits**, **Runway**, **Net worth**.

- **Spending**: {month_label} against the month before, the largest changes by category, and any
  spending limit passed or on pace to be passed.
- **Subscriptions**: new, lapsed or changed recurring charges the findings name; if there are
  none, say so in one line.
- **Credits**: card credits used and missed, and anything expiring soon.
- **Runway**: months of cash at recent spending, against the emergency-fund goal if there is one.
- **Net worth**: the change over the month and the accounts that moved it.

Keep each section to a few sentences. End with at most three things worth doing, drawn from the
findings, each pointing to the screen where it can be done. Nothing here changes any data.
