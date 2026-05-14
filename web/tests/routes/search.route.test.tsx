import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("search route", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest();
  });

  it("routes topbar text search into Search Intel", async () => {
    renderAppRoute("/");

    fireEvent.change(await screen.findByLabelText("global search"), { target: { value: "$RKC" } });
    fireEvent.click(screen.getByRole("button", { name: "检索" }));

    expect(await screen.findByRole("heading", { name: "Search Intel" })).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/search/inspect",
        expect.objectContaining({
          params: expect.objectContaining({ q: "$RKC", window: "24h", scope: "all" }),
        }),
      );
    });
    expect(screen.queryByText(/Select Token/i)).not.toBeInTheDocument();
  });
});
