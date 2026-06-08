import {
  newsAgentReviewBadge,
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenMarketLabel,
} from "@features/news/model/newsSignalViewModel";
import type { NewsRow } from "@shared/model/newsIntel";
import { describe, expect, it } from "vitest";

describe("newsSignalViewModel", () => {
  it("labels provider bullish, bearish, and neutral signals in Chinese", () => {
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bullish" })).toBe(
      "利好",
    );
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bearish" })).toBe(
      "利空",
    );
    expect(newsSignalLabel({ source: "provider", status: "partial", direction: "neutral" })).toBe(
      "中性",
    );
  });

  it("formats total scores only for the signal pill", () => {
    expect(newsSignalScoreLabel({ score: 82, grade: "A" })).toBe("A · 82");
    expect(newsSignalScoreLabel({ score: null, grade: null })).toBe("score --");
  });

  it("labels canonical token market context without provider scores", () => {
    expect(
      tokenMarketLabel({ market_type: "cex", resolution_status: "resolved", lane: "resolved" }),
    ).toBe("CEX");
  });

  it("maps signal tones to compact CSS modifiers", () => {
    expect(newsSignalTone({ direction: "bullish" })).toBe("is-long");
    expect(newsSignalTone({ direction: "bearish" })).toBe("is-short");
  });

  it("does not label policy-ineligible rows as waiting for agent", () => {
    expect(
      newsAgentReviewBadge({
        agent_status: "not_required",
        agent_brief: { status: "not_required" },
        agent_brief_status: null,
        signal: {
          display_signal: { source: "provider", status: "ready", direction: "neutral" },
          agent_signal: { status: "not_required" },
          alert_eligibility: { agent_status: "not_required", agent_admission_reason: "exact_duplicate" },
        },
      }),
    ).toEqual({
      label: "AGENT SKIP",
      detail: "exact_duplicate",
      tone: "is-blocked",
      title: "AGENT SKIP · exact_duplicate",
    });
  });

  it("keeps token display lanes canonical and ignores provider token impacts", () => {
    const lanes = newsDisplayTokenLanes({
      token_lanes: [{ lane: "resolved", symbol: "BTC", target_id: "token:btc" }],
      token_impacts: [
        { lane: "attention", symbol: "BTC", score: 91, signal: "long" },
        { lane: "attention", symbol: "SOL", score: 70, signal: "long" },
      ],
    });

    expect(lanes).toEqual([{ lane: "resolved", symbol: "BTC", target_id: "token:btc" }]);
  });

  it("marks ready watch and driver briefs ready independently of external push readiness", () => {
    expect(newsAgentReviewBadge(agentRow({ status: "ready", decisionClass: "watch" }))).toEqual({
      label: "AGENT READY",
      detail: null,
      tone: "is-ready",
      title: "AGENT READY",
    });
    expect(newsAgentReviewBadge(agentRow({ status: "ready", decisionClass: "driver" }))).toEqual({
      label: "AGENT READY",
      detail: null,
      tone: "is-ready",
      title: "AGENT READY",
    });
  });

  it("keeps ready context briefs separate from agent hold", () => {
    expect(newsAgentReviewBadge(agentRow({ status: "ready", decisionClass: "context" }))).toEqual({
      label: "AGENT CONTEXT",
      detail: "cooldown",
      tone: "is-waiting",
      title: "AGENT CONTEXT · cooldown",
    });
  });
});

function agentRow({
  status,
  decisionClass,
}: {
  status: string;
  decisionClass: string;
}): Pick<NewsRow, "agent_brief" | "agent_brief_status" | "agent_status" | "signal"> {
  return {
    agent_brief: {
      status,
      decision_class: decisionClass,
    },
    signal: {
      display_signal: { source: "agent", status: "ready", direction: "neutral" },
      agent_signal: { status, decision_class: decisionClass },
      alert_eligibility: {
        external_push_ready: false,
        external_push_block_reason: "cooldown",
        agent_status: status,
        decision_class: decisionClass,
      },
    },
  };
}
