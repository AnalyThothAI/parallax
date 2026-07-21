import { buildTokenCaseViewModel } from "@features/token-case/model/buildTokenCaseViewModel";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

const HANSA_TOKEN_IMAGE_URL = "/api/token-images/hansa-local";

describe("buildTokenCaseViewModel", () => {
  it("maps a token-case dossier without synthesizing narrative output", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier,
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
      isLoadingPosts: false,
      isFetchingNextPage: false,
    });

    expect(vm.hero.title).toContain("$HANSA");
    expect(vm.hero.subtitle).toContain("solana");
    expect(vm.metrics.map((metric) => metric.key)).toEqual([
      "mentions",
      "admission",
      "watched",
      "readiness",
    ]);
    expect(vm.metrics.find((metric) => metric.key === "admission")).toMatchObject({
      value: "admitted",
      detail: "18 posts · 7 authors",
      tone: "health",
    });
    expect(vm.hero.logoUrl).toBe(HANSA_TOKEN_IMAGE_URL);
    expect(vm.timeline.items[0]).toMatchObject({ phase: "expansion", role: "watched" });
    expect(vm.timeline.items[0].pills).toEqual([]);
    expect(vm.timeline.items[0].pills.map((pill) => pill.label)).not.toContain("PQ 82");
    expect(vm.market.status).toBe("missing");
    expect(vm.dataGaps).toEqual([]);
  });

  it("normalizes structured admission data gaps for the details rail", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        narrative_admission: {
          ...dossier.narrative_admission,
          status: "missing",
          reason: "no_current_admission",
          is_current: false,
          currentness: {
            display_status: "not_ready",
            reason: "no_current_admission",
          },
          coverage: { source_mentions: 0, independent_authors: 0 },
          data_gaps: [{ reason: "no_current_admission" }],
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.dataGaps).toEqual(["not admitted"]);
    expect(vm.metrics.find((metric) => metric.key === "admission")).toMatchObject({
      value: "not admitted",
      detail: "0 posts · 0 authors",
    });
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

  it("surfaces CEX open interest in the live market panel", () => {
    const dossier = tokenCaseFixture();
    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        market_live: {
          ...dossier.market_live,
          status: "ready",
          provider: "okx_cex_rest",
          price_usd: 1.24,
          open_interest_usd: 12_400_000,
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.market.openInterestLabel).toBe("$12M");
  });
});
