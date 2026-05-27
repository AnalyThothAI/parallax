import { NewsTape } from "@features/news/ui/NewsTape";
import type { NewsRow } from "@shared/model/newsIntel";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("NewsTape", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders compact rows without a duplicate score column", () => {
    render(<NewsTape rows={[rowWithBtcEth]} onOpen={vi.fn()} />);

    expect(screen.getByText("利好")).toBeInTheDocument();
    expect(screen.getByText("A · 82")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("82 A")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
    expect(screen.getByText("70 B+")).toBeInTheDocument();
    expect(screen.queryByText("score")).not.toBeInTheDocument();
  });

  it("opens one news item as one row even with multiple token chips", () => {
    const onOpen = vi.fn();
    render(<NewsTape rows={[rowWithBtcEth]} onOpen={onOpen} />);

    const rows = [screen.getByRole("button", { name: "Open news item BTC ETF flows expand" })];
    expect(screen.getAllByText("BTC ETF flows expand")).toHaveLength(1);

    fireEvent.click(rows[0]);
    expect(onOpen).toHaveBeenCalledWith("news-1");

    fireEvent.click(screen.getByRole("button", { name: /open btc etf flows expand/i }));
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});

const rowWithBtcEth: NewsRow = {
  row_id: "row-1",
  news_item_id: "news-1",
  lifecycle_status: "processed",
  headline: "BTC ETF flows expand",
  summary: "ETF desk activity stays elevated.",
  latest_at_ms: 1_779_000_000_000,
  source_domain: "6551.io",
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
      market_type: "cex",
    },
    {
      lane: "resolved",
      resolution_status: "resolved",
      symbol: "ETH",
      target_id: "token:eth",
      market_type: "cex",
    },
  ],
  token_impacts: [
    {
      lane: "provider",
      symbol: "BTC",
      provider_signal: "long",
      provider_score: 82,
      provider_grade: "A",
      market_type: "cex",
    },
    {
      lane: "provider",
      symbol: "ETH",
      provider_signal: "long",
      provider_score: 70,
      provider_grade: "B+",
      market_type: "cex",
    },
  ],
  fact_lanes: [],
};
