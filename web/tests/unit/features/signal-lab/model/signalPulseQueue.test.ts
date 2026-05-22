import { buildSignalPulseQueueItem } from "@features/signal-lab/model/signalPulseQueue";
import { tittyPulseFixture } from "@tests/fixtures/signal-lab";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.useRealTimers();
});

describe("buildSignalPulseQueueItem", () => {
  it("translates a high-score low-confidence pulse into a user-facing case row", () => {
    vi.useFakeTimers();
    vi.setSystemTime(tittyPulseFixture.updated_at_ms + 2 * 60 * 60 * 1000 + 5_000);

    const view = buildSignalPulseQueueItem(tittyPulseFixture);

    expect(view.symbol).toBe("$TITTY");
    expect(view.meta).toContain("SOLANA");
    expect(view.meta).toContain("DEX");
    expect(view.title).toBe("热度很高，但流动性极浅且作者集中");
    expect(view.summary).toBe(tittyPulseFixture.decision.summary_zh);
    expect(view.score.value).toBe("82");
    expect(view.score.caption).toBe("热度分");
    expect(view.timeLabel).toBe("2h前");
    expect(view.timeIso).toBe(new Date(tittyPulseFixture.updated_at_ms).toISOString());
    expect(view.verdict.label).toBe("候选");
    expect(view.verdict.confidenceLabel).toBe("conf 0.35");
    expect(view.tone).toBe("risk");
    expect(view.chips).toEqual(
      expect.arrayContaining([
        { label: "独立作者 3", tone: "health" },
        { label: "头部60%", tone: "risk" },
        { label: "提及 5 / 1h", tone: "warn" },
      ]),
    );
  });

  it("labels unknown update time explicitly", () => {
    const view = buildSignalPulseQueueItem({ ...tittyPulseFixture, updated_at_ms: 0 });

    expect(view.timeLabel).toBe("时间未知");
    expect(view.timeIso).toBeUndefined();
  });

  it("keeps watchlist wording separate from trade-candidate wording", () => {
    const view = buildSignalPulseQueueItem({
      ...tittyPulseFixture,
      candidate_score: 87,
      score_band: "high_conviction",
      decision: {
        ...tittyPulseFixture.decision,
        recommendation: "watchlist",
        confidence: 0.6,
      },
      fact_card: {
        ...tittyPulseFixture.fact_card,
        liquidity_usd: 1448109.87646942,
        volume_24h_usd: 2688279.37165528,
      },
      factor_snapshot: {
        ...tittyPulseFixture.factor_snapshot,
        market: {
          ...tittyPulseFixture.factor_snapshot.market,
          readiness: {
            ...tittyPulseFixture.factor_snapshot.market.readiness,
            latest_status: "live",
          },
          decision_latest: {
            ...tittyPulseFixture.factor_snapshot.market.decision_latest!,
            liquidity_usd: 1448109.87646942,
            volume_24h_usd: 2688279.37165528,
          },
        },
        families: {
          ...tittyPulseFixture.factor_snapshot.families,
          social_propagation: {
            ...tittyPulseFixture.factor_snapshot.families.social_propagation,
            facts: {
              ...tittyPulseFixture.factor_snapshot.families.social_propagation.facts,
              top_author_share: 0.33,
            },
          },
        },
      },
    });

    expect(view.title).toBe("Agent 建议先观察，不是直接交易结论");
    expect(view.verdict.label).toBe("观察");
    expect(view.verdict.confidenceLabel).toBe("conf 0.60");
    expect(view.chips).toContainEqual({ label: "独立作者 3", tone: "health" });
    expect(view.chips).toContainEqual({ label: "头部33%", tone: "warn" });
    expect(view.chips).not.toContainEqual({ label: "市场过期", tone: "risk" });
  });

  it("models matched lane rows as alert context instead of discovery", () => {
    const view = buildSignalPulseQueueItem({
      ...tittyPulseFixture,
      scope: "matched",
      fact_card: {
        ...tittyPulseFixture.fact_card,
        watched_mentions: 1,
      },
    });

    expect(view.chips).toContainEqual({ label: "关注匹配", tone: "alert" });
    expect(view.chips).not.toContainEqual({ label: "发现", tone: "neutral" });
  });

  it("surfaces watched-only source quality without treating it as discovery breadth", () => {
    const view = buildSignalPulseQueueItem({
      ...tittyPulseFixture,
      fact_card: {
        ...tittyPulseFixture.fact_card,
        mentions_1h: 2,
        unique_authors: 1,
        watched_mentions: 2,
      },
      factor_snapshot: {
        ...tittyPulseFixture.factor_snapshot,
        families: {
          ...tittyPulseFixture.factor_snapshot.families,
          social_heat: {
            ...tittyPulseFixture.factor_snapshot.families.social_heat,
            facts: {
              ...tittyPulseFixture.factor_snapshot.families.social_heat.facts,
              mentions_1h: 2,
              watched_mentions: 2,
            },
          },
          social_propagation: {
            ...tittyPulseFixture.factor_snapshot.families.social_propagation,
            facts: {
              ...tittyPulseFixture.factor_snapshot.families.social_propagation.facts,
              independent_authors: 1,
              top_author_share: 1,
            },
          },
        },
      },
    });

    expect(view.chips).toContainEqual({ label: "仅关注源", tone: "alert" });
    expect(view.chips).toContainEqual({ label: "独立作者 1", tone: "warn" });
    expect(view.chips).toContainEqual({ label: "头部100%", tone: "risk" });
  });
});
