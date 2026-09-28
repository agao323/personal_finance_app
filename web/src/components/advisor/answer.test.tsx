import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnswerText, type Answer } from "@/components/advisor/answer";
import { Conversation } from "@/components/advisor/conversation";
import { stashQuestion } from "@/lib/advisor";
import { parseEvents } from "@/lib/advisor-stream";
import { parse, parseInline } from "@/lib/markdown-lite";
import { CONVERSATION_ID, TURN_ID, mockConversation, storedTurn } from "@/test/msw";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  push.mockReset();
  sessionStorage.clear();
});

function answer(text: string, overrides: Partial<Answer> = {}): Answer {
  return {
    text,
    figures: [],
    citations: [],
    limitations: [],
    policy_notes: [],
    truncated: false,
    ...overrides,
  };
}

const citation = {
  call_id: "c2",
  tool: "spend_by_category",
  label: "Spending by category, this quarter",
  as_of: "2026-09-27",
  view: null,
  stale: false,
};

function events(text: string, final: Answer, extra: unknown[] = []): unknown[] {
  return [
    { type: "turn_started", turn_id: TURN_ID, conversation_id: CONVERSATION_ID },
    {
      type: "tool_call",
      lookup: {
        call_id: "c2",
        tool: "spend_by_category",
        label: "Spending by category, this quarter",
        arguments: "period=this_quarter",
        status: "ok",
        row_count: 12,
        latency_ms: 31,
        as_of: "2026-09-27",
      },
    },
    ...extra,
    { type: "text_delta", text: text.slice(0, 10) },
    { type: "text_delta", text: text.slice(10) },
    { type: "answer", answer: final },
    {
      type: "turn_complete",
      turn_id: TURN_ID,
      grounding: final.figures.length ? "verified" : "none",
      cost_cents: 4,
      month_spent_cents: 316,
    },
  ];
}

