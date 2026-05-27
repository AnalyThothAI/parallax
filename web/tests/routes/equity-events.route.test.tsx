import { useAppSession } from "@app/useAppSession";
import { AppRouteSessionProvider } from "@routes/AppRouteSessionProvider";
import { createAppMemoryRouter } from "@routes/router";
import { RouteFallback } from "@shared/ui/RouteFallback";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("equity events route", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/equity-events") return ok(equityEventPageFixture());
        if (path === "/api/equity-events/calendar") return ok(equityEventCalendarFixture());
        if (path === "/api/equity-events/event-1") return ok(equityEventDetailFixture());
        if (path === "/api/equity-events/summary") return ok(equityEventSummaryFixture());
        return baseGetApi(path, options);
      };
    });
  });

  it("renders feed rows at /earnings", async () => {
    renderAppRoute("/earnings");

    expect(await screen.findByRole("heading", { name: "Earnings" })).toBeInTheDocument();
    expect(await screen.findByText("NVDA Q3 earnings release")).toBeInTheDocument();
    expect(screen.getByText("后端摘要")).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getByRole("link", { name: /Earnings/i })).toHaveAttribute(
      "data-active",
      "true",
    );
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/equity-events", {
        params: { limit: 100 },
        token: "secret",
      }),
    );
  });

  it("renders Load More and fetches the next feed cursor", async () => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/equity-events") {
          return ok(
            equityEventPageFixture({
              headline:
                options?.params?.cursor === "cursor-next"
                  ? "NVDA next cursor earnings release"
                  : "NVDA Q3 earnings release",
              nextCursor: options?.params?.cursor === "cursor-next" ? null : "cursor-next",
            }),
          );
        }
        if (path === "/api/equity-events/calendar") return ok(equityEventCalendarFixture());
        if (path === "/api/equity-events/summary") return ok(equityEventSummaryFixture());
        return baseGetApi(path, options);
      };
    });

    const { router } = renderAppRouteWithRouter("/earnings");

    expect(await screen.findByText("NVDA Q3 earnings release")).toBeInTheDocument();
    const loadMore = screen.queryByRole("button", { name: /load more/i });
    expect(loadMore).toBeInTheDocument();
    fireEvent.click(loadMore as HTMLElement);

    await waitFor(() => expect(router.state.location.search).toBe("?cursor=cursor-next"));
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/equity-events", {
        params: { cursor: "cursor-next", limit: 100 },
        token: "secret",
      }),
    );
    expect(await screen.findByText("NVDA next cursor earnings release")).toBeInTheDocument();
  });

  it("renders calendar rows at /earnings/calendar", async () => {
    renderAppRoute("/earnings/calendar");

    expect(await screen.findByRole("heading", { name: "Earnings" })).toBeInTheDocument();
    expect(await screen.findByText("AAPL expected Q4 earnings release")).toBeInTheDocument();
    expect(screen.getByText("MSFT Q4 earnings release matched")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/equity-events/calendar", {
        token: "secret",
      }),
    );
  });

  it("renders event detail at /earnings/events/event-1", async () => {
    renderAppRoute("/earnings/events/event-1");

    expect(
      await screen.findByRole("heading", { name: "NVDA Q3 earnings release" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("后端事实解读")).toBeInTheDocument();
    expect(screen.getByText("AI capex earnings cluster")).toBeInTheDocument();
    expect(screen.getByText("Revenue increased year over year.")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/equity-events/event-1", {
        token: "secret",
      }),
    );
  });

  it("renders empty and error page states", async () => {
    setupAppRouteTest((mock) => {
      mockLiveRadarRoute(mock);
      const baseGetApi = mock.getApiImpl;
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/equity-events") return ok({ items: [], next_cursor: null });
        if (path === "/api/equity-events/calendar") throw new Error("calendar unavailable");
        return baseGetApi(path, options);
      };
    });

    renderAppRoute("/earnings");
    expect(await screen.findByText("No equity event rows")).toHaveTextContent(
      "No equity event rows",
    );

    renderAppRoute("/earnings/calendar");
    expect(await screen.findByText("calendar unavailable")).toBeInTheDocument();
  });
});

function renderAppRouteWithRouter(route = "/") {
  const router = createAppMemoryRouter({ initialEntries: [route] });
  return {
    router,
    ...renderWithProviders(<TestRouteApp router={router} />, { withRouter: false }),
  };
}

function TestRouteApp({ router }: { router: ReturnType<typeof createAppMemoryRouter> }) {
  const session = useAppSession();
  return (
    <AppRouteSessionProvider session={session}>
      <RouterProvider router={router} fallbackElement={<RouteFallback />} />
    </AppRouteSessionProvider>
  );
}

function equityEventPageFixture({
  headline = "NVDA Q3 earnings release",
  nextCursor = null,
}: {
  headline?: string;
  nextCursor?: string | null;
} = {}) {
  return {
    items: [
      {
        company_event_id: "event-1",
        ticker: "NVDA",
        company_name: "NVIDIA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "official_issuer",
        latest_event_at_ms: 1_765_000_000_000,
        headline,
        summary: "Revenue acceleration.",
        brief_json: {
          status: "ready",
          direction: "bullish",
          decision_class: "driver",
          summary_zh: "后端摘要",
          event_read_zh: "后端事件解读",
        },
      },
    ],
    next_cursor: nextCursor,
  };
}

function equityEventCalendarFixture() {
  return {
    items: [
      {
        expected_event_id: "expected-aapl",
        ticker: "AAPL",
        company_name: "Apple",
        event_type: "earnings_release",
        priority: "P1",
        source_role: "calendar",
        fiscal_period: "Q4",
        expected_at_ms: 1_765_200_000_000,
        status: "expected",
        headline: "AAPL expected Q4 earnings release",
      },
      {
        expected_event_id: "matched-msft",
        ticker: "MSFT",
        company_name: "Microsoft",
        event_type: "earnings_release",
        priority: "P1",
        source_role: "calendar",
        fiscal_period: "Q4",
        expected_at_ms: 1_765_100_000_000,
        status: "matched",
        headline: "MSFT Q4 earnings release matched",
        calendar_json: { observed_company_event_id: "event-msft" },
      },
    ],
  };
}

function equityEventDetailFixture() {
  return {
    company_event_id: "event-1",
    ticker: "NVDA",
    company_name: "NVIDIA",
    event_type: "earnings_release",
    priority: "P0",
    source_role: "official_issuer",
    latest_event_at_ms: 1_765_000_000_000,
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
        value_numeric: 35000,
        value_unit: "USD millions",
        validation_status: "accepted",
      },
    ],
    spans_json: [
      {
        span_id: "span-1",
        evidence_quote: "Revenue increased year over year.",
        confidence: 0.91,
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
  };
}

function equityEventSummaryFixture() {
  return {
    p0_open_count: 1,
    today_count: 2,
    due_brief_queue_count: 0,
    retryable_brief_failure_count: 0,
    stale_brief_count: 0,
    historical_backlog_count: 0,
    latest_material_event_at_ms: 1_765_000_000_000,
    latest_source_success_at_ms: 1_765_000_000_000,
    latest_evidence_ready_at_ms: 1_765_000_000_000,
    latest_projection_at_ms: 1_765_000_000_000,
    calendar_configured: true,
  };
}
