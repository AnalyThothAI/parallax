import { NewsPage } from "@features/news";
import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import type { NewsItemDetail, NewsRow } from "@shared/model/newsIntel";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@lib/api/client", () => ({
  fetchNewsItem: vi.fn(),
  fetchNewsRows: vi.fn(),
}));

const fetchNewsRowsMock = vi.mocked(fetchNewsRows);
const fetchNewsItemMock = vi.mocked(fetchNewsItem);

type ObservedNewsParams = {
  cursor: string | null;
  has_token: boolean;
  limit: number;
  min_score: number | null;
  q: string | null;
  signal: string | null;
  status: string | null;
  token: string;
};

const defaultNewsFetchParams: ObservedNewsParams = {
  cursor: null,
  has_token: true,
  limit: 100,
  min_score: null,
  q: null,
  signal: null,
  status: null,
  token: "test-token",
};

describe("NewsPage", () => {
  beforeEach(() => {
    fetchNewsRowsMock.mockReset();
    fetchNewsItemMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders a compact provider-signal tape with a right inspector", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    await waitFor(() => expect(fetchNewsRowsMock).toHaveBeenCalled());
    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    expect(screen.getByText("有 Token")).toBeInTheDocument();
    expect(screen.getByText("无 Token")).toBeInTheDocument();
    expect(screen.getAllByText("利好").length).toBeGreaterThan(0);
    expect(screen.getAllByText("A · 82").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BTC").length).toBeGreaterThan(0);
    expect(screen.getByText("Provider signal")).toBeInTheDocument();
    expect(screen.queryByText("Content")).not.toBeInTheDocument();
    expect(screen.queryByText("Decision")).not.toBeInTheDocument();
    expect(fetchNewsRowsMock).toHaveBeenCalledWith(defaultNewsFetchParams);
  });

  it("requests backend hard-cut filters from token, signal, score, and search controls", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "无 Token" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        has_token: false,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "利空" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        has_token: false,
        signal: "bearish",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "≥70" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        has_token: false,
        min_score: 70,
        signal: "bearish",
      }),
    );

    fireEvent.change(screen.getByLabelText("Search news"), { target: { value: "eth" } });
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        has_token: false,
        min_score: 70,
        q: "eth",
        signal: "bearish",
      }),
    );
  });

  it("routes the compact tape open action to the news item page", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /^open btc etf flows expand/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/news/items/news-1");
  });

  it("renders OpenNews provider fact instead of Agent memo when signal source is provider", async () => {
    fetchNewsItemMock.mockResolvedValue(providerDetail);

    renderNews(<NewsPage newsItemId="news-1" token="test-token" />);

    await waitFor(() =>
      expect(fetchNewsItemMock).toHaveBeenCalledWith({
        newsItemId: "news-1",
        token: "test-token",
      }),
    );
    expect((await screen.findAllByText("Provider signal")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("利好").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BTC").length).toBeGreaterThan(0);
    expect(screen.queryByText("Agent memo")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /original/i })).toHaveAttribute(
      "href",
      "https://example.test/news-1",
    );
  });
});

function renderNews(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/news"]}>
      <QueryClientProvider client={queryClient}>
        {children}
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function mockNewsRows() {
  fetchNewsRowsMock.mockResolvedValue({
    items: [providerRow],
    next_cursor: null,
  });
}

const providerRow: NewsRow = {
  row_id: "row-1",
  news_item_id: "news-1",
  lifecycle_status: "processed",
  headline: "BTC ETF flows expand",
  summary: "ETF desk activity stays elevated.",
  latest_at_ms: 1_779_000_000_000,
  source_domain: "6551.io",
  canonical_url: "https://example.test/news-1",
  signal: {
    source: "provider",
    provider: "opennews",
    status: "ready",
    direction: "bullish",
    label_zh: "利好",
    signal: "long",
    score: 82,
    grade: "A",
    summary_zh: "ETF 资金流持续增强。",
    method: "opennews.aiRating",
  },
  token_lanes: [
    {
      lane: "resolved",
      resolution_status: "resolved",
      symbol: "BTC",
      target_id: "token:btc",
      provider_signal: "long",
      provider_score: 82,
      provider_grade: "A",
      market_type: "cex",
    },
  ],
  fact_lanes: [{ event_type: "fund_flow", status: "accepted" }],
};

const providerDetail: NewsItemDetail = {
  ...providerRow,
  content: "OpenNews source content.",
  source: {
    provider_type: "opennews",
    source_domain: "6551.io",
    source_name: "OpenNews",
    source_quality_status: "healthy",
  },
  agent_brief: {
    status: "pending",
  },
};
