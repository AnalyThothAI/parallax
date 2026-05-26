import {
  buildEquityEventFeedModel,
  equityCalendarStatusLabel,
  equityEventBriefStatusLabel,
  equityEventPriorityRank,
  normalizeEquityCalendarRow,
  normalizeEquityEventRow,
  sortEquityEventRows,
} from "@features/equity-events";
import { describe, expect, it } from "vitest";

describe("equity event view model", () => {
  it("normalizes rows and sorts by priority before event time", () => {
    const oldP0 = normalizeEquityEventRow({
      company_event_id: "p0-old",
      ticker: "nvda",
      event_type: "earnings_release",
      priority: "P0",
      source_role: "official_issuer",
      latest_event_at_ms: 100,
      brief_json: { status: "ready" },
    });
    const newP2 = normalizeEquityEventRow({
      company_event_id: "p2-new",
      ticker: "aapl",
      event_type: "guidance_update",
      priority: "P2",
      source_role: "official_regulator",
      latest_event_at_ms: 200,
      brief_json: { status: "pending" },
    });

    expect(oldP0.ticker).toBe("NVDA");
    expect(equityEventPriorityRank(oldP0.priority)).toBeLessThan(
      equityEventPriorityRank(newP2.priority),
    );
    expect(sortEquityEventRows([newP2, oldP0]).map((row) => row.company_event_id)).toEqual([
      "p0-old",
      "p2-new",
    ]);
  });

  it("labels brief and calendar statuses without collapsing backend states", () => {
    expect(equityEventBriefStatusLabel("pending")).toBe("pending brief");
    expect(equityEventBriefStatusLabel("ready")).toBe("brief ready");
    expect(equityEventBriefStatusLabel("stale")).toBe("brief stale");
    expect(equityCalendarStatusLabel("expected")).toBe("expected");
    expect(equityCalendarStatusLabel("matched")).toBe("matched");
    expect(equityCalendarStatusLabel("missed")).toBe("missed");
  });

  it("builds dense feed summary and empty state labels", () => {
    const model = buildEquityEventFeedModel([
      normalizeEquityEventRow({
        company_event_id: "event-1",
        ticker: "NVDA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "official_issuer",
        latest_event_at_ms: 200,
        brief_json: { status: "ready", decision_class: "driver" },
      }),
      normalizeEquityEventRow({
        company_event_id: "event-2",
        ticker: "MSFT",
        event_type: "guidance_update",
        priority: "P1",
        source_role: "official_regulator",
        latest_event_at_ms: 100,
        brief_json: { status: "pending" },
      }),
    ]);

    expect(model.summary).toEqual({
      total: 2,
      p0: 1,
      ready: 1,
      pending: 1,
      drivers: 1,
    });
    expect(buildEquityEventFeedModel([]).emptyTitle).toBe("No equity event rows");
  });

  it("preserves backend incoming order by default", () => {
    const rows = [
      normalizeEquityEventRow({
        company_event_id: "p2-first",
        ticker: "MSFT",
        event_type: "guidance_update",
        priority: "P2",
        source_role: "official_regulator",
        latest_event_at_ms: 300,
      }),
      normalizeEquityEventRow({
        company_event_id: "p0-second",
        ticker: "NVDA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "official_issuer",
        latest_event_at_ms: 100,
      }),
    ];

    expect(buildEquityEventFeedModel(rows).rows.map((row) => row.company_event_id)).toEqual([
      "p2-first",
      "p0-second",
    ]);
  });

  it("sorts by priority when priority ordering is requested", () => {
    const rows = [
      normalizeEquityEventRow({
        company_event_id: "p2-first",
        ticker: "MSFT",
        event_type: "guidance_update",
        priority: "P2",
        source_role: "official_regulator",
        latest_event_at_ms: 300,
      }),
      normalizeEquityEventRow({
        company_event_id: "p0-second",
        ticker: "NVDA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "official_issuer",
        latest_event_at_ms: 100,
      }),
    ];

    expect(
      buildEquityEventFeedModel(rows, { ordering: "priority" }).rows.map(
        (row) => row.company_event_id,
      ),
    ).toEqual(["p0-second", "p2-first"]);
  });

  it("normalizes calendar aliases for observed matches", () => {
    const row = normalizeEquityCalendarRow({
      expected_event_id: "expected-1",
      ticker: "msft",
      event_type: "earnings_release",
      expected_at_ms: "1765100000000",
      status: "matched",
      calendar_json: { observed_company_event_id: "event-msft" },
    });

    expect(row.ticker).toBe("MSFT");
    expect(row.expected_at_ms).toBe(1_765_100_000_000);
    expect(row.observed_company_event_id).toBe("event-msft");
  });
});
