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

describe("NewsPage", () => {
  beforeEach(() => {
    fetchNewsRowsMock.mockReset();
    fetchNewsItemMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders a Token Radar-style paged news table and advances by cursor", async () => {
    fetchNewsRowsMock.mockImplementation(async (params = {}) => ({
      items: params.cursor === "cursor-2" ? [secondPageRow] : [firstPageRow],
      next_cursor: params.cursor === "cursor-2" ? null : "cursor-2",
    }));

    renderNews(<NewsPage token="test-token" />);

    expect(await screen.findByText("Coinbase lists NEWX")).toBeInTheDocument();
    expect(screen.getByText("Time / Source")).toBeInTheDocument();
    expect(screen.getByText("Event / Question")).toBeInTheDocument();
    expect(screen.getByText("Instrument / Price")).toBeInTheDocument();
    expect(screen.getByText("Route")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(fetchNewsRowsMock).toHaveBeenCalledWith({
      cursor: null,
      limit: 25,
      status: null,
      token: "test-token",
    });

    fireEvent.click(screen.getByLabelText("Next news page"));

    expect(await screen.findByText("Second page story")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        cursor: "cursor-2",
        limit: 25,
        status: null,
        token: "test-token",
      }),
    );
  });

  it("routes a table row to the news item page", async () => {
    fetchNewsRowsMock.mockResolvedValue({ items: [firstPageRow], next_cursor: null });

    renderNews(<NewsPage token="test-token" />);

    fireEvent.click(
      await screen.findByRole("button", { name: /open news item coinbase lists newx/i }),
    );

    expect(screen.getByTestId("location")).toHaveTextContent("/news/news-1");
  });

  it("renders item detail with instruments, token identity, and original source", async () => {
    fetchNewsItemMock.mockResolvedValue(newsDetail);

    renderNews(<NewsPage newsItemId="news-1" token="test-token" />);

    expect(
      await screen.findByText("World Liberty treasury company warns on solvency"),
    ).toBeInTheDocument();
    expect(screen.getByText("Market map")).toBeInTheDocument();
    expect(screen.getAllByText("WLFI").length).toBeGreaterThan(0);
    expect(screen.getByText("AI Financial")).toBeInTheDocument();
    expect(screen.getByText("Token identity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /original/i })).toHaveAttribute(
      "href",
      "https://example.test/news-1",
    );
    expect(fetchNewsItemMock).toHaveBeenCalledWith({
      newsItemId: "news-1",
      token: "test-token",
    });
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

const firstPageRow: NewsRow = {
  row_id: "row-1",
  news_item_id: "news-1",
  lifecycle_status: "attention",
  headline: "Coinbase lists NEWX",
  summary: "Trading starts today",
  source_domain: "example.test",
  latest_at_ms: 1_765_000_000_000,
  token_lanes: [{ lane: "attention", resolution_status: "unknown_attention", symbol: "NEWX" }],
  fact_lanes: [{ event_type: "listing", status: "attention" }],
};

const secondPageRow: NewsRow = {
  row_id: "row-2",
  news_item_id: "news-2",
  lifecycle_status: "attention",
  headline: "Second page story",
  summary: "Cursor pagination keeps the queue bounded",
  source_domain: "example.test",
  latest_at_ms: 1_765_000_000_001,
  token_lanes: [],
  fact_lanes: [{ event_type: "market", status: "attention" }],
};

const newsDetail: NewsItemDetail = {
  ...firstPageRow,
  headline: "World Liberty treasury company warns on solvency",
  canonical_url: "https://example.test/news-1",
  content: "SEC filing warns that the treasury company may not survive the year.",
  source: {
    source_domain: "example.test",
    source_name: "Example News",
    source_role: "primary",
    trust_tier: "trusted",
  },
  token_lanes: [{ lane: "attention", resolution_status: "unknown_attention", symbol: "WLFI" }],
  fact_lanes: [
    {
      claim: "Issuer warns it may not survive the year",
      event_type: "filing",
      realis: "actual",
      status: "attention",
    },
  ],
};
