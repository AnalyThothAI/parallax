import { screen, waitFor } from "@testing-library/react";
import {
  appStatusFixture,
  notificationSummaryFixture,
  tokenRadarFixture,
} from "@tests/fixtures/appRouteFixtures";
import { ok } from "@tests/msw/fixtures";
import { renderAppRoute } from "@tests/render/renderRoute";
import { beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

beforeEach(() => {
  setupAppRouteTest();
});

describe("watchlist navigation", () => {
  it("renders Watchlist as a primary sidebar route without handle rows in the shell", async () => {
    apiMock.getBootstrapImpl = async () =>
      ok({ ws_token: "test-token", handles: ["toly"], replay_limit: 25 });
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/status") {
        return ok(appStatusFixture({ handles: ["toly"] }));
      }
      if (path === "/api/watchlist/handles/overview") {
        return ok({
          window: "7d",
          items: [
            {
              handle: "toly",
              last_source_event_at_ms: 1_700_000_000_000,
              recent_source_event_count: 2,
            },
          ],
        });
      }
      if (path === "/api/token-radar") {
        return ok(tokenRadarFixture());
      }
      if (path === "/api/notifications") {
        return ok({ items: [], summary: notificationSummaryFixture() });
      }
      return ok({});
    };

    renderAppRoute("/");

    const link = await waitFor(() => screen.getByRole("link", { name: /Watchlist/i }));
    expect(link.getAttribute("href")).toBe("/watchlist");
    expect(screen.queryByRole("link", { name: /toly/i })).not.toBeInTheDocument();
  });

  it("renders selected watchlist facts from the persisted overview", async () => {
    apiMock.getBootstrapImpl = async () =>
      ok({ ws_token: "test-token", handles: ["marionawfal"], replay_limit: 25 });
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/status") {
        return ok(appStatusFixture({ handles: ["marionawfal"] }));
      }
      if (path === "/api/watchlist/handles/overview") {
        return ok({
          window: "7d",
          items: [
            {
              handle: "marionawfal",
              last_source_event_at_ms: 1_700_000_000_000,
              recent_source_event_count: 42,
            },
          ],
        });
      }
      if (path === "/api/watchlist/handle/marionawfal/overview") {
        return ok({
          query: { handle: "marionawfal", window: "3d" },
          metrics: {
            source_event_count: 42,
            resolved_token_count: 0,
            candidate_mention_count: 3,
            hashtag_count: 0,
            last_source_event_at_ms: 1_700_000_000_000,
          },
          resolved_token_clusters: [],
          candidate_mention_clusters: [
            {
              label: "$ALOY",
              count: 3,
              query: "$ALOY",
              kind: "candidate_mention",
              source: "event_cashtags",
              symbol: null,
              target_id: null,
              target_type: null,
            },
          ],
          hashtag_clusters: [],
          clusters_truncated: false,
          risk_notes: ["candidate_mentions_unresolved"],
        });
      }
      if (path === "/api/watchlist/handle/marionawfal/timeline") {
        return ok({
          query: { handle: "marionawfal", limit: 80 },
          items: [],
          has_more: false,
          next_cursor: null,
        });
      }
      if (path === "/api/token-radar") {
        return ok(tokenRadarFixture());
      }
      if (path === "/api/notifications") {
        return ok({ items: [], summary: notificationSummaryFixture() });
      }
      return ok({});
    };

    renderAppRoute("/watchlist?handle=marionawfal");

    expect(
      await screen.findByRole("navigation", { name: "Twitter source list" }),
    ).toHaveTextContent("@marionawfal");
    expect((await screen.findAllByText("Candidate mentions")).length).toBeGreaterThan(0);
    expect(await screen.findByText("$ALOY")).toBeInTheDocument();
    expect(screen.getAllByText("Resolved targets").length).toBeGreaterThan(0);
  });
});
