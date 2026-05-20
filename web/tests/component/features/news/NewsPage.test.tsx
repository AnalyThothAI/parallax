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

  it("renders a persisted agent brief news table and loads the next cursor at scroll bottom", async () => {
    fetchNewsRowsMock.mockImplementation(async (params = {}) => ({
      items: params.cursor === "cursor-2" ? [secondPageRow] : [firstPageRow],
      next_cursor: params.cursor === "cursor-2" ? null : "cursor-2",
    }));

    renderNews(<NewsPage token="test-token" />);

    expect(await screen.findByText("Coinbase lists NEWX")).toBeInTheDocument();
    expect(screen.getByText("Time")).toBeInTheDocument();
    expect(screen.getByText("Brief")).toBeInTheDocument();
    expect(screen.getByText("Direction")).toBeInTheDocument();
    expect(screen.getByText("Decision")).toBeInTheDocument();
    expect(screen.getByText("Evidence/Gaps")).toBeInTheDocument();
    expect(screen.getByText("Coinbase 上线 NEWX，短线关注流动性确认。")).toBeInTheDocument();
    expect(screen.getByText("bullish")).toBeInTheDocument();
    expect(screen.getByText("driver")).toBeInTheDocument();
    expect(screen.queryByText(/page\s+1/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Next news page")).not.toBeInTheDocument();
    expect(fetchNewsRowsMock).toHaveBeenCalledWith({
      cursor: null,
      limit: 25,
      status: null,
      token: "test-token",
    });

    const scrollContainer = screen.getByLabelText("News intel scroll container");
    Object.defineProperty(scrollContainer, "clientHeight", {
      configurable: true,
      value: 500,
    });
    Object.defineProperty(scrollContainer, "scrollHeight", {
      configurable: true,
      value: 1_000,
    });
    Object.defineProperty(scrollContainer, "scrollTop", {
      configurable: true,
      value: 470,
      writable: true,
    });
    fireEvent.scroll(scrollContainer);

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

  it("does not change rendered analysis when only the headline changes", async () => {
    fetchNewsRowsMock.mockResolvedValue({
      items: [{ ...firstPageRow, headline: "Completely different headline about BTC" }],
      next_cursor: null,
    });

    renderNews(<NewsPage token="test-token" />);

    expect(await screen.findByText("Completely different headline about BTC")).toBeInTheDocument();
    expect(screen.getByText("Coinbase 上线 NEWX，短线关注流动性确认。")).toBeInTheDocument();
    expect(
      screen.getByText("上市带来交易所可得性，但仍需确认真实成交与身份映射。"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/broad beta pressure/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/specific flow catalyst/i)).not.toBeInTheDocument();
  });

  it("routes a table row to the news item page", async () => {
    fetchNewsRowsMock.mockResolvedValue({ items: [firstPageRow], next_cursor: null });

    renderNews(<NewsPage token="test-token" />);

    fireEvent.click(
      await screen.findByRole("button", { name: /open news item coinbase lists newx/i }),
    );

    expect(screen.getByTestId("location")).toHaveTextContent("/news/news-1");
  });

  it("refetches the first news page when pulled down from the top", async () => {
    fetchNewsRowsMock
      .mockResolvedValueOnce({ items: [firstPageRow], next_cursor: null })
      .mockResolvedValueOnce({
        items: [{ ...firstPageRow, row_id: "row-refreshed", headline: "Fresh pull story" }],
        next_cursor: null,
      });

    renderNews(<NewsPage token="test-token" />);

    expect(await screen.findByText("Coinbase lists NEWX")).toBeInTheDocument();
    const scrollContainer = screen.getByLabelText("News intel scroll container");
    Object.defineProperty(scrollContainer, "scrollTop", {
      configurable: true,
      value: 0,
      writable: true,
    });

    fireEvent.touchStart(scrollContainer, { touches: [{ clientY: 16 }] });
    fireEvent.touchMove(scrollContainer, { touches: [{ clientY: 112 }] });
    fireEvent.touchEnd(scrollContainer);

    await waitFor(() => expect(fetchNewsRowsMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Fresh pull story")).toBeInTheDocument();
    expect(fetchNewsRowsMock).toHaveBeenLastCalledWith({
      cursor: null,
      limit: 25,
      status: null,
      token: "test-token",
    });
  });

  it("renders item detail with the persisted agent panel and original source", async () => {
    fetchNewsItemMock.mockResolvedValue(newsDetail);

    renderNews(<NewsPage newsItemId="news-1" token="test-token" />);

    expect(
      await screen.findByText("World Liberty treasury company warns on solvency"),
    ).toBeInTheDocument();
    expect(screen.getByText("Agent brief")).toBeInTheDocument();
    expect(
      screen.getAllByText("WLFI 财库公司披露持续经营风险，市场应先视作叙事风险。").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("该消息利空 WLFI 相关信心，但缺少可交易标的与价格反应确认。").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("多头视角")).toBeInTheDocument();
    expect(screen.getByText("空头视角")).toBeInTheDocument();
    expect(screen.getByText("反弹需要官方澄清和链上资金流入。")).toBeInTheDocument();
    expect(screen.getByText("持续经营风险可能压低 WLFI 叙事溢价。")).toBeInTheDocument();
    expect(screen.getByText("high · 缺少 WLFI 生产身份映射")).toBeInTheDocument();
    expect(screen.getByText("run-news-1")).toBeInTheDocument();
    expect(screen.getByText("prompt-news-v1")).toBeInTheDocument();
    expect(screen.getByText("Market map")).toBeInTheDocument();
    expect(screen.getAllByText("WLFI").length).toBeGreaterThan(0);
    expect(screen.queryByText("AI Financial")).not.toBeInTheDocument();
    expect(screen.getByText("Token identity")).toBeInTheDocument();
    expect(
      screen.queryByText(/Solvency warning around a WLFI-linked treasury vehicle/i),
    ).not.toBeInTheDocument();
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
  agent_brief: {
    status: "ready",
    direction: "bullish",
    decision_class: "driver",
    summary_zh: "Coinbase 上线 NEWX，短线关注流动性确认。",
    market_read_zh: "上市带来交易所可得性，但仍需确认真实成交与身份映射。",
    bull_strength: "moderate",
    bear_strength: "weak",
    data_gap_count: 1,
    evidence_refs: ["item:title", "fact:listing-1"],
    bull_view: {
      strength: "moderate",
      thesis_zh: "新增上市通常提升可得性和关注度。",
      evidence_refs: ["item:title"],
    },
    bear_view: {
      strength: "weak",
      thesis_zh: "若成交不足，上市本身难以延续叙事。",
      evidence_refs: ["fact:listing-1"],
    },
  },
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
  agent_brief: {
    status: "pending",
  },
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
  agent_brief: {
    status: "ready",
    direction: "bearish",
    decision_class: "watch",
    summary_zh: "WLFI 财库公司披露持续经营风险，市场应先视作叙事风险。",
    market_read_zh: "该消息利空 WLFI 相关信心，但缺少可交易标的与价格反应确认。",
    bull_strength: "weak",
    bear_strength: "strong",
    data_gap_count: 2,
    computed_at_ms: 1_765_000_000_999,
    agent_run_id: "run-news-1",
    schema_version: "news_item_agent_brief_v1",
    prompt_version: "prompt-news-v1",
    artifact_version_hash: "artifact-123",
    input_hash: "input-abc",
    output_hash: "output-def",
    evidence_refs: ["item:title", "fact:filing-1"],
    data_gaps: [
      { description_zh: "缺少 WLFI 生产身份映射", severity: "high" },
      { description_zh: "缺少价格反应", severity: "medium" },
    ] as unknown as string[],
    watch_triggers: ["官方澄清持续经营风险", "WLFI 相关市场出现放量"],
    invalidation_conditions: ["公司撤回持续经营风险提示"],
    bull_view: {
      strength: "weak",
      thesis_zh: "反弹需要官方澄清和链上资金流入。",
      evidence_refs: ["item:title"],
    },
    bear_view: {
      strength: "strong",
      thesis_zh: "持续经营风险可能压低 WLFI 叙事溢价。",
      evidence_refs: ["fact:filing-1"],
    },
  },
  agent_run: {
    run_id: "run-news-1",
    status: "succeeded",
    outcome: "ready",
    model: "gpt-test",
    prompt_version: "prompt-news-v1",
    schema_version: "news_item_agent_brief_v1",
    execution_started: true,
  },
};
