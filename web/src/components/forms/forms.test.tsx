import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AccountForm,
  emptyAccountForm,
  percentToBps,
  validateAccount,
} from "@/components/forms/account-form";
import { BalanceForm, validateBalance } from "@/components/forms/balance-form";
import { StakeForm, lastDay, previewStakes } from "@/components/forms/stake-form";
import { accountDetail, server } from "@/test/msw";

const stakes = accountDetail.stakes;

beforeEach(() => {
  server.use(
    http.post("/api/accounts", () =>
      HttpResponse.json({ ...accountDetail, id: 42 }, { status: 201 }),
    ),
    http.post("/api/accounts/:id/balances", () => HttpResponse.json({}, { status: 201 })),
    http.post("/api/accounts/:id/stakes", () => HttpResponse.json({}, { status: 201 })),
  );
});

// ── validation ──────────────────────────────────────────────────────────────────

describe("validateAccount", () => {
  const base = emptyAccountForm(new Date("2026-08-18T00:00:00Z"));

  it("accepts a minimal account", () => {
    expect(validateAccount({ ...base, name: "Checking" }, null)).toEqual({});
  });

  it("requires a name", () => {
    expect(validateAccount(base, null).name).toBeTruthy();
  });

  it("mirrors the API's 160-character limit", () => {
    expect(validateAccount({ ...base, name: "x".repeat(161) }, null).name).toBeTruthy();
    expect(validateAccount({ ...base, name: "x".repeat(160) }, null).name).toBeUndefined();
  });

  it("rejects a subtype that does not belong to the kind", () => {
    expect(
      validateAccount({ ...base, name: "X", kind: "liability", subtype: "checking" }, null).subtype,
    ).toBeTruthy();
  });

  it("rejects an unparseable balance", () => {
    expect(validateAccount({ ...base, name: "X", balance: "lots" }, null).balance).toBeTruthy();
  });

  it("requires a date once an amount is given", () => {
    // A figure with no date would be recorded against today — a claim nobody made.
    const errors = validateAccount({ ...base, name: "X", balance: "10", balanceAsOf: "" }, 1000);

    expect(errors.balanceAsOf).toBeTruthy();
  });

  it("allows no balance at all", () => {
    expect(validateAccount({ ...base, name: "X", balance: "" }, null)).toEqual({});
  });

  it("holds the stake between 0 and 100 percent", () => {
    expect(
      validateAccount({ ...base, name: "X", stakePercent: "101" }, null).stakePercent,
    ).toBeTruthy();
    expect(
      validateAccount({ ...base, name: "X", stakePercent: "-1" }, null).stakePercent,
    ).toBeTruthy();
    expect(
      validateAccount({ ...base, name: "X", stakePercent: "0" }, null).stakePercent,
    ).toBeUndefined();
  });
});

describe("percentToBps", () => {
  it("converts without floating point", () => {
    // 33.33 * 100 is 3332.9999999999995 as a double.
    expect(percentToBps("33.33")).toBe(3333);
    expect(percentToBps("100")).toBe(10_000);
    expect(percentToBps("50.5")).toBe(5050);
  });
});

describe("validateBalance", () => {
  it("requires an amount", () => {
    expect(validateBalance("2026-08-18", null).amount).toBeTruthy();
  });

  it("refuses a future date", () => {
    // A future balance becomes the in-force one immediately and quietly moves
    // today's net worth.
    expect(validateBalance("2026-09-01", 1000, "2026-08-18").asOf).toBeTruthy();
  });

  it("accepts today", () => {
    expect(validateBalance("2026-08-18", 1000, "2026-08-18")).toEqual({});
  });
});

// ── the stake preview ───────────────────────────────────────────────────────────

describe("previewStakes", () => {
  it("closes the open stake at the new date and opens a new one", () => {
    const rows = previewStakes(stakes, 1, "Owner", 2_500, "2026-08-18");

    expect(rows.at(-1)).toEqual({
      ownerName: "Owner",
      percentageBps: 2_500,
      from: "2026-08-18",
      to: null,
      isNew: true,
    });
    const closed = rows.find((row) => row.from === "2025-06-01")!;
    expect(closed.to).toBe("2026-08-18");
  });

  it("leaves history before the change untouched", () => {
    // This is the visible form of "your past net worth will not move".
    const rows = previewStakes(stakes, 1, "Owner", 2_500, "2026-08-18");

    const historical = rows.find((row) => row.from === "2024-03-01")!;
    expect(historical.to).toBe("2025-06-01");
    expect(historical.percentageBps).toBe(10_000);
  });

  it("does not touch another owner's stake", () => {
    const shared = [
      ...stakes,
      {
        ...stakes[1],
        id: 12,
        owner_user_id: 2,
        owner_display_name: "Partner",
        percentage_bps: 5_000,
      },
    ];

    const rows = previewStakes(shared, 1, "Owner", 2_500, "2026-08-18");

    const partner = rows.find((row) => row.ownerName === "Partner")!;
    expect(partner.to).toBeNull();
  });

  it("replaces rather than closing a stake dated at or after the change", () => {
    // Closing it would create a zero-length range, which is not a period of time.
    const rows = previewStakes(stakes, 1, "Owner", 2_500, "2025-06-01");

    expect(rows.filter((row) => row.from === "2025-06-01")).toHaveLength(1);
    expect(rows.find((row) => row.from === "2025-06-01")!.isNew).toBe(true);
  });
});

