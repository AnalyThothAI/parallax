import { cleanup, screen } from "@testing-library/react";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setupAppRouteTest } from "./routeTestSetup";

describe("live radar route", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    setupAppRouteTest();
  });

  it("renders Token Radar as the default route", async () => {
    renderAppRoute("/");

    expect(await screen.findByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
  });
});
