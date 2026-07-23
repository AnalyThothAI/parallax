import type { NewsFactItem, NewsFactRow } from "@features/news/model/newsFactViewModel";

const NOW_MS = 1_779_000_000_000;

export function newsRowFixture(overrides: Partial<NewsFactRow> = {}): NewsFactRow {
  return {
    canonical_item_key: "canonical:news-1",
    canonical_url: "https://example.test/news-1",
    computed_at_ms: NOW_MS,
    content_class: "market_update",
    content_classification: { basis: "provider_content_class" },
    content_tags: ["etf", "bitcoin"],
    duplicate_count: 1,
    fact_lanes: [
      {
        fact_candidate_id: "fact-1",
        event_type: "fund_flow",
        realis: "actual",
        status: "accepted",
        affected_targets: [{ symbol: "BTC" }],
      },
    ],
    headline: "BTC ETF flows expand",
    latest_at_ms: NOW_MS,
    lifecycle_status: "processed",
    market_scope: marketScopeFixture(),
    news_item_id: "news-1",
    projection_version: "news_page_projection_v1",
    provider_article_keys: ["opennews:news-1"],
    provider_rating: providerRatingFixture(),
    representative_news_item_id: "news-1",
    row_id: "row-1",
    source: sourceSummaryFixture(),
    source_domain: "6551.io",
    source_domains: ["6551.io"],
    source_ids: ["source-opennews"],
    story: storyFixture(),
    story_key: "story:btc-etf-flow",
    summary: "ETF desk activity stays elevated.",
    token_lanes: [
      {
        lane: "resolved",
        resolution_status: "resolved",
        symbol: "BTC",
        display_name: "Bitcoin",
        target_id: "token:btc",
        target_type: "CexToken",
        reason_codes: ["canonical_symbol"],
      },
      {
        lane: "resolved",
        resolution_status: "resolved",
        symbol: "ETH",
        display_name: "Ethereum",
        target_id: "token:eth",
        target_type: "CexToken",
        reason_codes: ["canonical_symbol"],
      },
    ],
    ...overrides,
  };
}

export function newsItemFixture(overrides: Partial<NewsFactItem> = {}): NewsFactItem {
  return {
    body_text: "OpenNews source content.",
    canonical_url: "https://example.test/news-1",
    content_class: "market_update",
    content_classification: { basis: "provider_content_class" },
    content_tags: ["etf", "bitcoin"],
    created_at_ms: NOW_MS - 120_000,
    duplicate_observation_count: 1,
    entities: [{ kind: "organization", name: "ETF desk" }],
    fact_candidates: [{ fact_candidate_id: "fact-1", status: "accepted" }],
    fact_lanes: newsRowFixture().fact_lanes,
    fetch_run: { run_id: "fetch-1" },
    fetched_at_ms: NOW_MS - 30_000,
    language: "en",
    lifecycle_status: "processed",
    market_scope: marketScopeFixture(),
    news_item_id: "news-1",
    observation_edges: [
      {
        observation_id: "observation-1",
        source_domain: "6551.io",
        source_id: "source-opennews",
      },
    ],
    processed_at_ms: NOW_MS - 20_000,
    processing_error: null,
    provider_item: { article_key: "opennews:news-1" },
    provider_observations: [{ observation_id: "observation-1" }],
    provider_rating: providerRatingFixture(),
    published_at_ms: NOW_MS - 60_000,
    representative_news_item_id: "news-1",
    source: sourceDetailFixture(),
    source_domain: "6551.io",
    source_id: "source-opennews",
    story: storyFixture(),
    story_key: "story:btc-etf-flow",
    summary: "ETF desk activity stays elevated.",
    title: "BTC ETF flows expand",
    token_lanes: newsRowFixture().token_lanes,
    token_mentions: [{ text: "BTC" }],
    updated_at_ms: NOW_MS,
    ...overrides,
  };
}

function marketScopeFixture() {
  return {
    basis: { subject: "crypto" },
    primary: "crypto",
    reason: "resolved_crypto_target",
    scope: ["crypto"],
    status: "classified",
    version: "news_market_scope_v1",
  };
}

function providerRatingFixture() {
  return {
    direction: "bullish",
    grade: "A",
    method: "provider_rating",
    provider: "opennews",
    score: 82,
    signal: "long",
    status: "ready",
  };
}

function storyFixture() {
  return {
    member_count: 2,
    member_news_item_ids: ["news-1", "news-2"],
    provider_article_keys: ["opennews:news-1", "opennews:news-2"],
    representative_news_item_id: "news-1",
    source_domains: ["6551.io"],
    source_ids: ["source-opennews"],
    story_key: "story:btc-etf-flow",
  };
}

function sourceSummaryFixture() {
  return {
    coverage_tags: ["crypto"],
    provider_type: "opennews",
    source_domain: "6551.io",
    source_id: "source-opennews",
    source_name: "OpenNews",
    source_quality_status: "healthy",
    source_role: "aggregator",
    trust_tier: "standard",
  };
}

function sourceDetailFixture() {
  return {
    ...sourceSummaryFixture(),
    asset_universe: ["crypto"],
    authority_scope: { markets: ["crypto"] },
    created_at_ms: NOW_MS - 1_000_000,
    enabled: true,
    managed_by_config: true,
    refresh_interval_seconds: 60,
    updated_at_ms: NOW_MS,
  };
}