async function ask(question: string) {
  await userEvent.type(await screen.findByLabelText("Ask a follow-up"), question);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("a streamed answer", () => {
  it("shows lookups as they happen, then the checked answer with its sources", async () => {
    const text = "Dining was $1,234.56 this quarter.";
    const final = answer(text, {
      figures: [{ start: 11, end: 20, status: "verified", source: { call_id: "c2", path: "x" } }],
      citations: [citation],
    });
    mockConversation({ turns: [], events: events(text, final) });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("Dining this quarter?");

    const turn = await screen.findByRole("article", { name: "Dining this quarter?" });
    await waitFor(() => expect(within(turn).getByText(/Dining was/)).toBeInTheDocument());
    expect(within(turn).getByRole("button", { name: "$1,234.56" })).toBeInTheDocument();
    expect(within(turn).getByRole("list", { name: "Sources" })).toHaveTextContent(
      "Spending by category, this quarter · as of Sep 27, 2026",
    );
    await userEvent.click(within(turn).getByRole("button", { name: "$1,234.56" }));
    expect(within(turn).getByText(/from Spending by category/)).toBeInTheDocument();
    await userEvent.click(within(turn).getByRole("button", { name: "Show lookups (1)" }));
    expect(within(turn).getByRole("list", { name: "Lookups" })).toHaveTextContent(
      "period=this_quarter · 12 rows · 31 ms",
    );
  });

  it("sends the question stashed by the list screen, once", async () => {
    stashQuestion(CONVERSATION_ID, "What's my runway?");
    const calls = mockConversation({ turns: [], events: events("Fine.", answer("Fine.")) });

    render(<Conversation id={CONVERSATION_ID} />);

    await screen.findByRole("article", { name: "What's my runway?" });
    await waitFor(() => expect(calls.turns.map((t) => t.question)).toEqual(["What's my runway?"]));
  });

  it("marks an unverified figure, with its reason on tap", async () => {
    const text = "About $1,200 more than usual.";
    const final = answer(text, {
      figures: [
        {
          start: 6,
          end: 12,
          status: "unverified",
          reason: "Not found in any lookup this conversation.",
        },
      ],
    });
    mockConversation({ turns: [], events: events(text, final) });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("More than usual?");

    const turn = await screen.findByRole("article", { name: "More than usual?" });
    await waitFor(() => expect(within(turn).getByText("unverified")).toBeInTheDocument());
    await userEvent.click(within(turn).getByRole("button", { name: "$1,200" }));
    expect(within(turn).getByText(/Not found in any lookup/)).toBeInTheDocument();
  });

  it("replaces the text when the answer is regenerated", async () => {
    const final = answer("Checked text.");
    mockConversation({
      turns: [],
      events: [
        { type: "turn_started", turn_id: TURN_ID, conversation_id: CONVERSATION_ID },
        { type: "text_delta", text: "First draft with $9.99." },
        { type: "regenerating", reason: "A figure could not be traced to a lookup." },
        { type: "text_delta", text: "Checked text." },
        { type: "answer", answer: final },
        {
          type: "turn_complete",
          turn_id: TURN_ID,
          grounding: "none",
          cost_cents: 1,
          month_spent_cents: 1,
        },
      ],
    });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("Anything?");

    const turn = await screen.findByRole("article", { name: "Anything?" });
    await waitFor(() => expect(within(turn).getByText("Checked text.")).toBeInTheDocument());
    expect(within(turn).queryByText(/First draft/)).not.toBeInTheDocument();
  });

  it("shows a stale citation's badge and the app's limitations", async () => {
    const final = answer("Here is what I can say.", {
      citations: [{ ...citation, stale: true, view: "mine" }],
      limitations: ["liability_terms"],
    });
    mockConversation({ turns: [], events: events("Here is what I can say.", final) });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("Mortgage rate?");

    const turn = await screen.findByRole("article", { name: "Mortgage rate?" });
    const sources = await within(turn).findByRole("list", { name: "Sources" });
    expect(within(sources).getByText("Stale")).toBeInTheDocument();
    expect(sources).toHaveTextContent("Mine");
    expect(within(turn).getByText(/no liability terms yet/)).toBeInTheDocument();
  });

  it("stops the answer being written, aborting the request", async () => {
    const calls = mockConversation({
      turns: [],
      hold: true,
      events: [
        { type: "turn_started", turn_id: TURN_ID, conversation_id: CONVERSATION_ID },
        { type: "text_delta", text: "Working on" },
      ],
    });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("Slow question?");
    const turn = await screen.findByRole("article", { name: "Slow question?" });
    await within(turn).findByText(/Working on/);
    await userEvent.click(within(turn).getByRole("button", { name: "Stop" }));

    await waitFor(() => expect(calls.turns[0].signal.aborted).toBe(true));
    expect(await within(turn).findByText("Stopped.")).toBeInTheDocument();
    expect(within(turn).queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("reads a cap plainly, with the date it resets", async () => {
    mockConversation({
      turns: [],
      events: [
        { type: "turn_started", turn_id: TURN_ID, conversation_id: CONVERSATION_ID },
        {
          type: "error",
          code: "monthly_cap",
          message: "This month's advisor budget is used up.",
          resets_on: "2026-10-01",
        },
        {
          type: "turn_complete",
          turn_id: TURN_ID,
          grounding: "none",
          cost_cents: 0,
          month_spent_cents: 2000,
        },
      ],
    });
    render(<Conversation id={CONVERSATION_ID} />);

    await ask("Another?");

    expect(
      await screen.findByText("This month's advisor budget is used up. It resets on Oct 1, 2026."),
    ).toBeInTheDocument();
  });
});

describe("feedback", () => {
  it("saves a flag with a note on that answer, without reloading the conversation", async () => {
    const calls = mockConversation();
    render(<Conversation id={CONVERSATION_ID} />);
    const turn = await screen.findByRole("article", { name: "What's our net worth?" });

    await userEvent.click(within(turn).getByRole("button", { name: "Flag" }));
    await userEvent.type(within(turn).getByLabelText("What was wrong? (optional)"), "Wrong view.");
    await userEvent.click(within(turn).getByRole("button", { name: "Save flag" }));

    await waitFor(() =>
      expect(within(turn).getByRole("button", { name: "Flagged" })).toBeInTheDocument(),
    );
    expect(calls.feedback).toEqual([
      { turnId: storedTurn.id, body: { verdict: "flagged", note: "Wrong view." } },
    ]);
    expect(turn).toHaveTextContent("Household net worth is $412,388.14.");
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });
});

describe("nothing in an answer can load or link", () => {
  const hostile = [
    "Inline ![x](https://evil.example/?d=1) image.",
    "Reference ![x][1] image.",
    "",
    "[1]: https://evil.example/?d=1",
    "",
    'Raw <img src="https://evil.example/?d=1"> tag and a [link](https://evil.example).',
    "",
    "Unknown [[screen:evil]] and known [[screen:cards]].",
  ].join("\n");

  it("draws no img and no a, and shows the syntax as literal text", () => {
    const { container } = render(<AnswerText text={hostile} answer={answer(hostile)} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container).toHaveTextContent("![x](https://evil.example/?d=1)");
    expect(container).toHaveTextContent('<img src="https://evil.example/?d=1">');
    expect(container).toHaveTextContent("[[screen:evil]]");
    expect(screen.getByRole("button", { name: "Open Cards" })).toBeInTheDocument();
  });

  it("routes a screen token inside the app", async () => {
    render(<AnswerText text="Mark it on [[screen:cards]]." />);

    await userEvent.click(screen.getByRole("button", { name: "Open Cards" }));

    expect(push).toHaveBeenCalledWith("/cards");
  });

  it("renders the formatting it does support", () => {
    const text = [
      "### Summary",
      "**Bold** and *italic* and `code`.",
      "",
      "- one",
      "- two",
      "",
      "1. first",
      "2. second",
      "",
      "| Month | Spend |",
      "|---|---|",
      "| July | $10.00 |",
    ].join("\n");
    const { container } = render(<AnswerText text={text} />);

    expect(container.querySelector("h3")).toHaveTextContent("Summary");
    expect(container.querySelector("strong")).toHaveTextContent("Bold");
    expect(container.querySelector("em")).toHaveTextContent("italic");
    expect(container.querySelector("code")).toHaveTextContent("code");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("td")).toHaveTextContent("July");
  });
});

describe("markdown-lite", () => {
  it("places figure spans by their offsets in the whole answer", () => {
    const text = "Line one.\n\n**Net worth** is $1,234.56 today.";
    const start = text.indexOf("$");
    const blocks = parse(text, [{ start, end: start + 9 }]);

    expect(blocks[1]).toEqual({
      type: "paragraph",
      children: [
        { type: "strong", children: [{ type: "text", text: "Net worth" }] },
        { type: "text", text: " is " },
        { type: "figure", text: "$1,234.56", index: 0 },
        { type: "text", text: " today." },
      ],
    });
  });

  it("finds a figure inside bold and inside a table cell", () => {
    const bold = "It is **$5.00** now.";
    const inBold = bold.indexOf("$");
    expect(parseInline(bold, 0, [{ start: inBold, end: inBold + 5 }])[1]).toEqual({
      type: "strong",
      children: [{ type: "figure", text: "$5.00", index: 0 }],
    });

    const table = "| A |\n|---|\n| $7.00 |";
    const inCell = table.indexOf("$");
    const [block] = parse(table, [{ start: inCell, end: inCell + 5 }]);
    expect(block).toMatchObject({ type: "table", rows: [[[{ type: "figure", text: "$7.00" }]]] });
  });

  it("has no link or image node, whatever the input", () => {
    const tree = JSON.stringify(parse("![a](b) [c](d) <a href=e>f</a> https://g.example"));

    expect(tree).not.toMatch(/"type":"(link|image|html)"/);
  });
});

describe("the event stream", () => {
  it("parses complete events and keeps the partial remainder", () => {
    const { events: first, rest } = parseEvents(
      'data: {"type":"heartbeat"}\n\ndata: {"type":"text_delta","text":"a"}\n\ndata: {"type":"te',
    );

    expect(first).toEqual([{ type: "heartbeat" }, { type: "text_delta", text: "a" }]);
    expect(rest).toBe('data: {"type":"te');
    expect(parseEvents(`${rest}xt_delta","text":"b"}\n\n`).events).toEqual([
      { type: "text_delta", text: "b" },
    ]);
  });

  it("accepts CRLF line endings", () => {
    expect(parseEvents('data: {"type":"heartbeat"}\r\n\r\n').events).toEqual([
      { type: "heartbeat" },
    ]);
  });
});
