import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("../check/CheckPage", () => ({
  default: () => {
    throw new Error("the check page blew up");
  },
}));

import App from "../App";
import { REVIEW, STEPS, fakeApi, steps } from "./fakeApi";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("shows a way out instead of a blank page when a view blows up", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]]);
  vi.stubGlobal("fetch", api.fetch);
  const user = userEvent.setup();
  render(<App />);

  await user.click((await screen.findAllByRole("button", { name: "Try the demo →" }))[0]);

  expect(await screen.findByRole("alert")).toHaveTextContent("Part of this page could not be drawn");
  expect(screen.getByRole("button", { name: "Start another check" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Start another check" }));
  expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Your AI agent for financial model analysis.");
});
