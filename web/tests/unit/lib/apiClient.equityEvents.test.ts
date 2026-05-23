import {
  fetchEquityEventCalendar,
  fetchEquityEventDetail,
  fetchEquityEventSummary,
  fetchEquityEvents,
} from "@lib/api/client";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("equity events API client normalization", () => {
  it("normalizes paged rows with pending, ready, and stale brief statuses", async () => {
    mockFetch((url, init) => {
      if (url.pathname === "/api/equity-events") {
        expect(url.searchParams.get("limit")).toBe("3");
        expect(url.searchParams.get("ticker")).toBe("NVDA");
        expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
        return {
          ok: true,
          data: {
            items: [
              {
                company_event_id: "event-pending",
                ticker: "nvda",
                event_type: "earnings_release",
                priority: "P0",
                source_role: "official_issuer",
                latest_event_at_ms: "1765000000000",
                headline: "NVDA earnings",
                brief_json: { status: "pending" },
              },
              {
                company_event_id: "event-ready",
                ticker: "MSFT",
                event_type: "guidance_update",
                priority: "P1",
                source_role: "official_regulator",
                latest_event_at_ms: 1765100000000,
                brief_json: {
                  status: "ready",
                  direction: "bullish",
                  decision_class: "driver",
                  summary_zh: "后端摘要",
                  event_read_zh: "后端事件解读",
                  watch_triggers: ["gross margin"],
                },
              },
              {
                company_event_id: "event-stale",
                ticker: "TSLA",
                event_type: "quarterly_report",
                priority: "P2",
                source_role: "official_regulator",
                latest_event_at_ms: 1764900000000,
                brief_json: { status: "stale", data_gaps: ["fresh filing parse pending"] },
              },
            ],
            next_cursor: "1764900000000:event-stale",
          },
        };
      }
      throw new Error(`unexpected path ${url.pathname}`);
    });

    const page = await fetchEquityEvents({ limit: 3, ticker: "NVDA", token: "test-token" });

    expect(page.next_cursor).toBe("1764900000000:event-stale");
    expect(page.items.map((row) => row.ticker)).toEqual(["NVDA", "MSFT", "TSLA"]);
    expect(page.items.map((row) => row.brief.status)).toEqual(["pending", "ready", "stale"]);
    expect(page.items[1].brief.summary_zh).toBe("后端摘要");
    expect(page.items[1].latest_event_at_ms).toBe(1_765_100_000_000);
    expect(page.items[2].brief.data_gaps).toEqual([
      { description_zh: "fresh filing parse pending", severity: null },
    ]);
  });

  it("normalizes calendar rows with expected, matched, and missed statuses", async () => {
    mockFetch((url) => {
      expect(url.pathname).toBe("/api/equity-events/calendar");
      return {
        ok: true,
        data: {
          items: [
            {
              expected_event_id: "expected-1",
              ticker: "AAPL",
              event_type: "earnings_release",
              expected_at_ms: "1765200000000",
              status: "expected",
              calendar_json: { session: "after_close" },
            },
            {
              expected_event_id: "matched-1",
              ticker: "MSFT",
              event_type: "quarterly_report",
              expected_at_ms: 1765100000000,
              status: "matched",
              calendar_json: { observed_company_event_id: "event-msft" },
            },
            {
              expected_event_id: "missed-1",
              ticker: "TSLA",
              event_type: "earnings_release",
              expected_at_ms: 1765000000000,
              status: "missed",
            },
          ],
        },
      };
    });

    const calendar = await fetchEquityEventCalendar({ status: "expected" });

    expect(calendar.items.map((row) => row.status)).toEqual(["expected", "matched", "missed"]);
    expect(calendar.items[0].calendar.session).toBe("after_close");
    expect(calendar.items[1].observed_company_event_id).toBe("event-msft");
  });

  it("normalizes detail documents, facts, spans, story, and brief payloads", async () => {
    mockFetch((url) => {
      expect(url.pathname).toBe("/api/equity-events/event-1");
      return {
        ok: true,
        data: {
          company_event_id: "event-1",
          ticker: "NVDA",
          company_name: "NVIDIA",
          event_type: "earnings_release",
          priority: "P0",
          source_role: "official_issuer",
          latest_event_at_ms: 1765000000000,
          headline: "NVDA Q3 earnings release",
          documents_json: [
            {
              event_document_id: "doc-1",
              document_type: "press_release",
              document_url: "https://example.com/nvda",
            },
          ],
          facts_json: [
            {
              fact_candidate_id: "fact-1",
              metric_name: "revenue",
              value_numeric: "35000",
              value_unit: "USD millions",
              validation_status: "accepted",
            },
          ],
          spans_json: [
            {
              span_id: "span-1",
              evidence_quote: "Revenue increased year over year.",
              confidence: "0.91",
            },
          ],
          story_json: {
            story_id: "story-1",
            representative_headline: "AI capex earnings cluster",
            event_count: 2,
          },
          brief_json: {
            status: "ready",
            direction: "mixed",
            decision_class: "watch",
            summary_zh: "来自后端的详情摘要",
            event_read_zh: "后端事实解读",
            evidence_refs: ["fact:fact-1"],
          },
        },
      };
    });

    const detail = await fetchEquityEventDetail({ eventId: "event-1" });

    expect(detail.company_event_id).toBe("event-1");
    expect(detail.documents[0].event_document_id).toBe("doc-1");
    expect(detail.facts[0].value_numeric).toBe(35_000);
    expect(detail.spans[0].confidence).toBe(0.91);
    expect(detail.story?.story_id).toBe("story-1");
    expect(detail.brief.evidence_refs).toEqual(["fact:fact-1"]);
  });

  it("normalizes the compact equity event summary", async () => {
    mockFetch((url) => {
      expect(url.pathname).toBe("/api/equity-events/summary");
      return {
        ok: true,
        data: {
          p0_open_count: "2",
          today_count: 5,
          brief_pending_count: "3",
          latest_event_at_ms: "1765000000000",
        },
      };
    });

    await expect(fetchEquityEventSummary()).resolves.toEqual({
      p0_open_count: 2,
      today_count: 5,
      brief_pending_count: 3,
      latest_event_at_ms: 1_765_000_000_000,
    });
  });
});

function mockFetch(handler: (url: URL, init?: RequestInit) => unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input));
      const body = handler(url, init);
      return new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      });
    }),
  );
}
