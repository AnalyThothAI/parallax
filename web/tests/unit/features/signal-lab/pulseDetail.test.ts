import {
  buildPulseDetailView,
  GATE_AGENT_MISMATCH_CONFIDENCE,
} from "@features/signal-lab/model/pulseDetail";
import {
  tittyLegacyStages,
  tittyPulseFixture,
  tittySourceEventsFixture,
  TITTY_NOW_MS,
} from "@features/signal-lab/test/fixtures";
import { describe, expect, it } from "vitest";

describe("buildPulseDetailView", () => {
  const view = buildPulseDetailView({
    item: tittyPulseFixture,
    sourceEvents: tittySourceEventsFixture,
    now: TITTY_NOW_MS,
  });

  it("constructs hero identity and pills", () => {
    expect(view.hero.subject.symbol).toBe("$TITTY");
    expect(view.hero.subject.chain).toBe("solana");
    expect(view.hero.subject.shortAddress).toMatch(/^gTi4ZMMM/);
    expect(view.hero.pills).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "score_band", tone: "opportunity" }),
        expect.objectContaining({ id: "route", tone: "info" }),
        expect.objectContaining({ id: "gate_agent_mismatch", tone: "risk" }),
        expect.objectContaining({ id: "market_data_stale", tone: "risk" }),
      ]),
    );
  });

  it("computes freshness, histogram, and timeline", () => {
    expect(view.hero.burstHistogram.bins).toHaveLength(24);
    expect(view.hero.burstHistogram.bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(5);
    expect(view.hero.freshness.find((row) => row.label === "decision_latest")?.value).toMatch(
      /2h ago/,
    );
    expect(view.timeline.nodes.map((node) => node.kind)).toEqual([
      "market_anchor",
      "first",
      "peak",
      "now",
    ]);
    expect(view.timeline.nodes[0].timestampLabel).toMatch(/UTC$/);
  });

  it("orders factor families and flags missing market context", () => {
    expect(view.families.map((family) => family.id)).toEqual([
      "social_heat",
      "social_propagation",
      "semantic_catalyst",
      "timing_risk",
    ]);
    expect(view.families[0].score).toBe(91);
    expect(view.families[0].rankLabel).toMatch(/top 9%/);
    expect(view.families[3].dataHealth).toBe("missing");
    expect(view.market.metrics.map((metric) => metric.id)).toEqual([
      "price",
      "mcap",
      "liq",
      "vol_24h",
      "holders",
    ]);
    expect(view.market.metrics.find((metric) => metric.id === "liq")?.tone).toBe("warn");
    expect(view.market.metrics.find((metric) => metric.id === "vol_24h")?.tone).toBe("risk");
    expect(view.market.staleNotice).toMatch(/decision_latest 陈旧/);
  });

  it("adapts source evidence into token-case timeline cards with quote context", () => {
    expect(view.evidence.timelineItems).toHaveLength(5);
    expect(view.evidence.timelineItems[0]).toMatchObject({
      handle: "moontoklisting",
      market: {
        eventPriceLabel: "$0.00011621",
        providerLabel: "latest · okx_dex_ws_price_info",
      },
      phase: "burst",
    });
    expect(view.evidence.timelineItems[0].pills.map((pill) => pill.label)).toEqual(
      expect.arrayContaining(["$TITTY", "tweet", "KOL"]),
    );

    const withPostBurst = buildPulseDetailView({
      item: tittyPulseFixture,
      sourceEvents: [
        ...tittySourceEventsFixture,
        {
          ...tittySourceEventsFixture[0],
          event_id: "post-burst-event",
          timestamp_ms: TITTY_NOW_MS - 15 * 60_000,
          author_handle: "latecaller",
          text_clean: "follow-on mention after the burst",
        },
      ],
      now: TITTY_NOW_MS,
    });
    expect(withPostBurst.evidence.timelineItems.map((item) => item.phase)).toContain("post-burst");
  });

  it("enriches factor family breakdowns with all spec'd rows", () => {
    const heat = view.families[0];
    expect(heat.breakdown.map((row) => row.label)).toEqual([
      "mentions 1h / 4h / 24h",
      "unique authors",
      "attention surprise",
      "watched seed mentions",
    ]);

    const propagation = view.families[1];
    expect(propagation.breakdown.map((row) => row.label)).toEqual([
      "independent authors",
      "time to 2nd / 3rd author",
      "top author share",
      "duplicate text share",
      "watched / kol authors",
    ]);
    const topAuthor = propagation.breakdown.find((row) => row.label === "top author share");
    expect(topAuthor?.value).toMatch(/← @cache100x/);
    expect(topAuthor?.tone).toBe("warn");

    const semantic = view.families[2];
    expect(semantic.breakdown.map((row) => row.label)).toEqual([
      "llm covered mentions",
      "direction mix",
      "impact / novelty",
    ]);

    const timing = view.families[3];
    expect(timing.breakdown.map((row) => row.label)).toEqual([
      "price change before social",
      "price change since social",
      "dex floor",
    ]);
    expect(timing.breakdown.find((row) => row.label === "dex floor")?.value).toBe("ready");
  });

  it("groups evidence and classifies authors", () => {
    expect(view.evidence.groups.map((group) => group.id)).toContain("burst_window");
    expect(view.evidence.totalUniqueAuthors).toBe(3);
    const rows = view.evidence.groups.flatMap((group) => group.rows);
    const cacheRows = rows.filter((row) => row.handle === "cache100x");
    expect(cacheRows).toHaveLength(3);
    expect(cacheRows[0].authorTag).toBe("spam_suspect");
    expect(cacheRows[0].cohortPosition).toMatch(/\d\/3/);
    expect(rows.find((row) => row.handle === "moontoklisting")?.authorTag).toBe("kol_signal");
    expect(view.evidence.concentration.topAuthorShare).toBeCloseTo(0.6);
  });

  it("builds v2 stage rail with investigator + decision_maker entries", () => {
    expect(view.agent.kind).toBe("stages");
    expect(view.agent.isLegacy).toBe(false);
    expect(view.agent.railItems.map((entry) => entry.kind)).toEqual([
      "investigator",
      "decision_maker",
    ]);
    const decision = view.agent.railItems.find((entry) => entry.kind === "decision_maker");
    expect(decision?.status).toBe("ok");
    expect(decision?.summary).toMatch(/TITTY/);
    expect(view.agent.mismatch?.agentLabel).toMatch(/0\.35/);
    expect(view.agent.replay.pulseVersion).toBe("pulse-decision-harness-v1");
  });

  it("falls back to legacy stage rail when only analyst/critic/judge are present", () => {
    const legacy = buildPulseDetailView({
      item: { ...tittyPulseFixture, stages: tittyLegacyStages },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    expect(legacy.agent.isLegacy).toBe(true);
    const kinds = legacy.agent.railItems.map((entry) => entry.kind);
    expect(kinds).toEqual(["legacy", "legacy", "legacy"]);
    const legacyEntries = legacy.agent.railItems.filter(
      (entry): entry is Extract<typeof entry, { kind: "legacy" }> => entry.kind === "legacy",
    );
    expect(legacyEntries.map((entry) => entry.stageName)).toEqual([
      "analyst",
      "critic",
      "judge",
    ]);
    expect(legacyEntries[0].summary).toMatch(/Analyst legacy summary/);
  });

  it("handles abstain, research-only, and failed stage edge cases", () => {
    const abstain = buildPulseDetailView({
      item: {
        ...tittyPulseFixture,
        evidence_event_ids: [],
        decision: {
          ...tittyPulseFixture.decision,
          recommendation: "abstain",
          confidence: 0,
          evidence_event_ids: [],
        },
      },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    expect(abstain.evidence.citedCount).toBe(0);
    expect(abstain.evidence.abstainCallout).toMatch(/agent abstained/);

    const researchOnly = buildPulseDetailView({
      item: {
        ...tittyPulseFixture,
        decision: {
          ...tittyPulseFixture.decision,
          route: "research_only",
          recommendation: "abstain",
          confidence: 0,
        },
        stages: {
          investigator: null,
          decision_maker: null,
          research_only_gate: {
            stage: "research_only_gate",
            route: "research_only",
            status: "ok",
            model: null,
            started_at_ms: TITTY_NOW_MS,
            finished_at_ms: TITTY_NOW_MS,
            latency_ms: 0,
            attempt_index: 0,
            response: { abstain_reason: "no_target_resolved" },
            error: null,
          },
        },
      },
      sourceEvents: [],
      now: TITTY_NOW_MS,
    });
    expect(researchOnly.agent.kind).toBe("research_only");
    expect(researchOnly.agent.railItems).toEqual([]);
    expect(researchOnly.agent.researchOnlyGate?.abstainReason).toBe("no_target_resolved");

    const failed = buildPulseDetailView({
      item: {
        ...tittyPulseFixture,
        stages: {
          ...tittyPulseFixture.stages!,
          investigator: {
            ...tittyPulseFixture.stages!.investigator!,
            status: "failed",
            response: null,
            error: "investigator timed out",
          },
        },
      },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    const failedInvestigator = failed.agent.railItems.find(
      (entry) => entry.kind === "investigator",
    );
    expect(failedInvestigator?.status).toBe("failed");
    expect(failedInvestigator?.summary).toMatch(/timed out/);
  });
});

describe("GATE_AGENT_MISMATCH_CONFIDENCE", () => {
  it("is 0.5", () => {
    expect(GATE_AGENT_MISMATCH_CONFIDENCE).toBe(0.5);
  });
});
