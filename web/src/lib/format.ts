/**
 * Money and number formatting.
 *
 * Everything takes **integer cents**, because that is the wire format. There is no
 * place in `web/` that handles a decimal money value, and no place that divides one
 * by 100 on its own — do that here or the rounding differs by screen.
 *
 * The exact-currency path never performs floating-point division. `cents / 100` is
 * a double, and doubles cannot represent most two-decimal values exactly; formatting
 * from one is how a total ends up a cent away from the rows above it. Splitting the
 * integer instead is exact for every value up to `Number.MAX_SAFE_INTEGER`.
 *
 * Compact formatting is the deliberate exception: `$4.2M` is an approximation by
 * definition, so a float is fine there.
 */

const MINUS = "−";

export type Direction = "up" | "down" | "flat";

function split(cents: number): { negative: boolean; whole: number; fraction: number } {
  if (!Number.isFinite(cents)) throw new RangeError(`Not a finite amount: ${cents}`);
  if (!Number.isInteger(cents)) {
    throw new RangeError(
      `Money must be integer cents, got ${cents}. A fractional value here means ` +
        `something already divided by 100 — fix it at the source.`,
    );
  }

  const negative = cents < 0;
  const absolute = Math.abs(cents);
  const fraction = absolute % 100;
  // Exact integer division: the remainder is removed before dividing.
  const whole = (absolute - fraction) / 100;
  return { negative, whole, fraction };
}

const grouped = new Intl.NumberFormat("en-US");

/**
 * `$1,234.56`. Negatives use a typographic minus, not a hyphen.
 *
 * Accounting parentheses were rejected: they read as a footnote reference at a
 * glance, and this app shows negative deltas far more often than negative balances.
 */
export function formatCurrency(
  cents: number,
  options: { showCents?: boolean; signed?: boolean } = {},
): string {
  const { showCents = true, signed = false } = options;
  const { negative, whole, fraction } = split(cents);

  const body = showCents
    ? `$${grouped.format(whole)}.${String(fraction).padStart(2, "0")}`
    : `$${grouped.format(fraction >= 50 ? whole + 1 : whole)}`;

  if (negative) return `${MINUS}${body}`;
  return signed && cents !== 0 ? `+${body}` : body;
}

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/**
 * `$4.2M`. For tiles and axis ticks where the exact cent is noise.
 *
 * Under $10,000 the compact form saves nothing and loses precision, so it falls
 * through to whole dollars.
 */
export function formatCompactCurrency(cents: number, options: { signed?: boolean } = {}): string {
  const { negative, whole } = split(cents);

  if (whole < 10_000) return formatCurrency(cents, { showCents: false, ...options });

  const body = `$${compact.format(whole)}`;
  if (negative) return `${MINUS}${body}`;
  return options.signed && cents !== 0 ? `+${body}` : body;
}

/** `+$1,234.56` / `−$1,234.56` / `$0.00`. Zero is never signed. */
export function formatSignedCurrency(cents: number): string {
  return formatCurrency(cents, { signed: true });
}

/**
 * `50%` / `33.33%`. Takes **basis points**, matching the wire format.
 *
 * Trailing zeros are dropped: `5000` is `50%`, not `50.00%`. A stake that happens to
 * be a round number should not look more precise than it is.
 */
export function formatBps(bps: number, options: { decimals?: number } = {}): string {
  if (!Number.isInteger(bps)) throw new RangeError(`Basis points must be an integer, got ${bps}`);

  const { decimals = 2 } = options;
  const negative = bps < 0;
  const absolute = Math.abs(bps);
  const fraction = absolute % 100;
  const whole = (absolute - fraction) / 100;

  let body = String(whole);
  if (fraction !== 0 && decimals > 0) {
    body += `.${String(fraction).padStart(2, "0").slice(0, decimals).replace(/0+$/, "")}`;
  }
  return `${negative ? MINUS : ""}${body}%`;
}

export interface Delta {
  direction: Direction;
  /** Signed absolute change, already formatted. */
  absolute: string;
  /** Signed percentage change, or null when the prior period was zero. */
  percent: string | null;
}

/**
 * Change between two periods.
 *
 * `percent` is null rather than `Infinity` when the prior value was zero: going from
 * nothing to something is not a percentage, and rendering one would be a lie. The
 * caller shows the absolute change alone in that case.
 *
 * Percentage of a *negative* prior value is also null — "net worth improved by
 * −140%" is not a sentence anyone can act on.
 */
export function computeDelta(currentCents: number, priorCents: number): Delta {
  split(currentCents);
  split(priorCents);

  const change = currentCents - priorCents;
  const direction: Direction = change > 0 ? "up" : change < 0 ? "down" : "flat";

  let percent: string | null = null;
  if (priorCents > 0) {
    const ratio = (change / priorCents) * 100;
    const rounded = Math.round(ratio * 10) / 10;
    const sign = rounded > 0 ? "+" : rounded < 0 ? MINUS : "";
    percent = `${sign}${Math.abs(rounded).toFixed(1)}%`;
  }

  return { direction, absolute: formatSignedCurrency(change), percent };
}

const dateFormat = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

/** `Aug 18, 2026` from an ISO date. UTC, so a date never shifts by timezone. */
export function formatDate(iso: string): string {
  return dateFormat.format(new Date(`${iso}T00:00:00Z`));
}

export type DateGrain = "day" | "month";

const shortDate: Record<DateGrain, Intl.DateTimeFormat> = {
  day: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }),
  month: new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" }),
};

/**
 * `Aug 14` or `Aug 2026` — the axis-tick form of `formatDate`.
 *
 * The grain is the caller's, because it depends on how much time is on screen
 * rather than on the date: a day is noise across three years, and a bare month is
 * ambiguous across three weeks.
 */
export function formatShortDate(iso: string, grain: DateGrain): string {
  return shortDate[grain].format(new Date(`${iso}T00:00:00Z`));
}

/** `3 months ago` — for saying how stale a carried-forward balance is. */
export function formatAge(iso: string, now: Date = new Date()): string {
  const then = new Date(`${iso}T00:00:00Z`);
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);

  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;

  const months = Math.floor(days / 30);
  if (months === 1) return "1 month ago";
  if (months < 12) return `${months} months ago`;

  const years = Math.floor(days / 365);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}
