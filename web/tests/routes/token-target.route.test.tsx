import { screen, within } from "@testing-library/react";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setupAppRouteTest } from "./routeTestSetup";

describe("token target route", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest();
  });

  it("renders the target page with the shared Social x Market Timeline", async () => {
    const { container } = renderAppRoute("/token/CexToken/cex_token%3AZEC?window=1h&scope=all");

    expect(await screen.findByRole("heading", { name: "$ZEC" })).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Social x Market Timeline" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Not in current radar window").length).toBeGreaterThan(0);
    expect(screen.queryByText("score audit")).not.toBeInTheDocument();

    const page = container.querySelector(".token-target-page");
    expect(page).toBeTruthy();
    expect(within(page as HTMLElement).getByText("message evidence")).toBeInTheDocument();
  });
});
