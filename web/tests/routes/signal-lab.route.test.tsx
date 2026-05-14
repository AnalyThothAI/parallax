import { waitFor } from "@testing-library/react";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("signal lab route", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest();
  });

  it("passes handle, status, window, and scope from URL params to the read model", async () => {
    renderAppRoute("/signal-lab?handle=toly&status=token_watch&window=4h&scope=matched");

    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse",
        expect.objectContaining({
          params: expect.objectContaining({
            handle: "toly",
            scope: "matched",
            status: "token_watch",
            window: "4h",
          }),
        }),
      );
    });
  });
});
