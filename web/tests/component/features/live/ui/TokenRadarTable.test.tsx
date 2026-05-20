import { TokenRadarTable } from "@features/live/ui/TokenRadarTable";
import type { TokenFlowItem } from "@lib/types";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TokenRadarTable rows", () => {
  it("does not render unresolved intent ids as address-like token subtitles", () => {
    renderTokenRadarTable([unresolvedSymbolOnly()]);

    expect(screen.getByText("$SLOP")).toBeInTheDocument();
    expect(
      screen.getByText("symbol-only · 候选价格过期 · 2 candidates · found:2"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/8ff41158.*e70faa/i)).not.toBeInTheDocument();
  });

  it("renders DEX market cap as the primary market value", async () => {
    const { container } = renderTokenRadarTable([mixedFreshnessToken()]);

    const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
    expect(
      screen.queryByRole("button", { name: "Open Search Intel for $TROLL" }),
    ).not.toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "官网" })).toHaveAttribute(
      "href",
      "https://troll.example",
    );
    expect(within(row).getByRole("link", { name: "X" })).toHaveAttribute(
      "href",
      "https://x.com/troll",
    );
    expect(within(row).getByRole("link", { name: "GMGN" })).toHaveAttribute(
      "href",
      "https://gmgn.ai/eth/token/0x1111111111111111111111111111111111111111",
    );
    expect(row.querySelector(".radar-token-logo")).toHaveAttribute(
      "src",
      "https://cdn.example.test/troll.png",
    );
    expect(within(row).getByText("$TROLL")).toBeInTheDocument();
    expect(within(row).getByText("ETH · 0x111111...111111")).toBeInTheDocument();
    expect(within(row).getByText("1 帖 · 1 作者")).toBeInTheDocument();
    expect(within(row).getByText("关注源 0 · 较前窗 +1")).toBeInTheDocument();
    expect(within(row).getByText("叙事分析暂不可用")).toBeInTheDocument();
    expect(within(row).getByText("discussion digest missing")).toBeInTheDocument();
    expect(within(row).queryByText("种子中 · 1 条有效讨论")).not.toBeInTheDocument();
    expect(within(row).queryByText("profile")).not.toBeInTheDocument();
    expect(within(row).queryByText("links")).not.toBeInTheDocument();
    expect(within(row).queryByText("unverified")).not.toBeInTheDocument();
    expect(within(row).queryByText("investigate")).not.toBeInTheDocument();
    expect(within(row).queryByText("Official")).not.toBeInTheDocument();
    expect(within(row).queryByText("Community")).not.toBeInTheDocument();
    expect(within(row).queryByText("Narrative")).not.toBeInTheDocument();
    expect(within(row).queryByText("Decision")).not.toBeInTheDocument();
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("$51M");
    expect(market).toHaveTextContent("-");
    expect(market).toHaveTextContent("liq");
    expect(market).toHaveTextContent("$3M");
    expect(market).toHaveTextContent("vol");
    expect(market).toHaveTextContent("$1.3M");
    expect(market).toHaveTextContent("holders");
    expect(market).toHaveTextContent("52K");
    expect(market).not.toHaveTextContent("partial");
    expect(market).not.toHaveTextContent("cap stale");
    expect(market).not.toHaveTextContent("$0.104");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks rows with normalized chain and CEX venue labels", () => {
    const base = tokenWithVenue({
      symbol: "BASER",
      chain: "eip155:8453",
      targetId: "asset:eip155:8453:erc20:0x1111111111111111111111111111111111111111",
    });

    renderTokenRadarTable([base]);

    const row = screen.getByRole("article", { name: "Token Radar item $BASER" });
    expect(within(row).getByText("BASE")).toHaveClass("radar-venue-badge");
    expect(within(row).getByText("BASE · 0x111111...111111")).toBeInTheDocument();
    expect(row).not.toHaveTextContent("eip155:8453");
  });

  it("filters rows by one selected chain or CEX venue while defaulting to all", () => {
    const eth = tokenWithVenue({
      symbol: "ETHY",
      chain: "eip155:1",
      targetId: "asset:eip155:1:erc20:0x1111111111111111111111111111111111111111",
    });
    const base = tokenWithVenue({
      symbol: "BASER",
      chain: "eip155:8453",
      targetId: "asset:eip155:8453:erc20:0x2222222222222222222222222222222222222222",
    });
    const sol = tokenWithVenue({
      address: "33eum82LaAhtv5YkUq1BdwEviSErH5CnFxqVNLT5pump",
      symbol: "SOLLY",
      chain: "solana",
      targetId: "asset:solana:token:33eum82LaAhtv5YkUq1BdwEviSErH5CnFxqVNLT5pump",
    });
    renderTokenRadarTable([eth, base, sol, cexToken()]);

    expect(screen.getByRole("button", { name: "All" })).toHaveClass("active");
    expect(screen.getByRole("article", { name: "Token Radar item $ETHY" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Token Radar item $BASER" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Token Radar item $SOLLY" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Token Radar item $OPN" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "BASE" }));

    expect(screen.getByRole("button", { name: "BASE" })).toHaveClass("active");
    expect(screen.getByRole("article", { name: "Token Radar item $BASER" })).toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Token Radar item $ETHY" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Token Radar item $SOLLY" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Token Radar item $OPN" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "CEX" }));

    expect(screen.getByRole("button", { name: "CEX" })).toHaveClass("active");
    expect(screen.getByRole("article", { name: "Token Radar item $OPN" })).toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Token Radar item $BASER" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));

    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("renders hydrated narrative digest in the why-now cell", () => {
    renderTokenRadarTable([
      {
        ...mixedFreshnessToken(),
        discussion_digest: {
          status: "ready",
          dominant_narrative: {
            title: "隐私轮动",
            summary_zh: "资金转向隐私叙事",
            evidence_refs: [],
          },
          stance_mix: { bullish: 0.7 },
          coverage: {
            semantic_coverage: 0.75,
            source_mentions: 4,
            labeled_mentions: 3,
            independent_authors: 2,
          },
          data_gaps: [],
          evidence_refs: [],
        },
      },
    ]);

    const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
    expect(within(row).getByText("隐私轮动 · bullish 70%")).toBeInTheDocument();
    expect(within(row).getByText("资金转向隐私叙事 · coverage 75%")).toBeInTheDocument();
  });

  it("renders empty state when not loading and no items, instead of a skeleton", () => {
    render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        items={[]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText("loading token radar")).not.toBeInTheDocument();
    expect(screen.queryByText("loading")).not.toBeInTheDocument();
    expect(screen.getByText("no live cases")).toBeInTheDocument();
    expect(screen.getByText("当前窗口暂无可交易 token 热度")).toBeInTheDocument();
  });

  it("shows the skeleton only while the query is genuinely pending", () => {
    render(
      <TokenRadarTable
        error={null}
        isLoading={true}
        isRefreshing={false}
        items={[]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("loading token radar")).toBeInTheDocument();
    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(screen.queryByText("当前窗口暂无可交易 token 热度")).not.toBeInTheDocument();
  });

  it("keeps the last settled rows visible while radar refreshes", () => {
    render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        isRefreshing={true}
        items={[mixedFreshnessToken()]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("article", { name: "Token Radar item $TROLL" })).toBeInTheDocument();
    expect(screen.getByText("1 live case · updating")).toBeInTheDocument();
    expect(screen.queryByLabelText("loading token radar")).not.toBeInTheDocument();
    expect(screen.queryByText("当前窗口暂无可交易 token 热度")).not.toBeInTheDocument();
  });

  it("shows token radar errors instead of the empty-data loading state", () => {
    render(
      <TokenRadarTable
        error={new Error("boom")}
        isLoading={true}
        isRefreshing={false}
        items={[]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText("loading token radar")).not.toBeInTheDocument();
    expect(screen.getByText("Token Radar 暂不可用 · boom")).toBeInTheDocument();
  });

  it("opens token detail from the whole row", () => {
    const item = mixedFreshnessToken();
    const onSelect = vi.fn();
    render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        items={[item]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={onSelect}
        onWindowChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("article", { name: "Token Radar item $TROLL" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(item);
  });

  it("does not fall back to token price for DEX rows without market cap", () => {
    const item = mixedFreshnessToken();
    renderTokenRadarTable([
      {
        ...item,
        market: {
          ...item.market,
          market_cap: null,
          market_cap_status: "missing",
        },
      },
    ]);

    const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("-");
    expect(market).toHaveTextContent("liq");
    expect(market).toHaveTextContent("holders");
    expect(market).not.toHaveTextContent("cap missing");
    expect(market).not.toHaveTextContent("$0.104");
  });

  it("suppresses anchored readiness noise from compact radar cells", () => {
    const item = mixedFreshnessToken();
    renderTokenRadarTable([
      {
        ...item,
        market: {
          ...item.market,
          market_status: "anchored",
          price_status: "ready",
          market_cap: 236_000,
          market_cap_status: "live",
          liquidity: 9_000,
          liquidity_status: "live",
          price_change_since_social_pct: null,
          price_change_since_first_snapshot_pct: null,
          price_change_status: "live_not_persisted",
        },
      },
    ]);

    const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
    const market = row.querySelector('[data-radar-metric="market"]') as HTMLElement;
    expect(market).toHaveTextContent("$236K");
    expect(market).not.toHaveTextContent("anchored");
    expect(market).not.toHaveTextContent("price ready");
    expect(market).not.toHaveTextContent("cap live");
    expect(market).not.toHaveTextContent("liq live");
    expect(row.querySelector('[data-radar-metric="timing"]')).not.toBeInTheDocument();
    expect(row).not.toHaveTextContent("live not persisted");
  });

  it("renders CEX venue links directly without a profile abstraction", () => {
    const logoUrl = "https://bin.bnbstatic.com/image/admin_mgs_image_upload/opn.png";
    renderTokenRadarTable([cexToken()]);

    const row = screen.getByRole("article", { name: "Token Radar item $OPN" });
    expect(row.querySelector(".radar-token-logo")).toHaveAttribute(
      "src",
      `/api/token-image?url=${encodeURIComponent(logoUrl)}`,
    );
    expect(within(row).getByRole("link", { name: "X" })).toHaveAttribute(
      "href",
      "https://x.com/opn",
    );
    expect(within(row).getByRole("link", { name: "OKX" })).toHaveAttribute(
      "href",
      "https://www.okx.com/trade-swap/opn-usdt-swap",
    );
    expect(within(row).queryByText("profile")).not.toBeInTheDocument();
  });

  it("renders the compact scan bar without old sort controls or table labels", () => {
    render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        items={[mixedFreshnessToken()]}
        scope="matched"
        selectedKey={null}
        windowKey="5m"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
    expect(screen.getByText("1 live case")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5m" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "watched" })).toHaveClass("active");

    for (const label of ["Attention", "Proof", "Reach", "Entry"]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
    for (const label of ["Official", "Community", "Narrative"]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("renders market stats and relative listed age for ranked rows", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(1_778_426_440_000));
    const item = withRadarMeta(mixedFreshnessToken(), {
      listed_at_ms: 1_778_420_000_000,
      rank: 4,
    });

    render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        items={[item]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /sort by holders/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sort by market/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sort by listed/i })).toBeInTheDocument();
    expect(screen.getByText("52K")).toBeInTheDocument();
    expect(screen.getByText("$1.3M")).toBeInTheDocument();
    expect(screen.getByText("#4")).toBeInTheDocument();
    expect(screen.getByText("1h前")).toBeInTheDocument();
    expect(screen.queryByText(/2026-/)).not.toBeInTheDocument();
  });

  it("keeps score before listed time without a trailing Search action", () => {
    renderTokenRadarTable([mixedFreshnessToken()]);

    const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
    const children = Array.from(row.children);
    expect(children.map((child) => child.className)).toEqual([
      "token-radar-cell case",
      "token-radar-cell social",
      "token-radar-cell why",
      "token-radar-cell market",
      "token-radar-cell score",
      "token-radar-cell listed",
    ]);
    expect((children.at(-2) as HTMLElement).querySelector(".radar-score")).toBeInTheDocument();
    expect(within(children.at(-1) as HTMLElement).getByText("rank -")).toBeInTheDocument();
    expect(
      within(children.at(-1) as HTMLElement).queryByRole("button", {
        name: "Open Search Intel for $TROLL",
      }),
    ).not.toBeInTheDocument();
  });

  it("uses score ranking as the default table sort", () => {
    const low = withRadarMeta(
      {
        ...mixedFreshnessToken(),
        identity: { ...mixedFreshnessToken().identity, symbol: "LOW" },
        opportunity: { ...mixedFreshnessToken().opportunity, score: 12 },
      },
      { listed_at_ms: 1_778_420_000_000, rank: 12 },
    );
    const high = withRadarMeta(
      {
        ...mixedFreshnessToken(),
        identity: { ...mixedFreshnessToken().identity, symbol: "HIGH" },
        opportunity: { ...mixedFreshnessToken().opportunity, score: 91 },
      },
      { listed_at_ms: 1_778_421_000_000, rank: 1 },
    );
    const { container } = render(
      <TokenRadarTable
        error={null}
        isLoading={false}
        items={[low, high]}
        scope="all"
        selectedKey={null}
        windowKey="1h"
        onScopeChange={vi.fn()}
        onSelect={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    const rows = Array.from(container.querySelectorAll(".token-radar-row"));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("$HIGH");
    expect(rows[1]).toHaveTextContent("$LOW");
  });
});

function renderTokenRadarTable(items: TokenFlowItem[]) {
  return render(
    <TokenRadarTable
      error={null}
      isLoading={false}
      items={items}
      scope="all"
      selectedKey={null}
      windowKey="1h"
      onScopeChange={vi.fn()}
      onSelect={vi.fn()}
      onWindowChange={vi.fn()}
    />,
  );
}

function withRadarMeta(
  item: TokenFlowItem,
  radar: Pick<NonNullable<TokenFlowItem["radar"]>, "listed_at_ms" | "rank">,
): TokenFlowItem {
  return {
    ...item,
    radar: {
      lane: "resolved",
      computed_at_ms: 1_778_426_440_000,
      source_max_received_at_ms: 1_778_426_100_000,
      ...radar,
    },
  } as TokenFlowItem;
}

function tokenWithVenue({
  address = "0x1111111111111111111111111111111111111111",
  chain,
  symbol,
  targetId,
}: {
  address?: string;
  chain: string;
  symbol: string;
  targetId: string;
}): TokenFlowItem {
  const item = mixedFreshnessToken();
  return {
    ...item,
    identity: {
      ...item.identity,
      address,
      asset_id: targetId,
      chain,
      identity_key: targetId,
      symbol,
      target_id: targetId,
    },
  };
}

function mixedFreshnessToken(): TokenFlowItem {
  const item = unresolvedSymbolOnly();
  return {
    ...item,
    identity: {
      ...item.identity,
      identity_key: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      identity_status: "EXACT",
      target_type: "Asset",
      target_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      asset_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
      asset_type: "Asset",
      venue_type: "dex",
      exchange: "gmgn",
      chain: "eth",
      address: "0x1111111111111111111111111111111111111111",
      symbol: "TROLL",
      resolution_reasons: [],
    },
    market: {
      event_anchor: null,
      decision_latest: {
        target_type: "Asset",
        target_id: "asset:dex:eth:0x1111111111111111111111111111111111111111",
        source: "decision_latest",
        price_usd: 0.104,
        market_cap_usd: 51_000_000,
        liquidity_usd: 3_000_000,
        holders: 52_000,
        observed_at_ms: 1_778_426_440_000,
        received_at_ms: 1_778_426_440_000,
        provider: "okx_dex_price",
      },
      readiness: {
        anchor_status: "ready",
        latest_status: "live",
        dex_floor_status: "ready",
        missing_fields: [],
        stale_fields: [],
      },
      market_status: "partial",
      price: 0.104,
      price_status: "fresh",
      market_cap: 51_000_000,
      market_cap_status: "stale",
      liquidity: 3_000_000,
      liquidity_status: "stale",
      volume_24h: 1_300_000,
      volume_24h_status: "stale",
      holder_count: 52_000,
      holder_count_status: "stale",
      pool_status: "missing",
      snapshot_age_ms: 30_000,
      snapshot_received_at_ms: 1_778_426_440_000,
      provider: "okx_dex_price",
      price_change_status: "insufficient_history",
    },
    timing: {
      ...item.timing,
      status: "neutral",
      risks: [],
      market_observation_status: "partial",
    },
    tradeability: {
      ...item.tradeability,
      identity_tradeable: true,
      market_fresh: true,
      market_cap_present: true,
      liquidity_present: true,
      risks: [],
      score: 64,
    },
    profile: {
      status: "ready",
      provider: "gmgn_dex_profile",
      identity: {
        symbol: "TROLL",
        name: "Troll Protocol",
        logo_url: "https://cdn.example.test/troll.png",
      },
      links: {
        website_url: "https://troll.example",
        twitter_url: "https://x.com/troll",
        gmgn_url: "https://gmgn.ai/eth/token/0x1111111111111111111111111111111111111111",
      },
    },
  };
}

function cexToken(): TokenFlowItem {
  const item = mixedFreshnessToken();
  return {
    ...item,
    identity: {
      ...item.identity,
      identity_key: "cex_token:OPN",
      identity_status: "EXACT",
      target_type: "CexToken",
      target_id: "cex_token:OPN",
      asset_id: null,
      asset_type: "CexToken",
      venue_type: "cex",
      exchange: "okx",
      inst_id: "OPN-USDT-SWAP",
      inst_type: "SWAP",
      chain: null,
      address: null,
      symbol: "OPN",
      resolution_reasons: [],
    },
    market: {
      ...item.market,
      market_cap: null,
      market_cap_status: "missing",
      price: 0.084,
      price_status: "fresh",
      price_change_since_social_pct: -0.032,
      price_change_status: "ready",
      provider: "okx",
    },
    profile: {
      status: "ready",
      provider: "binance_cex_profile",
      identity: {
        symbol: "OPN",
        name: "Open Protocol",
        logo_url: "https://bin.bnbstatic.com/image/admin_mgs_image_upload/opn.png",
      },
      links: {
        twitter_username: "opn",
      },
    },
  };
}

function unresolvedSymbolOnly(): TokenFlowItem {
  return {
    identity: {
      identity_key: "8ff41158250b70866f20284037a06ed483d97883fd0eaa4ac11932f4b3e70faa",
      identity_status: "AMBIGUOUS",
      target_type: null,
      target_id: null,
      asset_id: null,
      chain: null,
      address: null,
      symbol: "SLOP",
      resolution_reasons: ["SYMBOL_CANDIDATES_STALE"],
      candidate_count: 2,
      discovery_status: "found:2",
    },
    market: {
      event_anchor: null,
      decision_latest: null,
      readiness: {
        anchor_status: "missing",
        latest_status: "missing",
        dex_floor_status: "not_applicable",
        missing_fields: [],
        stale_fields: [],
      },
      market_status: "missing",
      price_change_status: "missing",
    },
    flow: {
      window: "5m",
      mentions: 1,
      watched_mentions: 0,
      previous_mentions: 0,
      mention_delta: 1,
      stream_dominance: 1,
      baseline_status: "insufficient_history",
      baseline_sample_count: 0,
    },
    social_heat: {
      score_version: "token_factor_snapshot_v3_social_attention:social_heat",
      score: 44,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      window: "5m",
      mentions: 1,
      mentions_5m: 1,
      mentions_1h: 1,
      mentions_4h: 1,
      mentions_24h: 1,
      weighted_mentions: 1,
      previous_mentions: 0,
      mention_delta: 1,
      stream_share: 1,
      watched_share: 0,
      status: "insufficient_history",
    },
    discussion_quality: {
      score_version: "token_factor_snapshot_v3_social_attention:discussion_quality",
      score: 43,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      evidence_specificity: 0,
      avg_post_quality: 43,
      avg_attribution_confidence: 0,
      duplicate_text_share: 0,
      informative_post_count: 1,
      watched_source_count: 0,
    },
    propagation: {
      score_version: "token_factor_snapshot_v3_social_attention:propagation",
      score: 50,
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      independent_authors: 1,
      effective_authors: 1,
      new_authors: 1,
      top_author_share: 1,
      duplicate_text_share: 0,
      author_entropy: 0,
      phase: "seed",
      top_authors: [],
    },
    tradeability: {
      score_version: "token_factor_snapshot_v3_social_attention:gates",
      score: 0,
      reasons: [],
      risks: ["identity_not_tradeable"],
      contributions: [],
      risk_caps: [],
      identity_tradeable: false,
      market_fresh: false,
      market_cap_present: false,
      liquidity_present: false,
      pool_present: false,
    },
    timing: {
      score_version: "token_factor_snapshot_v3_social_attention:timing",
      score: 0,
      status: "market_unavailable",
      chase_risk: false,
      reasons: [],
      risks: ["no_resolved_target"],
      market_observation_status: "no_resolved_target",
    },
    opportunity: {
      score_version: "token_factor_snapshot_v3_social_attention:composite",
      score: 44,
      decision: "investigate",
      reasons: [],
      risks: [],
      contributions: [],
      risk_caps: [],
      components: { heat: 44, quality: 43, propagation: 50, timing: 0 },
    },
    watch: {
      status: "seed",
      direct_mentions: 1,
      direct_authors: 1,
      seed_link_count: 0,
      top_seed: null,
      reasons: [],
      risks: [],
    },
    evidence_total_count: 1,
    posts_query: {
      target_type: null,
      target_id: null,
      window: "5m",
      scope: "all",
      range: "current_window",
    },
    timeline_query: { target_type: null, target_id: null, window: "5m", scope: "all" },
  };
}
