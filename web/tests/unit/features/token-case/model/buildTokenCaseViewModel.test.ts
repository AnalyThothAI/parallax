import { buildTokenCaseViewModel } from "@features/token-case/model/buildTokenCaseViewModel";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

describe("buildTokenCaseViewModel", () => {
  it("maps a token-case dossier into the narrative view model", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier,
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
      isLoadingPosts: false,
      isFetchingNextPage: false,
    });

    expect(vm.hero.title).toContain("$HANSA");
    expect(vm.metrics.map((metric) => metric.key)).toEqual([
      "mentions",
      "phase",
      "watched",
      "readiness",
    ]);
    expect(vm.propagation.stages).toHaveLength(3);
    expect(vm.timeline.items[0].quality.scoreLabel).toMatch(/PQ/);
    expect(vm.market.status).toBe("missing");
    expect(vm.bullBear.bull.title).toBe("Bull · 多头");
    expect(vm.bullBear.bear.title).toBe("Bear · 空头");
    expect(vm.dataGaps.length).toBeGreaterThan(0);
  });

  it("surfaces event-level token prices in timeline pills", () => {
    const dossier = tokenCaseFixture();
    const firstPost = dossier.posts.items[0];

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        posts: {
          ...dossier.posts,
          items: [
            {
              ...firstPost,
              price: {
                status: "ready",
                provider: "gmgn_dex_quote",
                price_usd: 0.00042,
                observed_at_ms: 1_700_000_000_000,
                observation_lag_ms: 500,
                observation_id: "tick:hansa",
                observation_kind: "tier3_inline",
              },
            },
            ...dossier.posts.items.slice(1),
          ],
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
    });

    expect(vm.timeline.items[0].pills.map((pill) => pill.label)).toContain("$0.00042");
  });

  it("promotes event prices with a live-market comparison for the timeline", () => {
    const dossier = tokenCaseFixture();
    const firstPost = dossier.posts.items[0];

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        market_live: {
          ...dossier.market_live,
          status: "ready",
          price_usd: 0.0005,
          provider: "gmgn_dex_quote",
        },
        posts: {
          ...dossier.posts,
          items: [
            {
              ...firstPost,
              price: {
                status: "ready",
                provider: "gmgn_dex_quote",
                price_usd: 0.0004,
                observed_at_ms: 1_700_000_000_000,
                observation_lag_ms: 500,
                observation_id: "tick:hansa",
                observation_kind: "tier3_inline",
              },
            },
          ],
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
    });

    expect(vm.timeline.items[0].market).toEqual({
      eventPriceLabel: "$0.0004",
      liveDeltaLabel: "+25.00% vs live",
      providerLabel: "gmgn_dex_quote",
      tone: "health",
    });
  });

  it("filters watched timeline items on the client", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier,
      route: { window: "1h", scope: "all", postSort: "watched" },
      posts: dossier.posts,
      isLoadingPosts: false,
      isFetchingNextPage: false,
    });

    expect(vm.timeline.items.every((item) => item.isWatched)).toBe(true);
  });

  it("keeps stale market snapshots in a degraded market state", () => {
    const dossier = tokenCaseFixture();
    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        market_live: {
          ...dossier.market_live,
          status: "stale",
          price_usd: 0.00042,
          error: null,
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.market.status).toBe("stale");
    expect(vm.market.tone).toBe("warn");
    expect(vm.market.emptyTitle).toBe("Live market stale");
  });
});
