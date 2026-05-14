import { tittyPulseFixture } from "@features/signal-lab/test/fixtures";
import { screen, waitFor } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
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

  it("keeps direct pulse detail URLs addressable", async () => {
    apiMock.getApiImpl = async (path) => {
      if (path === "/api/status") return ok({ handles: [], collector: {}, notifications: null });
      if (path === "/api/notification-summary") return ok(null);
      if (path === "/api/notifications") return ok({ items: [], summary: null });
      if (path === "/api/recent") return ok({ items: [] });
      if (path === "/api/token-radar") return ok({ targets: [], attention: [] });
      if (path.startsWith("/api/signal-lab/pulse/")) return ok(tittyPulseFixture);
      if (path === "/api/social-events/by-ids") return ok({ events: [], not_found: [] });
      throw new Error(`unexpected path ${path}`);
    };

    renderAppRoute("/signal-lab/pulse/pulse-titty");

    expect(await screen.findByRole("heading", { name: "$TITTY" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回列表" })).toHaveAttribute("href", "/signal-lab");
  });
});
