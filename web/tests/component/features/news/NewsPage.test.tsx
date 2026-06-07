import { readFileSync } from "node:fs";
import { join } from "node:path";

import { NewsPage } from "@features/news";
import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import type { NewsItemDetail, NewsRow, NewsSignalEnvelope, NewsSignalSummary } from "@shared/model/newsIntel";
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
  limit: number;
  min_score: number | null;
  q: string | null;
  signal: string | null;
  status: string | null;
  token: string;
};

const defaultNewsFetchParams: ObservedNewsParams = {
  cursor: null,
  limit: 100,
  min_score: 80,
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

  it("renders a compact provider-signal tape without an inline inspector", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    await waitFor(() => expect(fetchNewsRowsMock).toHaveBeenCalled());
    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    expect(screen.queryByText("有 Token")).not.toBeInTheDocument();
    expect(screen.queryByText("无 Token")).not.toBeInTheDocument();
    expect(screen.getAllByText("利好").length).toBeGreaterThan(0);
    expect(screen.getAllByText("A · 82").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BTC").length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("news inspector")).not.toBeInTheDocument();
    expect(screen.queryByText("Provider signal")).not.toBeInTheDocument();
    expect(screen.queryByText("Content")).not.toBeInTheDocument();
    expect(screen.queryByText("Decision")).not.toBeInTheDocument();
    expect(fetchNewsRowsMock).toHaveBeenCalledWith(defaultNewsFetchParams);
  });

  it("anchors sparse and loading queue content at the top of the scroll surface", () => {
    const newsCss = readFileSync(join(process.cwd(), "src/features/news/news.css"), "utf8");
    const tableWrapRule = cssRuleBody(newsCss, ".news-table-wrap");

    expect(tableWrapRule).toContain("align-content: start");
    expect(tableWrapRule).toContain("grid-auto-rows: max-content");
  });

  it("requests backend hard-cut filters from signal, score, and search controls", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "利空" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        signal: "bearish",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "≥80" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        min_score: null,
        signal: "bearish",
      }),
    );

    fireEvent.change(screen.getByLabelText("Search news"), { target: { value: "eth" } });
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        min_score: null,
        q: "eth",
        signal: "bearish",
      }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/news?q=eth");
  });

  it("hydrates the news search input from the route query", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />, "/news?q=ethereum");

    expect(await screen.findByLabelText("Search news")).toHaveValue("ethereum");
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        q: "ethereum",
      }),
    );
  });

  it("preserves intermediate spaces while typing multi-word news queries", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    const searchInput = await screen.findByLabelText("Search news");
    fireEvent.change(searchInput, { target: { value: "ethereum" } });
    await waitFor(() => expect(searchInput).toHaveValue("ethereum"));

    fireEvent.change(searchInput, { target: { value: "ethereum " } });
    await waitFor(() => expect(searchInput).toHaveValue("ethereum "));

    fireEvent.change(searchInput, { target: { value: "ethereum e" } });
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        q: "ethereum e",
      }),
    );
    expect(searchInput).toHaveValue("ethereum e");
    expect(screen.getByTestId("location")).toHaveTextContent("/news?q=ethereum+e");
  });

  it("disables next pagination when the backend returns no next cursor", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Next news page" })).toBeDisabled();
  });

  it("resets pagination to the first page when the news query changes", async () => {
    fetchNewsRowsMock.mockImplementation(async (params) => {
      const cursor = params?.cursor ?? null;
      return {
        items: [providerRow],
        next_cursor: cursor ? null : "1779000000000:row-1",
      };
    });

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    await waitFor(() => expect(fetchNewsRowsMock).toHaveBeenLastCalledWith(defaultNewsFetchParams));

    fireEvent.click(screen.getByRole("button", { name: "Next news page" }));
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        cursor: "1779000000000:row-1",
      }),
    );
    await waitFor(() => expect(screen.getByText("Page 2 · 1/100")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Search news"), { target: { value: "zec" } });
    await waitFor(() =>
      expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
        ...defaultNewsFetchParams,
        q: "zec",
      }),
    );
    expect(fetchNewsRowsMock).not.toHaveBeenCalledWith({
      ...defaultNewsFetchParams,
      cursor: "1779000000000:row-1",
      q: "zec",
    });
    await waitFor(() => expect(screen.getByText("Page 1 · 1/100")).toBeInTheDocument());
    expect(screen.getByTestId("location")).toHaveTextContent("/news?q=zec");
  });

  it("routes the compact tape open action to the news item page", async () => {
    mockNewsRows();

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /^open btc etf flows expand/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/news/items/news-1");
  });

  it("renders an evidence page for OpenNews provider facts instead of Agent memo", async () => {
    fetchNewsItemMock.mockResolvedValue(providerDetail);

    renderNews(<NewsPage newsItemId="news-1" token="test-token" />);

    await waitFor(() =>
      expect(fetchNewsItemMock).toHaveBeenCalledWith({
        newsItemId: "news-1",
        token: "test-token",
      }),
    );
    await screen.findByText("Evidence page");
    expect(screen.getByText("Original article")).toBeInTheDocument();
    expect(screen.getByText("OpenNews source content.")).toBeInTheDocument();
    expect(screen.getByText("Agent gate")).toBeInTheDocument();
    expect(screen.getAllByText("eligible").length).toBeGreaterThan(0);
    expect(screen.queryByText("Research tools")).not.toBeInTheDocument();
    expect(screen.queryByText("Legacy agent audit")).not.toBeInTheDocument();
    expect(screen.getAllByText("Provider aiRating").length).toBeGreaterThan(0);
    expect(screen.getByText("Token impacts")).toBeInTheDocument();
    expect(screen.getByText("Execution gaps")).toBeInTheDocument();
    expect(screen.getByText("Price reaction")).toBeInTheDocument();
    expect(screen.getByText("Liquidity / OI")).toBeInTheDocument();
    expect(screen.getByText("Agent thesis")).toBeInTheDocument();
    expect(screen.getAllByText("利好").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BTC").length).toBeGreaterThan(0);
    expect(screen.queryByText("Agent memo")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /original/i })).toHaveAttribute(
      "href",
      "https://example.test/news-1",
    );
  });
});

