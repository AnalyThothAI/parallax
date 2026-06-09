import { NewsTape } from "@features/news/ui/NewsTape";
import type { NewsRow, NewsSignalEnvelope, NewsSignalSummary } from "@shared/model/newsIntel";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("NewsTape", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders compact rows without provider score labels", () => {
    render(<NewsTape rows={[rowWithBtcEth]} onOpen={vi.fn()} />);

    expect(screen.getByText("利好")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
    expect(screen.getAllByText("CEX").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("A · 82")).not.toBeInTheDocument();
    expect(screen.queryByText("82 A")).not.toBeInTheDocument();
    expect(screen.queryByText("70 B+")).not.toBeInTheDocument();
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

  it("surfaces agent review state separately from provider score", () => {
    render(<NewsTape rows={[rowWithInsufficientAgentBrief]} onOpen={vi.fn()} />);

    expect(screen.getByText("AGENT INSUFF")).toBeInTheDocument();
    expect(
      screen.getByText("Provider high score without enough agent evidence"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Insufficient agent title")).not.toBeInTheDocument();
  });

  it("does not show ready watch agents as held when push readiness is blocked", () => {
    render(<NewsTape rows={[rowWithReadyWatchAgentPushBlocked]} onOpen={vi.fn()} />);

    expect(screen.getByText("AGENT READY")).toBeInTheDocument();
    expect(screen.queryByText("AGENT HOLD")).not.toBeInTheDocument();
    expect(screen.getByText("Agent watch title")).toBeInTheDocument();
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
  signal: newsSignalEnvelope({
    source: "provider",
    provider: "opennews",
    status: "ready",
    direction: "bullish",
    label_zh: "利好",
    signal: "long",
    summary_zh: "ETF 资金流持续增强。",
    method: "opennews.aiRating",
  }),
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
      market_type: "cex",
    },
    {
      lane: "provider",
      symbol: "ETH",
      market_type: "cex",
    },
  ],
  fact_lanes: [],
};

const rowWithInsufficientAgentBrief: NewsRow = {
  ...rowWithBtcEth,
  row_id: "row-2",
  news_item_id: "news-2",
  headline: "Provider high score without enough agent evidence",
  signal: newsSignalEnvelope(
    {
      source: "provider",
      provider: "opennews",
      status: "ready",
      direction: "bullish",
      label_zh: "利好",
      signal: "long",
      summary_zh: "Provider summary remains visible.",
      method: "opennews.aiRating",
    },
    {
      alert_eligibility: {
        in_app_eligible: true,
        external_push_ready: false,
        external_push_block_reason: "agent_brief_not_ready",
        agent_status: "insufficient",
        decision_class: "context",
      },
    },
  ),
  agent_brief: {
    status: "insufficient",
    direction: "neutral",
    decision_class: "context",
    title_zh: "Insufficient agent title",
    summary_zh: "证据不足。",
  },
};

const rowWithReadyWatchAgentPushBlocked: NewsRow = {
  ...rowWithBtcEth,
  row_id: "row-3",
  news_item_id: "news-3",
  headline: "Ready watch item",
  signal: newsSignalEnvelope(
    {
      source: "agent",
      provider: "news_item_brief",
      status: "ready",
      direction: "bullish",
      label_zh: "利好",
      signal: "long",
      title_zh: "Provider title",
      summary_zh: "Agent summary remains visible.",
      method: "news_item_brief",
    },
    {
      alert_eligibility: {
        in_app_eligible: true,
        external_push_ready: false,
        external_push_block_reason: "cooldown",
        agent_status: "ready",
        decision_class: "watch",
      },
    },
  ),
  agent_brief: {
    status: "ready",
    direction: "bullish",
    decision_class: "watch",
    title_zh: "Agent watch title",
    summary_zh: "Agent summary.",
  },
};

function newsSignalEnvelope(
  displaySignal: NewsSignalSummary,
  overrides: { alert_eligibility?: Record<string, unknown> } = {},
): NewsSignalEnvelope {
  return {
    display_signal: displaySignal,
    agent_signal: { status: overrides.alert_eligibility?.agent_status ?? "pending" },
    alert_eligibility: {
      in_app_eligible: true,
      external_push_ready: false,
      agent_status: "pending",
      ...overrides.alert_eligibility,
    },
  };
}
