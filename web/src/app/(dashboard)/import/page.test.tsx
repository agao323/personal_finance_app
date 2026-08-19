import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import ImportPage from "./page";
import { headersOf } from "@/components/import/csv-wizard";
import { orderRows } from "@/components/import/import-preview";
import { csvPreview, mockAccounts, mockCsvImport, server } from "@/test/msw";

const CSV = "Date,Amount,Description\n2026-08-14,-45.12,Corner Market\n";

beforeEach(() => {
  mockAccounts();
  mockCsvImport();
});

function csvFile(content = CSV, name = "export.csv") {
  return new File([content], name, { type: "text/csv" });
}

/** Drive the wizard as far as the mapping step. */
async function reachMapping() {
  render(<ImportPage />);
  await screen.findByLabelText("Import into");
  await userEvent.selectOptions(screen.getByLabelText("Import into"), "1");
  await userEvent.upload(screen.getByLabelText("CSV file"), csvFile());
  await screen.findByText("Sign convention");
}

describe("headersOf", () => {
  it("reads the header row", () => {
    expect(headersOf(CSV)).toEqual(["Date", "Amount", "Description"]);
  });

  it("strips quotes and blanks", () => {
    expect(headersOf('"Date","Amount",\nrow')).toEqual(["Date", "Amount"]);
  });

  it("returns nothing for an empty file", () => {
    expect(headersOf("")).toEqual([]);
  });
});

describe("orderRows", () => {
  it("puts problems first, then changes, then unchanged rows", () => {
    const ordered = orderRows(csvPreview.rows);

    expect(ordered.map((row) => row.row_number)).toEqual([4, 2, 3]);
  });
});

describe("import wizard", () => {
  it("will not take a file until an account is chosen", async () => {
    // An import with no account has nowhere to put the rows.
    render(<ImportPage />);

    expect(await screen.findByLabelText("CSV file")).toBeDisabled();
    expect(screen.getByText("Pick an account first.")).toBeInTheDocument();
  });

  it("moves to the mapping step once a file is read", async () => {
    await reachMapping();

    expect(screen.getByLabelText("Date")).toHaveValue("Date");
    expect(screen.getByLabelText("Amount")).toHaveValue("Amount");
  });

  it("says where the mapping came from", async () => {
    // A guess and a memory presented identically is how a stale mapping gets reused.
    await reachMapping();

    expect(screen.getByText(/Guessed from the header row/)).toBeInTheDocument();
  });

  it("says so when the mapping was remembered", async () => {
    mockCsvImport({ mapping_source: "saved" });

    await reachMapping();

    expect(screen.getByText(/saved for this account last time/)).toBeInTheDocument();
  });

  it("shows a row-level result, not just counts", async () => {
    // "312 rows updated" is equally consistent with a correct mapping and one that
    // read the wrong column into every field.
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));

    const table = await screen.findByRole("table", { name: /Rows this import would write/ });
    expect(within(table).getByText("Corner Market")).toBeInTheDocument();
    expect(within(table).getByText("−$45.12")).toBeInTheDocument();
  });

  it("reports a bad row against that row, not as one opaque failure", async () => {
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));

    expect(await screen.findByText(/could not read the date/)).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();
  });

  it("shows the effect of flipping the sign in the preview", async () => {
    await reachMapping();
    await userEvent.click(screen.getByRole("radio", { name: /Spending is positive/ }));
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));

    // The same row, now an inflow — which is what a wrong sign convention looks like.
    const table = await screen.findByRole("table", { name: /Rows this import would write/ });
    expect(within(table).getByText("$45.12")).toBeInTheDocument();
  });

  it("goes back to the mapping step from the preview", async () => {
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));
    await screen.findByRole("table", { name: /Rows this import would write/ });

    await userEvent.click(screen.getByRole("button", { name: "Change the mapping" }));

    expect(screen.getByText("Sign convention")).toBeInTheDocument();
  });

  it("commits and summarises what it wrote", async () => {
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));
    await screen.findByRole("table", { name: /Rows this import would write/ });

    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText("2 transactions written")).toBeInTheDocument();
    expect(screen.getByText(/1 new, 1 changed, 1 already up to date/)).toBeInTheDocument();
  });

  it("says a re-import would change nothing, rather than reporting a number", async () => {
    // The whole point of the idempotent upsert. "412 updated" and "nothing changed"
    // are the same outcome, but only one of them tells you the import was a no-op.
    mockCsvImport({ will_create: 0, will_update: 0, will_skip: 3 });

    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));

    expect(await screen.findByText(/Nothing here would change/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import anyway" })).toBeInTheDocument();
  });

  it("surfaces an unreadable file instead of an empty mapping step", async () => {
    server.use(
      http.post("/api/import/csv/preview", () =>
        HttpResponse.json({ detail: "no header row found" }, { status: 422 }),
      ),
    );

    render(<ImportPage />);
    await screen.findByLabelText("Import into");
    await userEvent.selectOptions(screen.getByLabelText("Import into"), "1");
    await userEvent.upload(screen.getByLabelText("CSV file"), csvFile("garbage"));

    expect(await screen.findByRole("alert")).toHaveTextContent("no header row found");
    expect(screen.queryByText("Sign convention")).not.toBeInTheDocument();
  });

  it("routes to account creation when there is nowhere to import", async () => {
    mockAccounts({ groups: [] });

    render(<ImportPage />);

    expect(await screen.findByText("No accounts to import into")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      "/accounts/new",
    );
  });

  it("offers to remember the mapping", async () => {
    let body: { save_mapping_as?: string } | null = null;
    server.use(
      http.post("/api/import/csv/commit", async ({ request }) => {
        body = (await request.json()) as { save_mapping_as?: string };
        return HttpResponse.json({ created: 1, updated: 0, skipped: 0, errors: [] });
      }),
    );

    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Check the result" }));
    await screen.findByRole("table", { name: /Rows this import would write/ });
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(body).toMatchObject({ save_mapping_as: "export" }));
  });
});