function renderNews(children: ReactNode, route = "/news") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <QueryClientProvider client={queryClient}>
        {children}
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

function cssRuleBody(css: string, selector: string): string {
  const match = new RegExp(`${selector.replace(".", "\\.")}\\s*\\{(?<body>[^}]*)\\}`).exec(css);
  return match?.groups?.body ?? "";
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
  signal: newsSignalEnvelope({
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
  }),
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

function newsSignalEnvelope(displaySignal: NewsSignalSummary): NewsSignalEnvelope {
  return {
    display_signal: displaySignal,
    provider_signal: displaySignal.source === "provider" ? displaySignal : null,
    agent_signal: { status: "pending" },
    alert_eligibility: {
      in_app_eligible: true,
      external_push_ready: false,
      agent_status: "pending",
      provider_status: displaySignal.status,
      provider_score: displaySignal.score,
    },
    agent_requirement: {
      status: "required",
      reason: "eligible",
      priority: 18,
      basis: { provider_score: displaySignal.score },
      version: "news_item_agent_requirement_v1",
    },
  };
}

const providerDetail: NewsItemDetail = {
  ...providerRow,
  content: "OpenNews source content.",
  body_text: "OpenNews source content.",
  source: {
    provider_type: "opennews",
    source_domain: "6551.io",
    source_name: "OpenNews",
    source_quality_status: "healthy",
  },
  agent_brief: {
    status: "ready",
    summary_zh: "ETF 资金流持续增强。",
    market_read_zh: "AI reads this as a liquidity signal worth watching.",
    confirmation_state: "single_source",
    novelty_status: "new",
    requirement_status: "required",
    requirement_reason: "eligible",
    eligibility_reason: "eligible",
  },
  agent_requirement_status: "required",
  agent_requirement_reason: "eligible",
  agent_requirement_priority: 18,
  analysis_admission_status: "admitted",
  analysis_admission_reason: "crypto_native_evidence",
  agent_run: {
    run_id: "run-news-1",
    status: "completed",
    outcome: "ready",
    model: "deepseek-v4-flash",
    provider: "litellm",
    latency_ms: 1200,
    usage_json: { input_tokens: 100, output_tokens: 20 },
    response_json: { summary_zh: "ETF 资金流持续增强。" },
  },
};
