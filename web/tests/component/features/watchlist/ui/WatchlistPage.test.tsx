import { WatchlistPage, type WatchlistAccountCase } from "@features/watchlist";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("WatchlistPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
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

    renderWithProviders(<WatchlistPage accountCases={[caseFor("toly")]} token="secret" />, {
      route: "/watchlist?handle=toly",
    });

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

    fireEvent.click(screen.getByRole("tab", { name: "all" }));
    await waitFor(() => expect(screen.getAllByText("All source event").length).toBeGreaterThan(0), {
      timeout: 1_000,
    });
    expect(screen.queryAllByText("First signal")).toHaveLength(0);
  });
});

function timelineItem(eventId: string, summary: string) {
  return {
    event_id: eventId,
    received_at_ms: eventId === "event-2" ? 900 : 1_000,
    author_handle: "toly",
    text_clean: summary,
    cashtags: ["SOL"],
    hashtags: [],
    mentions: [],
    token_resolutions: [],
    social_event: { summary_zh: summary, is_signal_event: true, token_candidates: [] },
  };
}

function caseFor(handle: string): WatchlistAccountCase {
  return {
    emptyState: null,
    handle,
    lastSeenAtMs: 1_700_000_000_000,
    narrativeClusters: [],
    recentEvents: [],
    riskNotes: [],
    searchLinks: [{ href: `/search?q=%40${handle}`, label: "Search account" }],
    tokenMentions: [],
    unreadCount: 0,
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
