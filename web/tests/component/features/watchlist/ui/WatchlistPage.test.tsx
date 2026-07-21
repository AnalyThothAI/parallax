import { WatchlistPage } from "@features/watchlist";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("WatchlistPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the full source navigator and keeps timeline scope when switching handles", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      requests.push(`${url.pathname}?${url.searchParams.toString()}`);
      if (url.pathname === "/api/watchlist/handles/overview") {
        return jsonResponse({
          ok: true,
          data: {
            window: "7d",
            items: [
              {
                handle: "toly",
                last_source_event_at_ms: 1_700_000_000_000,
                recent_source_event_count: 3,
                recent_signal_event_count: 2,
                total_signal_event_count: 12,
                summary_status: "ready",
                summary_is_stale: false,
              },
              {
                handle: "marionawfal",
                last_source_event_at_ms: 1_700_000_060_000,
                recent_source_event_count: 42,
                recent_signal_event_count: 12,
                total_signal_event_count: 42,
                summary_status: "ready",
                summary_is_stale: true,
              },
              {
                handle: "gdb",
                last_source_event_at_ms: null,
                recent_source_event_count: 0,
                recent_signal_event_count: 0,
                total_signal_event_count: 0,
                summary_status: "not_ready",
                summary_is_stale: false,
              },
            ],
          },
        });
      }
      if (url.pathname.endsWith("/summary")) {
        const handle = handleFromWatchlistPath(url.pathname);
        return jsonResponse({
          ok: true,
          data: {
            handle,
            status: "ready",
            generated_at_ms: 1_700_000_000_000,
            staleness_ms: 0,
            is_stale: handle === "marionawfal",
            pending_recompute: false,
            signal_count: handle === "marionawfal" ? 12 : 2,
            input_event_count: handle === "marionawfal" ? 42 : 3,
            signal_count_at_generation: handle === "marionawfal" ? 12 : 2,
            model: "test-model",
            summary_zh: `${handle} summary`,
            topics: [],
          },
        });
      }
      if (url.pathname.endsWith("/overview")) {
        const handle = handleFromWatchlistPath(url.pathname);
        return jsonResponse({
          ok: true,
          data: handleOverviewResponse(handle, url.searchParams.get("scope") ?? "signal"),
        });
      }
      const handle = handleFromWatchlistPath(url.pathname);
      return jsonResponse({
        ok: true,
        data: {
          query: { handle, scope: url.searchParams.get("scope"), limit: 30 },
          items: [timelineItem(`${handle}-event`, `${handle} timeline`)],
          has_more: false,
          next_cursor: null,
        },
      });
    });

    renderWithProviders(
      <WatchlistPage
        accountUnreadCounts={{ marionawfal: 4 }}
        handles={["toly", "marionawfal", "gdb"]}
        token="secret"
      />,
      {
        route: "/watchlist?handle=toly&timeline_scope=all",
      },
    );

    const sourceList = await screen.findByRole("navigation", { name: "Twitter source list" });
    expect(sourceList).toHaveTextContent("@marionawfal");
    await waitFor(() => expect(sourceList).toHaveTextContent("42 posts"));
    expect(sourceList).toHaveTextContent("@toly");
    expect(sourceList).toHaveTextContent("@gdb");
    expect(screen.getByRole("link", { name: /@marionawfal/i })).toHaveAttribute(
      "href",
      "/watchlist?handle=marionawfal&timeline_scope=all",
    );

    fireEvent.click(screen.getByRole("link", { name: /@marionawfal/i }));

    await waitFor(() =>
      expect(
        requests.some((request) =>
          request.includes("/api/watchlist/handle/marionawfal/overview?scope=all"),
        ),
      ).toBe(true),
    );
    expect(await screen.findByRole("heading", { name: "@marionawfal" })).toBeInTheDocument();
  });

  it("appends cursor pages and resets the stream when scope changes", async () => {
    const requests: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      requests.push(`${url.pathname}?${url.searchParams.toString()}`);
      if (url.pathname.endsWith("/summary")) {
        return jsonResponse({
          ok: true,
          data: {
            handle: "toly",
            status: "ready",
            generated_at_ms: 1_700_000_000_000,
            staleness_ms: 0,
            is_stale: false,
            pending_recompute: false,
            signal_count: 2,
            input_event_count: 2,
            signal_count_at_generation: 2,
            model: "test-model",
            summary_zh: "Toly 正在跟踪 SOL 生态信号。",
            topics: [{ title: "SOL", event_count: 2, description: "SOL 生态持续出现。" }],
          },
        });
      }
      if (url.pathname.endsWith("/overview")) {
        return jsonResponse({
          ok: true,
          data: {
            query: { handle: "toly", scope: url.searchParams.get("scope"), window: "7d" },
            metrics: {
              source_event_count: 2,
              signal_event_count: 2,
              resolved_token_count: 1,
              candidate_mention_count: 1,
              narrative_count: 0,
              last_source_event_at_ms: 1_700_000_000_000,
            },
            resolved_token_clusters: [
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
            candidate_mention_clusters: [
              {
                label: "$ALOY",
                count: 1,
                query: "$ALOY",
                kind: "candidate_mention",
                source: "social_event_candidates",
              },
            ],
            narrative_clusters: [],
            risk_notes: ["candidate_mentions_unresolved"],
          },
        });
      }
      const scope = url.searchParams.get("scope");
      const cursor = url.searchParams.get("cursor");
      return jsonResponse({
        ok: true,
        data: {
          query: { handle: "toly", scope, limit: 30 },
          items:
            scope === "all"
              ? [timelineItem("all-event", "All source event")]
              : [
                  timelineItem(
                    cursor ? "event-2" : "event-1",
                    cursor ? "Second signal" : "First signal",
                  ),
                ],
          has_more: scope === "signal" && !cursor,
          next_cursor: scope === "signal" && !cursor ? "cursor-1" : null,
        },
      });
    });

    renderWithProviders(
      <WatchlistPage accountUnreadCounts={{ toly: 2 }} handles={["toly"]} token="secret" />,
      {
        route: "/watchlist?handle=toly&timeline_scope=signal",
      },
    );

    await waitFor(
      () => expect(screen.getAllByText("Candidate mentions").length).toBeGreaterThan(0),
      {
        timeout: 1_000,
      },
    );
    await waitFor(() => expect(screen.getAllByText("$ALOY").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Resolved targets").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "$SOL1 event" })).toHaveAttribute(
      "href",
      "/token/Asset/asset%3Asolana%3Atoken%3ASo11111111111111111111111111111111111111112",
    );

    await waitFor(() => expect(screen.getAllByText("First signal").length).toBeGreaterThan(0), {
      timeout: 1_000,
    });
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(
      () => expect(requests.some((value) => value.includes("cursor=cursor-1"))).toBe(true),
      {
        timeout: 1_000,
      },
    );
    await waitFor(() => expect(screen.getAllByText("Second signal").length).toBeGreaterThan(0), {
      timeout: 1_000,
    });
    expect(screen.getAllByText("$SOL").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$0.104").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gmgn_dex_quote").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("tab", { name: "all" }));
    await waitFor(() => expect(screen.getAllByText("All source event").length).toBeGreaterThan(0), {
      timeout: 1_000,
    });
    expect(screen.queryAllByText("First signal")).toHaveLength(0);
  });

  it("shows candidate mentions separately when resolved targets are empty", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/overview")) {
        return jsonResponse({
          ok: true,
          data: {
            query: { handle: "marionawfal", scope: "signal", window: "7d" },
            metrics: {
              source_event_count: 42,
              signal_event_count: 42,
              resolved_token_count: 0,
              candidate_mention_count: 3,
              narrative_count: 0,
              last_source_event_at_ms: 1_700_000_000_000,
            },
            resolved_token_clusters: [],
            candidate_mention_clusters: [
              {
                label: "$ALOY",
                count: 3,
                query: "$ALOY",
                kind: "candidate_mention",
                source: "social_event_candidates",
              },
            ],
            narrative_clusters: [],
            risk_notes: ["candidate_mentions_unresolved"],
          },
        });
      }
      if (url.pathname.endsWith("/summary")) {
        return jsonResponse({
          ok: true,
          data: {
            handle: "marionawfal",
            status: "not_ready",
            is_stale: false,
            pending_recompute: false,
            signal_count: 42,
            input_event_count: 0,
            signal_count_at_generation: 0,
            summary_zh: "",
            topics: [],
          },
        });
      }
      return jsonResponse({
        ok: true,
        data: {
          query: { handle: "marionawfal", scope: "signal", limit: 30 },
          items: [],
          has_more: false,
          next_cursor: null,
        },
      });
    });

    renderWithProviders(<WatchlistPage handles={["marionawfal"]} token="secret" />, {
      route: "/watchlist?handle=marionawfal&timeline_scope=signal",
    });

    await waitFor(() =>
      expect(screen.getAllByText("Candidate mentions").length).toBeGreaterThan(0),
    );
    await waitFor(() => expect(screen.getByText("$ALOY")).toBeInTheDocument());
    expect(screen.getAllByText("Resolved targets").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });

  it("keeps source-only timeline text visible in all mode", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/overview")) {
        return jsonResponse({
          ok: true,
          data: {
            query: { handle: "gdb", scope: "all", window: "7d" },
            metrics: {
              source_event_count: 1,
              signal_event_count: 0,
              resolved_token_count: 0,
              candidate_mention_count: 0,
              narrative_count: 0,
              last_source_event_at_ms: 1_700_000_000_000,
            },
            resolved_token_clusters: [],
            candidate_mention_clusters: [],
            narrative_clusters: [],
            risk_notes: [],
          },
        });
      }
      if (url.pathname.endsWith("/summary")) {
        return jsonResponse({
          ok: true,
          data: {
            handle: "gdb",
            status: "not_ready",
            is_stale: false,
            pending_recompute: false,
            signal_count: 0,
            input_event_count: 0,
            signal_count_at_generation: 0,
            summary_zh: "",
            topics: [],
          },
        });
      }
      return jsonResponse({
        ok: true,
        data: {
          query: { handle: "gdb", scope: "all", limit: 30 },
          items: [
            {
              event_id: "source-1",
              received_at_ms: 1_700_000_000_000,
              author_handle: "gdb",
              text_clean: "so much to build",
              cashtags: [],
              hashtags: [],
              mentions: [],
              token_resolutions: [],
              social_event: null,
            },
          ],
          has_more: false,
          next_cursor: null,
        },
      });
    });

    renderWithProviders(<WatchlistPage handles={["gdb"]} token="secret" />, {
      route: "/watchlist?handle=gdb&timeline_scope=all",
    });

    await waitFor(() => expect(screen.getByText("so much to build")).toBeVisible());
  });
});

function handleOverviewResponse(handle: string, scope: string) {
  return {
    query: { handle, scope, window: "7d" },
    metrics: {
      source_event_count: handle === "marionawfal" ? 42 : 2,
      signal_event_count: handle === "marionawfal" ? 12 : 2,
      resolved_token_count: 1,
      candidate_mention_count: handle === "marionawfal" ? 3 : 1,
      narrative_count: 0,
      last_source_event_at_ms: 1_700_000_000_000,
    },
    resolved_token_clusters: [],
    candidate_mention_clusters: [],
    narrative_clusters: [],
    risk_notes: [],
  };
}

function handleFromWatchlistPath(pathname: string): string {
  const match = pathname.match(/\/api\/watchlist\/handle\/([^/]+)\//);
  return match ? decodeURIComponent(match[1]) : "toly";
}

function timelineItem(eventId: string, summary: string) {
  return {
    event_id: eventId,
    received_at_ms: eventId === "event-2" ? 900 : 1_000,
    author_handle: "toly",
    text_clean: summary,
    cashtags: ["SOL"],
    hashtags: [],
    mentions: [],
    token_resolutions: [
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
    ],
    social_event: { summary_zh: summary, is_signal_event: true, token_candidates: [] },
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
