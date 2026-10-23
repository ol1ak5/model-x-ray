import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("../components/Stage", () => ({
  default: () => {
    throw new Error("the sheet view blew up");
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

  await user.click(await screen.findByRole("button", { name: "See it in action" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Part of this view could not be drawn");
  expect(screen.getByText("Demo model")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start another check" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Start another check" }));
  expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Your Excel models. Under the X-Ray.");
});
