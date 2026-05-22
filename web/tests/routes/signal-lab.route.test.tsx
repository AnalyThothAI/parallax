import { cleanup, screen, waitFor } from "@testing-library/react";
import { appStatusFixture } from "@tests/fixtures/appRouteFixtures";
import { tittyPulseFixture } from "@tests/fixtures/signal-lab";
import { ok } from "@tests/msw/fixtures";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("signal lab route", () => {
  afterEach(() => {
    cleanup();
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
      if (path === "/api/status") return ok(appStatusFixture({ handles: [] }));
      if (path === "/api/notification-summary") return ok(null);
      if (path === "/api/notifications") return ok({ items: [], summary: null });
      if (path === "/api/recent") return ok({ items: [] });
      if (path === "/api/token-radar") return ok({ targets: [], attention: [] });
      if (path === "/api/stocks-radar") {
        return ok({
          rows: [],
          health: { returned_count: 0, quote_ready_count: 0, quote_unavailable_count: 0 },
        });
      }
      if (path === "/api/news") return ok({ items: [], next_cursor: null });
      if (path.startsWith("/api/signal-lab/pulse/")) return ok(tittyPulseFixture);
      if (path === "/api/social-events/by-ids") return ok({ events: [], not_found: [] });
      throw new Error(`unexpected path ${path}`);
    };

    renderAppRoute("/signal-lab/pulse/pulse-titty");

    expect(await screen.findByRole("heading", { name: "$TITTY" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回列表" })).toHaveAttribute("href", "/signal-lab");
  });
});