describe("lastDay", () => {
  it("steps back a day, including across a month boundary", () => {
    expect(lastDay("2026-03-01")).toBe("2026-02-28");
    expect(lastDay("2026-01-01")).toBe("2025-12-31");
  });
});

// ── the forms ───────────────────────────────────────────────────────────────────

describe("AccountForm", () => {
  it("shows validation messages instead of submitting", async () => {
    const onCreated = vi.fn();
    render(<AccountForm onCreated={onCreated} />);

    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Give the account a name.")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("narrows the type list to the chosen kind", async () => {
    render(<AccountForm onCreated={() => {}} />);

    await userEvent.selectOptions(screen.getByLabelText("Kind"), "liability");

    expect(screen.getByRole("option", { name: "Mortgage" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Checking" })).not.toBeInTheDocument();
  });

  it("submits dollars as integer cents", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/accounts", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...accountDetail, id: 42 }, { status: 201 });
      }),
    );

    render(<AccountForm onCreated={() => {}} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checking");
    await userEvent.type(screen.getByLabelText("Opening balance"), "1234.56");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(body).toMatchObject({
        opening_balance_cents: 123_456,
        ownership_percentage_bps: 10_000,
      }),
    );
  });

  it("surfaces the server's rejection rather than swallowing it", async () => {
    // A form that believes it validated everything is how a 422 becomes a no-op.
    server.use(
      http.post("/api/accounts", () =>
        HttpResponse.json({ detail: "That name is already taken" }, { status: 409 }),
      ),
    );

    render(<AccountForm onCreated={() => {}} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checking");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That name is already taken");
  });
});

describe("BalanceForm", () => {
  it("defaults the date to today", () => {
    render(<BalanceForm accountId={3} accountName="Rental" onRecorded={() => {}} />);

    expect(screen.getByLabelText("As of")).toHaveValue(new Date().toISOString().slice(0, 10));
  });

  it("caps the date at today", () => {
    render(<BalanceForm accountId={3} accountName="Rental" onRecorded={() => {}} />);

    expect(screen.getByLabelText("As of")).toHaveAttribute(
      "max",
      new Date().toISOString().slice(0, 10),
    );
  });

  it("submits integer cents", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/accounts/:id/balances", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    render(<BalanceForm accountId={3} accountName="Rental" onRecorded={() => {}} />);
    await userEvent.type(screen.getByLabelText("Balance"), "450880.82");
    await userEvent.click(screen.getByRole("button", { name: "Record balance" }));

    await waitFor(() =>
      expect(body).toMatchObject({ balance_cents: 45_088_082, source: "manual" }),
    );
  });
});

describe("StakeForm", () => {
  it("explains what an effective date does, in a sentence", () => {
    render(
      <StakeForm
        accountId={3}
        stakes={stakes}
        ownerUserId={1}
        ownerName="Owner"
        onSaved={() => {}}
      />,
    );

    expect(screen.getByText(/Your past net worth will not change/)).toBeInTheDocument();
  });

  it("previews the resulting history with the new row marked", async () => {
    render(
      <StakeForm
        accountId={3}
        stakes={stakes}
        ownerUserId={1}
        ownerName="Owner"
        onSaved={() => {}}
      />,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    // Header plus the two existing periods plus the new one.
    expect(rows).toHaveLength(4);
    expect(within(table).getByText("new")).toBeInTheDocument();
  });

  it("submits basis points", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/accounts/:id/stakes", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    render(
      <StakeForm
        accountId={3}
        stakes={stakes}
        ownerUserId={1}
        ownerName="Owner"
        onSaved={() => {}}
      />,
    );
    await userEvent.clear(screen.getByLabelText("New share"));
    await userEvent.type(screen.getByLabelText("New share"), "33.33");
    await userEvent.click(screen.getByRole("button", { name: "Save ownership change" }));

    await waitFor(() => expect(body).toMatchObject({ percentage_bps: 3333, owner_user_id: 1 }));
  });

  it("refuses a share above 100%", async () => {
    render(
      <StakeForm
        accountId={3}
        stakes={stakes}
        ownerUserId={1}
        ownerName="Owner"
        onSaved={() => {}}
      />,
    );
    await userEvent.clear(screen.getByLabelText("New share"));
    await userEvent.type(screen.getByLabelText("New share"), "150");
    await userEvent.click(screen.getByRole("button", { name: "Save ownership change" }));

    expect(await screen.findByText(/between 0% and 100%/)).toBeInTheDocument();
  });
});
