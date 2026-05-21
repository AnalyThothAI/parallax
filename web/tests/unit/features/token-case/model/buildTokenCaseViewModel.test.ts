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
    expect(vm.hero.subtitle).toBe("Contract-confirmed Solana rotation");
    expect(vm.metrics.map((metric) => metric.key)).toEqual([
      "mentions",
      "phase",
      "watched",
      "readiness",
    ]);
    expect(vm.hero.logoUrl).toBe("https://example.test/hansa.png");
    expect(vm.propagation.stages).toHaveLength(3);
    expect(vm.propagation.summaryZh).toBe("语义扩散从 CA 证据帖进入 scanner 复述。");
    expect(vm.timeline.items[0].pills.map((pill) => pill.label)).toContain("bullish");
    expect(vm.timeline.items[0].pills.map((pill) => pill.label)).not.toContain("PQ 82");
    expect(vm.market.status).toBe("missing");
    expect(vm.bullBear.bull.title).toBe("Bull · 多头");
    expect(vm.bullBear.bull.thesis).toContain("多个独立账号围绕 CA 证据");
    expect(vm.bullBear.bear.title).toBe("Bear · 空头");
    expect(vm.propagation.currentness).toMatchObject({
      displayStatus: "current",
      deltaSourceEventCount: 0,
      deltaIndependentAuthorCount: 0,
      label: "叙事已更新",
    });
    expect(vm.propagation.statusPills.map((pill) => pill.label)).toContain("叙事已更新");
    expect(vm.propagation.statusPills.some((pill) => pill.label.startsWith("last ready "))).toBe(
      true,
    );
    expect(vm.dataGaps).toEqual([
      "live market snapshot missing",
      "official liquidity route not confirmed",
    ]);
  });

  it("does not read canonical token agent_brief as a fallback narrative", () => {
    const dossier = tokenCaseFixture();
    const dossierWithRemovedLegacyBrief = {
      ...dossier,
      agent_brief: undefined,
    };

    const vm = buildTokenCaseViewModel({
      dossier: dossierWithRemovedLegacyBrief,
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.propagation.summaryZh).toBe("语义扩散从 CA 证据帖进入 scanner 复述。");
    expect(vm.bullBear.stance).toBe("watch");
  });

  it("normalizes structured digest data gaps for the details rail", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        discussion_digest: {
          ...dossier.discussion_digest,
          status: "pending",
          currentness: {
            display_status: "not_ready",
            reason: "no_ready_digest",
            delta_source_event_count: 0,
            delta_independent_author_count: 0,
          },
          data_gaps: [{ reason: "no_ready_digest" }],
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.dataGaps).toEqual(["叙事待生成"]);
    expect(vm.propagation.currentness.label).toBe("叙事待生成");
  });

  it("keeps ready narrative visible while currentness is updating", () => {
    const dossier = tokenCaseFixture();

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        discussion_digest: {
          ...dossier.discussion_digest,
          currentness: {
            ...dossier.discussion_digest.currentness,
            display_status: "updating",
            reason: "digest_updating",
            delta_source_event_count: 6,
            delta_independent_author_count: 2,
            last_ready_computed_at_ms: 1_777_746_000_000,
          },
          data_gaps: [{ reason: "digest_updating", delta_source_event_count: 6 }],
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.hero.subtitle).toBe("Contract-confirmed Solana rotation");
    expect(vm.propagation.summaryZh).toBe("语义扩散从 CA 证据帖进入 scanner 复述。");
    expect(vm.propagation.currentness).toMatchObject({
      displayStatus: "updating",
      deltaSourceEventCount: 6,
      deltaIndependentAuthorCount: 2,
      deltaLabel: "+6 posts · +2 authors",
      label: "叙事更新中 +6",
    });
    expect(vm.propagation.statusPills.map((pill) => pill.label)).toEqual(
      expect.arrayContaining(["叙事更新中 +6", "+6 posts · +2 authors"]),
    );
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

  it("uses the token image proxy for Binance-hosted hero logos", () => {
    const dossier = tokenCaseFixture();
    const logoUrl = "https://bin.bnbstatic.com/image/admin_mgs_image_upload/btc.png";

    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        profile: {
          ...dossier.profile!,
          identity: {
            ...dossier.profile!.identity!,
            logo_url: logoUrl,
          },
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
    });

    expect(vm.hero.logoUrl).toBe(`/api/token-image?url=${encodeURIComponent(logoUrl)}`);
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

  it("maps CEX detail snapshots into a derivatives view", () => {
    const dossier = tokenCaseFixture();
    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        target: {
          ...dossier.target,
          target_type: "CexToken",
          target_id: "cex_token:BTC",
          symbol: "BTC",
          chain_id: null,
          address: null,
        },
        cex_detail: {
          snapshot_id: "cex-detail:binance:BTCUSDT",
          target_type: "CexToken",
          target_id: "cex_token:BTC",
          exchange: "binance",
          native_market_id: "BTCUSDT",
          status: "partial",
          baseline_status: "ready",
          coinglass_status: "unavailable",
          mark_price: 67_050,
          funding_rate: 0.0001,
          volume_24h_usd: 12_400_000,
          open_interest_usd: 98_000_000,
          oi_change_pct_24h: 3.5,
          cvd_delta_4h: -1_250_000,
          level_bands: [{ kind: "resistance", price: 72_000, score: 0.82 }],
          degraded_reasons: ["coinglass_unavailable"],
          source_refs: [{ ref_id: "metric:cex:open_interest_usd:BTCUSDT" }],
          observed_at_ms: 1_777_746_000_000,
          computed_at_ms: 1_777_746_030_000,
        },
      },
      route: { window: "1h", scope: "all", postSort: "recent" },
      posts: dossier.posts,
    });

    expect(vm.cexDetail?.instrumentLabel).toBe("Binance · BTCUSDT");
    expect(vm.cexDetail?.statusLabel).toBe("partial");
    expect(vm.cexDetail?.metrics.find((metric) => metric.key === "open_interest")?.value).toBe(
      "$98M",
    );
    expect(vm.cexDetail?.oiDeltas.find((delta) => delta.label === "OI 24h")?.value).toBe("+3.5%");
    expect(vm.cexDetail?.cvdDeltas.find((delta) => delta.label === "CVD 4h")?.value).toBe("-$1.3M");
    expect(vm.cexDetail?.levels[0]).toMatchObject({
      kind: "resistance",
      priceLabel: "$72K",
    });
    expect(vm.cexDetail?.dataGaps).toEqual(["CoinGlass unavailable"]);
  });
});
