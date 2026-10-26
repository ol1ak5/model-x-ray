import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import type { InvestigationView } from "../api";
import { APPROVED, CLEAR, REJECTED, REVIEW, SHEET, STEPS, fakeApi, steps } from "./fakeApi";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

const CORRECTED = { name: "My model-corrected.xlsx", base64: "UEsDBAo=" };

function lastResume(api: ReturnType<typeof fakeApi>) {
  return api.sent.filter((request) => request.url.includes("/resume/")).at(-1);
}

function phase(name: string) {
  return within(screen.getByRole("region", { name: "Progress" })).getByText(name).closest("li");
}

async function openTheError(user: ReturnType<typeof userEvent.setup>) {
  const errors = await screen.findByRole("region", { name: "Errors detected" });
  await user.click(await within(errors).findByRole("button", { name: /COGS 2025A has the wrong sign/ }));
  return errors;
}

async function checkDemo() {
  const user = userEvent.setup();
  render(<App />);
  await user.click((await screen.findAllByRole("button", { name: "Try the demo →" }))[0]);
  return user;
}

describe("the landing page", () => {
  test("presents the agent and starts a live check of the demo model", async () => {
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your AI agent for financial model analysis.");
    expect(screen.getByRole("heading", { name: /Small errors, billion-dollar consequences/ })).toBeInTheDocument();
    expect(screen.getByText("Did you know that?", { selector: ".label" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read the code on GitHub" })).toHaveAttribute("href", "https://github.com/ol1ak5/model-x-ray");

    await user.click((await screen.findAllByRole("button", { name: "Try the demo →" }))[0]);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Demo model.xlsx");
    expect(api.sent.find((request) => request.url.endsWith("/investigations/stream"))?.body).toEqual({ spreadsheet_id: "demo", question: "" });
    const sheets = screen.getByText("Sheets in this file:").parentElement as HTMLElement;
    expect(within(sheets).getAllByRole("button").map((button) => button.textContent)).toEqual(["P&L", "Assumptions", "Summary"]);
  });

  test("says so in one line when the upload is refused", async () => {
    const api = fakeApi([]);
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => (url.includes("/spreadsheets?name=") ? Response.json({ detail: "Upload an Excel .xlsx file" }, { status: 400 }) : api.fetch(url, init)));
    const user = userEvent.setup();
    render(<App />);

    await user.upload(screen.getByLabelText("Upload your model"), new File(["notes"], "notes.xlsx"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Upload an Excel .xlsx file");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your AI agent for financial model analysis.");
  });
});

describe("a model check", () => {
  test("follows the stream, lists the error with its tested fix, and hands over the corrected file after approval", async () => {
    const api = fakeApi(
      [...steps(...STEPS.map(([name]) => name)), ["view", { ...REVIEW, sheet: SHEET, report: `${REVIEW.report} G5 uses \`=G4*Assumptions!$C$5\` instead of a subtraction..` }]],
      [[...steps("human_review", "apply_fix"), ["view", { ...APPROVED, sheet: SHEET, corrected_file: CORRECTED }]]],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = userEvent.setup();
    render(<App />);

    await user.upload(screen.getByLabelText("Upload your model"), new File(["xlsx bytes"], "My model.xlsx"));

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("My model.xlsx");
    expect(api.sent.find((request) => request.url.endsWith("/investigations/stream"))?.body).toEqual({ spreadsheet_id: "upload-1", question: "", file: "My model.xlsx" });
    expect(await screen.findByText("Errors detected: 1")).toBeInTheDocument();
    expect(screen.getByText("Progress: 3 of 5")).toBeInTheDocument();
    expect(phase("Prove")).toHaveAttribute("data-state", "done");
    expect(phase("Approve")).toHaveAttribute("data-state", "wait");
    expect(screen.getByText("1 error detected")).toBeInTheDocument();
    expect(screen.getByText("Waiting for your decision")).toBeInTheDocument();

    const errors = await openTheError(user);
    const facts = errors.querySelector("dl") as HTMLElement;
    expect(within(facts).getByText("Where").nextElementSibling).toHaveTextContent("P&L!G5");
    expect(within(facts).getByText("Error").nextElementSibling).toHaveTextContent("=G4*Assumptions!$C$5");
    expect(within(facts).getByText("Solution").nextElementSibling).toHaveTextContent("=-G4*Assumptions!$C$5");
    const explanation = within(facts).getByText("Explanation").nextElementSibling as HTMLElement;
    expect(explanation).toHaveTextContent(/Gross profit 2025A moved from 84\.72 to 285\.76/);
    expect(explanation.textContent).not.toMatch(/ev-\d|`|\.\./);
    expect(explanation).toHaveTextContent("G5 uses =G4*Assumptions!$C$5 instead of a subtraction.");

    await user.click(within(errors).getByRole("button", { name: "Approve fix" }));

    expect(lastResume(api)).toMatchObject({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", state: { id: REVIEW.id, status: "needs_review" }, file: "My model.xlsx" },
    });
    expect(await within(errors).findByText("✓ Fix accepted")).toBeInTheDocument();
    expect(within(errors).getByText("Fixed")).toBeInTheDocument();
    expect(within(errors).getByText("Fixed with")).toBeInTheDocument();
    expect(screen.getByText("Review complete", { selector: ".state" })).toBeInTheDocument();
    expect(screen.getByText("Progress: 5 of 5")).toBeInTheDocument();
    const download = screen.getByRole("link", { name: "Download My model (corrected).xlsx" });
    expect(download).toHaveAttribute("download", CORRECTED.name);
    expect(download.getAttribute("href")).toBe(`data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${CORRECTED.base64}`);
    expect(within(errors).queryByRole("button", { name: "Approve fix" })).toBeNull();
  });

  test("tests the reviewer's own formula before anything is approved", async () => {
    const edited: InvestigationView = { ...REVIEW, patch: { cell: "P&L!G5", old_formula: "=G4*Assumptions!$C$5", new_formula: "=-G4*0.52", source: "human" } };
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("test", "verify", "explain"), ["view", edited]]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();
    const errors = await openTheError(user);

    await user.click(within(errors).getByRole("button", { name: "Edit fix" }));
    const field = within(errors).getByLabelText(/Your formula for/);
    expect(field).toHaveValue("=-G4*Assumptions!$C$5");
    await user.clear(field);
    await user.type(field, "=-G4*0.52");
    await user.click(within(errors).getByRole("button", { name: "Test my fix" }));

    expect(lastResume(api)?.body).toMatchObject({ action: "edit", patch: { cell: "P&L!G5", old_formula: "=G4*Assumptions!$C$5", new_formula: "=-G4*0.52" } });
    await waitFor(() => expect(within(errors).getByText("Solution").nextElementSibling).toHaveTextContent("=-G4*0.52"));
    expect(screen.getByText("1 error detected")).toBeInTheDocument();
  });

  test("a rejection marked as never flag again closes the check without touching the file", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review"), ["view", REJECTED]]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();
    const errors = await openTheError(user);

    await user.click(within(errors).getByRole("button", { name: "Reject" }));
    await user.click(within(errors).getByLabelText("Never flag this cell again"));
    await user.click(within(errors).getByRole("button", { name: "It's not an error" }));

    expect(lastResume(api)?.body).toMatchObject({ action: "reject", intentional: true });
    expect(await within(errors).findByText("Not an error")).toBeInTheDocument();
    expect(screen.getByText("No changes to your file")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /corrected/ })).toBeNull();
  });

  test("a model with nothing to fix says so and asks for no decision", async () => {
    vi.stubGlobal("fetch", fakeApi([...steps("explain"), ["view", CLEAR]]).fetch);
    await checkDemo();

    expect(await screen.findByText("The agent found nothing to fix in this model.")).toBeInTheDocument();
    expect(screen.getByText("No errors found")).toBeInTheDocument();
    expect(screen.getByText("Progress: 5 of 5")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve fix" })).toBeNull();
  });

  test("opens the real workbook with the error in red and the cells that depend on it in blue, and shows each cell's formula", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();
    const errors = await openTheError(user);

    await user.click(within(errors).getByRole("button", { name: "Open in the sheet" }));

    const dialog = await screen.findByRole("dialog", { name: /P&L!G5/ });
    await waitFor(() => expect(dialog.querySelector('td[data-ref="G5"]')).toHaveClass("m-err"));
    expect(dialog.querySelector('td[data-ref="G6"]')).toHaveClass("m-dep");
    expect(dialog.querySelector('td[data-ref="G5"]')).toHaveTextContent("97.76");
    expect(within(dialog).getByText("=G4*Assumptions!$C$5")).toBeInTheDocument();
    expect(within(dialog).getByText("Marks are only shown here, your file is not changed")).toBeInTheDocument();

    await user.click(dialog.querySelector('td[data-ref="G6"]') as HTMLElement);
    expect(within(dialog).getByText("=G4+G5")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("tab", { name: "Summary" }));
    expect(dialog.querySelector('td[data-ref="H6"]')).toHaveClass("m-dep");
    expect(dialog.querySelector('td[data-ref="H6"]')).toHaveTextContent("-0.8586666667");
    expect(api.sent.filter((request) => request.url.endsWith("/workbook"))).toHaveLength(1);
  });

  test("answers the reviewer's questions about the error, one line each, remembering the conversation", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [], [], ["COGS is a cost, so G5 should subtract it like the other years.", "Yes. In the copy Gross profit 2025A became 90.2."]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();
    const errors = await openTheError(user);
    const field = within(errors).getByLabelText("Ask the agent about this error");

    await user.type(field, "Why is G5 wrong?");
    await user.click(within(errors).getByRole("button", { name: "Ask" }));

    expect(await within(errors).findByText("COGS is a cost, so G5 should subtract it like the other years.")).toBeInTheDocument();
    expect(within(errors).getByText("Why is G5 wrong?").closest("p")).toHaveTextContent("You: Why is G5 wrong?");
    const first = api.sent.filter((request) => request.url.endsWith("/ask")).at(-1);
    expect(first?.url).toBe(`http://localhost:8000/investigations/${REVIEW.id}/ask`);
    expect(first?.body).toMatchObject({ question: "Why is G5 wrong?", history: [], state: { id: REVIEW.id, status: "needs_review" } });

    await user.type(field, "Was the fix tested?");
    await user.click(within(errors).getByRole("button", { name: "Ask" }));

    expect(await within(errors).findByText("Yes. In the copy Gross profit 2025A became 90.2.")).toBeInTheDocument();
    expect(api.sent.filter((request) => request.url.endsWith("/ask")).at(-1)?.body).toMatchObject({
      question: "Was the fix tested?",
      history: [
        { role: "user", text: "Why is G5 wrong?" },
        { role: "agent", text: "COGS is a cost, so G5 should subtract it like the other years." },
      ],
    });
    expect(field).toHaveValue("");
  });

  test("shows a short message when the check fails, and keeps the page", async () => {
    vi.stubGlobal("fetch", fakeApi([...steps("load_sheet"), ["error", 503, "The AI service is busy right now. Please try again in a minute."]]).fetch);
    await checkDemo();

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service is busy right now");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Demo model.xlsx");
  });

  test("goes back to the landing from the check", async () => {
    vi.stubGlobal("fetch", fakeApi([...steps("explain"), ["view", REVIEW]]).fetch);
    const user = await checkDemo();
    await screen.findByText("Errors detected: 1");

    await user.click(screen.getByRole("button", { name: "Check another model" }));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your AI agent for financial model analysis.");
  });
});
