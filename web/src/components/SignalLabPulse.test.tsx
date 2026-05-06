import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TradingAttentionItem } from "../api/types";
import { SignalLabPulse } from "./SignalLabPulse";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
  it("shows every pulse item instead of truncating to a date-window-sized preview", () => {
    const items = Array.from({ length: 7 }, (_, index) => chain(index));

    render(
      <SignalLabPulse
        data={{
          query: { window: "24h", scope: "all" },
          items,
          summary: {
            direct_token: 7,
            topic_heat: 0,
            ecosystem_signal: 0,
            market_structure: 0,
            risk_alert: 0,
            low_signal: 0,
            hot: 7,
            watch: 0,
            context: 0,
            muted: 0
          },
          returned_count: 7,
          has_more: false,
          next_cursor: null
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /TOKEN6/ })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(7);
  });
});

function chain(index: number): TradingAttentionItem {
  return {
    item_id: `attention-${index}`,
    kind: "direct_token",
    kind_label: "Direct token",
    priority: "hot",
    heat_score: 80,
    received_at_ms: 1_700_000_000_000 + index,
    updated_at_ms: 1_700_000_000_000 + index,
    source: { handle: "toly", followers: 1000 },
    event: {
      event_id: `event-${index}`,
      tweet_id: `${index}`,
      canonical_url: null,
      author_handle: "toly",
      text: `summary ${index}`,
      received_at_ms: 1_700_000_000_000 + index
    },
    event_type: "mention",
    title: `TOKEN${index}`,
    summary: `summary ${index}`,
    why_it_matters: `why ${index}`,
    direction_hint: "attention_positive",
    attention_mechanism: "direct_mention",
    linked_tokens: [
      {
        token_id: `token-${index}`,
        identity_key: `token-${index}`,
        symbol: `TOKEN${index}`,
        chain: "sol",
        address: null,
        relation: "direct",
        confidence: 0.9,
        status: "resolved",
        source: "attribution"
      }
    ],
    linked_topics: [{ key: `token-${index}`, label: `TOKEN${index}`, role: "asset" }],
    metrics: {
      impact: 80,
      novelty: 50,
      confidence: 0.9,
      direct_token_count: 1,
      topic_count: 1,
      account_alert_count: 0,
      window_mentions: 1,
      watched_author_count: 1
    },
    risks: [],
    next_action: "Inspect token tape and price response."
  };
}
