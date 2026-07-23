import { WatchlistPage } from "@features/watchlist";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("WatchlistPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders persisted source activity and links by handle only", async () => {
    installWatchlistApi();

    renderWithProviders(
      <WatchlistPage
        accountUnreadCounts={{ marionawfal: 4 }}
        handles={["toly", "marionawfal", "gdb"]}
        token="secret"
      />,
      { route: "/watchlist?handle=toly" },
    );

    const sourceList = await screen.findByRole("navigation", { name: "Twitter source list" });
    await waitFor(() => expect(sourceList).toHaveTextContent("42 posts"));
    expect(sourceList).toHaveTextContent("@toly");
    expect(sourceList).toHaveTextContent("@marionawfal");
    expect(sourceList).toHaveTextContent("@gdb");
    expect(screen.getByRole("link", { name: /@marionawfal/i })).toHaveAttribute(
      "href",
      "/watchlist?handle=marionawfal",
    );
    expect(screen.queryByRole("tablist", { name: /timeline scope/i })).not.toBeInTheDocument();
  });

  it("pages the raw event stream without sending a fake scope", async () => {
    const requests: string[] = [];
    installWatchlistApi(requests);

    renderWithProviders(<WatchlistPage handles={["toly"]} token="secret" />, {
      route: "/watchlist?handle=toly",
    });

    await waitFor(() => expect(screen.getByText("First source event")).toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText("Second source event")).toBeVisible());

    expect(requests.some((request) => request.includes("scope="))).toBe(false);
    expect(requests.some((request) => request.includes("/timeline?cursor=cursor-1&limit=80"))).toBe(
      true,
    );
    expect(screen.getByRole("link", { name: "$SOL1 event" })).toHaveAttribute(
      "href",
      "/token/Asset/asset%3Asolana%3Atoken%3ASo11111111111111111111111111111111111111112",
    );
  });

  it("keeps source-only text visible without a social-event projection", async () => {
    installWatchlistApi([], { sourceOnly: true });

    renderWithProviders(<WatchlistPage handles={["gdb"]} token="secret" />, {
      route: "/watchlist?handle=gdb",
    });

    expect(await screen.findByText("so much to build")).toBeVisible();
  });
});

function installWatchlistApi(requests: string[] = [], options: { sourceOnly?: boolean } = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = new URL(String(input));
    requests.push(`${url.pathname}?${url.searchParams.toString()}`);
    if (url.pathname === "/api/watchlist/handles/overview") {
      return jsonResponse({
        ok: true,
        data: {
          window: "3d",
          items: [
            handleRow("toly", 3, 1_700_000_000_000),
            handleRow("marionawfal", 42, 1_700_000_060_000),
            handleRow("gdb", 0, null),
          ],
        },
      });
    }
    if (url.pathname.endsWith("/overview")) {
      const handle = handleFromWatchlistPath(url.pathname);
      return jsonResponse({
        ok: true,
        data: {
          query: { handle, window: "3d" },
          metrics: {
            source_event_count: handle === "marionawfal" ? 42 : 2,
            resolved_token_count: options.sourceOnly ? 0 : 1,
            candidate_mention_count: 0,
            hashtag_count: 0,
            last_source_event_at_ms: 1_700_000_000_000,
          },
          resolved_token_clusters: options.sourceOnly
            ? []
            : [
                {
                  label: "$SOL",
                  count: 1,
                  query: "$SOL",
                  kind: "resolved_token",
                  target_type: "Asset",
                  target_id: "asset:solana:token:So11111111111111111111111111111111111111112",
                  symbol: "SOL",
                  source: "token_resolutions",
                },
              ],
          candidate_mention_clusters: [],
          hashtag_clusters: [],
          clusters_truncated: false,
          risk_notes: [],
        },
      });
    }
    const handle = handleFromWatchlistPath(url.pathname);
    if (options.sourceOnly) {
      return jsonResponse({
        ok: true,
        data: {
          query: { handle, limit: 80 },
          items: [sourceTimelineItem("source-1", "so much to build")],
          has_more: false,
          next_cursor: null,
        },
      });
    }
    const cursor = url.searchParams.get("cursor");
    return jsonResponse({
      ok: true,
      data: {
        query: { handle, limit: 80 },
        items: [
          sourceTimelineItem(
            cursor ? "event-2" : "event-1",
            cursor ? "Second source event" : "First source event",
          ),
        ],
        has_more: !cursor,
        next_cursor: cursor ? null : "cursor-1",
      },
    });
  });
}

function handleRow(handle: string, recentSourceCount: number, lastSeenAtMs: number | null) {
  return {
    handle,
    last_source_event_at_ms: lastSeenAtMs,
    recent_source_event_count: recentSourceCount,
  };
}

function handleFromWatchlistPath(pathname: string): string {
  const match = pathname.match(/\/api\/watchlist\/handle\/([^/]+)\//);
  return match ? decodeURIComponent(match[1]) : "toly";
}

function sourceTimelineItem(eventId: string, text: string) {
  return {
    event_id: eventId,
    received_at_ms: eventId === "event-2" ? 900 : 1_000,
    author_handle: "toly",
    action: "tweet",
    text_clean: text,
    canonical_url: `https://x.com/toly/status/${eventId}`,
    cashtags: eventId.startsWith("event") ? ["SOL"] : [],
    hashtags: [],
    mentions: [],
    event: {
      event_id: eventId,
      action: "tweet",
      canonical_url: `https://x.com/toly/status/${eventId}`,
      received_at_ms: eventId === "event-2" ? 900 : 1_000,
      author_handle: "toly",
      text_clean: text,
    },
    token_resolutions: eventId.startsWith("event")
      ? [
          {
            event_id: eventId,
            target_type: "Asset",
            target_id: "asset:solana:token:So11111111111111111111111111111111111111112",
            symbol: "SOL",
            resolution_status: "EXACT",
            price: {
              status: "ready",
              provider: "gmgn_dex_quote",
              price_usd: 0.104,
              observation_id: `tick:${eventId}`,
            },
          },
        ]
      : [],
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
