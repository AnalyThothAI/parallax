import type { Page, Route } from "@playwright/test";
import {
  macroCorrelationFixture,
  macroModuleFixture,
  macroOverviewModuleFixture,
  macroSeriesFixture,
} from "@tests/fixtures/macroFixture";
import { marketContextFixture, marketObservationFixture } from "@tests/fixtures/marketFixtures";
import { tokenCaseFixture, tokenCasePostsFixture } from "@tests/fixtures/tokenCaseFixture";

const NOW = 1_777_746_300_000;
const ADDRESS = "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
const TARGET_ID = `asset:dex:eth:${ADDRESS.toLowerCase()}`;
const unhandledApiRequests = new WeakMap<Page, string[]>();

export type MockApiOptions = {
  delayNonBootstrapMs?: number;
  failNonBootstrap?: boolean;
};

export async function installMockApi(page: Page, options: MockApiOptions = {}) {
  unhandledApiRequests.set(page, []);

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path !== "/api/bootstrap") {
      if (options.delayNonBootstrapMs) {
        await new Promise((resolve) => setTimeout(resolve, options.delayNonBootstrapMs));
      }
      if (options.failNonBootstrap) {
        return route.abort("failed");
      }
    }

    if (path === "/api/bootstrap") {
      return fulfill(route, {
        ws_token: "secret",
        handles: ["toly", "traderpow"],
        replay_limit: 25,
      });
    }
    if (path === "/api/status") return fulfill(route, statusData());
    if (path === "/api/recent") return fulfill(route, recentData());
    if (path === "/api/token-radar") return fulfill(route, tokenRadarData(url));
    if (path === "/api/token-case") return fulfill(route, tokenCaseData(url));
    if (path.startsWith("/api/token-images/")) return fulfillTokenImage(route);
    if (path === "/api/search/inspect") return fulfill(route, searchInspectData(url));
    if (path === "/api/signal-lab/pulse") return fulfill(route, signalPulseData(url));
    if (path.startsWith("/api/signal-lab/pulse/")) return fulfill(route, pulseItem());
    if (path === "/api/social-events/by-ids") return fulfill(route, socialEventsByIds(url));
    if (path === "/api/target-social-timeline") return fulfill(route, timelineData());
    if (path === "/api/target-posts") return fulfill(route, targetPostsData(url));
    if (path === "/api/account-quality") return fulfill(route, accountQualityData());
    if (path === "/api/notification-summary") return fulfill(route, notificationSummary());
    if (path === "/api/notifications") return fulfill(route, notificationsData());
    if (path === "/api/news") return fulfill(route, newsRowsData());
    if (path.startsWith("/api/news/items/")) return fulfill(route, newsItemDetailData(path));
    if (path === "/api/equity-events") return fulfill(route, equityEventRowsData());
    if (path === "/api/equity-events/calendar") return fulfill(route, equityEventCalendarData());
    if (path === "/api/equity-events/summary") return fulfill(route, equityEventSummaryData());
    if (path.startsWith("/api/equity-events/")) return fulfill(route, equityEventDetailData(path));
    if (path.endsWith("/read"))
      return fulfill(route, { notification_id: "notification-1", updated: true });
    if (path === "/api/notifications/read-all") return fulfill(route, { updated: true });
    if (path === "/api/stocks-radar") return fulfill(route, stocksRadarData(url));
    if (path === "/api/watchlist/handles/overview") return fulfill(route, watchlistOverviewData());
    if (path.match(/^\/api\/watchlist\/handles?\/[^/]+\/overview$/)) {
      return fulfill(route, watchlistHandleOverviewData(handleFromPath(path)));
    }
    if (path.match(/^\/api\/watchlist\/handles?\/[^/]+\/summary$/)) {
      return fulfill(route, watchlistHandleSummaryData(handleFromPath(path)));
    }
    if (path.match(/^\/api\/watchlist\/handles?\/[^/]+\/timeline$/)) {
      return fulfill(route, watchlistHandleTimelineData(handleFromPath(path)));
    }
    if (path === "/api/macro") return fulfill(route, macroData());
    if (path === "/api/macro/assets/correlation") return fulfill(route, macroCorrelationData(url));
    if (path.startsWith("/api/macro/modules/")) {
      const moduleId = macroModuleIdFromPath(path);
      if (isParentMacroModule(moduleId)) {
        recordUnhandledApiRequest(page, url);
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            ok: false,
            error: "unsupported_macro_module",
            field: "module_id",
          }),
        });
      }
      return fulfill(route, macroModuleData(moduleId));
    }
    if (path === "/api/macro/series") return fulfill(route, macroSeriesData(url));
    if (path === "/api/ops/diagnostics") return fulfill(route, opsDiagnosticsData());
    if (path.startsWith("/api/ops/queues/")) return fulfill(route, opsQueueData(path));

    recordUnhandledApiRequest(page, url);
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, error: `unhandled ${path}` }),
    });
  });
}

export function getUnhandledApiRequests(page: Page): string[] {
  return [...(unhandledApiRequests.get(page) ?? [])];
}

function recordUnhandledApiRequest(page: Page, url: URL) {
  const requests = unhandledApiRequests.get(page) ?? [];
  requests.push(`${url.pathname}${url.search}`);
  unhandledApiRequests.set(page, requests);
}

function newsRowsData() {
  return {
    items: [
      {
        row_id: "news-row-1",
        news_item_id: "news-row-1",
        lifecycle_status: "processed",
        headline: "Macro desk flags liquidity rotation",
        latest_at_ms: NOW,
        canonical_url: "https://example.com/macro-liquidity",
        source_domain: "example.com",
        summary: "Liquidity rotation is visible across crypto beta and rates-sensitive assets.",
        token_lanes: [
          { lane: "resolved", symbol: "UPEG", target_type: "Asset", target_id: TARGET_ID },
        ],
        fact_lanes: [{ lane: "accepted", summary: "Funding stress remains elevated." }],
      },
    ],
    next_cursor: null,
  };
}

function newsItemDetailData(path: string) {
  const newsItemId = decodeURIComponent(path.split("/").pop() ?? "news-row-1");
  return {
    row_id: newsItemId,
    news_item_id: newsItemId,
    lifecycle_status: "processed",
    headline: "Macro desk flags liquidity rotation",
    latest_at_ms: NOW,
    canonical_url: "https://example.com/macro-liquidity",
    source_domain: "example.com",
    summary: "Liquidity rotation is visible across crypto beta and rates-sensitive assets.",
    content:
      "A deterministic e2e article body gives the mobile cold-load route enough detail content.",
    source: {
      source_name: "Example Wire",
      source_domain: "example.com",
      trust_tier: "tier_1",
      source_role: "wire",
    },
    token_lanes: [{ lane: "resolved", symbol: "UPEG", target_type: "Asset", target_id: TARGET_ID }],
    fact_lanes: [{ lane: "accepted", summary: "Funding stress remains elevated." }],
    token_mentions: [],
    fact_candidates: [],
    story_members: [],
    agent_brief: {
      status: "ready",
      summary_zh: "流动性轮动正在影响高 beta crypto。",
      key_points: ["Funding stress elevated", "Crypto beta in focus"],
      data_gaps: [],
      evidence_refs: [],
      computed_at_ms: NOW,
    },
    agent_run: null,
  };
}

function equityEventRowsData() {
  return {
    items: [
      {
        company_event_id: "event-nvda-1",
        ticker: "NVDA",
        company_name: "NVIDIA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "official_issuer",
        latest_event_at_ms: NOW,
        lifecycle_status: "ready",
        headline: "NVDA Q3 earnings release",
        summary: "Revenue acceleration with cited official evidence.",
        documents_json: [{ event_document_id: "doc-nvda-1", document_type: "press_release" }],
        facts_json: [{ fact_candidate_id: "fact-nvda-1", metric_name: "revenue" }],
        brief_json: {
          status: "ready",
          direction: "bullish",
          decision_class: "driver",
          summary_zh: "收入增速和指引构成一线事件流。",
          event_read_zh: "官方材料显示收入重新加速。",
        },
      },
    ],
    next_cursor: null,
  };
}

function equityEventCalendarData() {
  return {
    items: [
      {
        expected_event_id: "expected-nvda-1",
        ticker: "NVDA",
        company_name: "NVIDIA",
        event_type: "earnings_release",
        priority: "P0",
        source_role: "calendar",
        fiscal_period: "Q3",
        expected_at_ms: NOW,
        status: "matched",
        headline: "NVDA Q3 earnings release matched",
        calendar_json: { observed_company_event_id: "event-nvda-1" },
      },
    ],
  };
}

function equityEventSummaryData() {
  return {
    p0_open_count: 1,
    today_count: 1,
    brief_pending_count: 0,
    latest_event_at_ms: NOW,
  };
}

function equityEventDetailData(path: string) {
  const eventId = decodeURIComponent(path.split("/").pop() ?? "event-nvda-1");
  return {
    company_event_id: eventId,
    ticker: "NVDA",
    company_name: "NVIDIA",
    event_type: "earnings_release",
    priority: "P0",
    source_role: "official_issuer",
    latest_event_at_ms: NOW,
    headline: "NVDA Q3 earnings release",
    documents_json: [
      {
        event_document_id: "doc-nvda-1",
        document_type: "press_release",
        document_url: "https://example.com/nvda",
      },
    ],
    facts_json: [
      {
        fact_candidate_id: "fact-nvda-1",
        metric_name: "revenue",
        value_numeric: 35000,
        value_unit: "USD millions",
        validation_status: "accepted",
      },
    ],
    spans_json: [{ span_id: "span-nvda-1", evidence_quote: "Revenue increased year over year." }],
    story_json: {
      story_id: "story-nvda",
      representative_headline: "AI capex earnings cluster",
      event_count: 2,
    },
    brief_json: {
      status: "ready",
      direction: "bullish",
      decision_class: "driver",
      summary_zh: "收入增速和指引构成一线事件流。",
      event_read_zh: "官方材料显示收入重新加速。",
      evidence_refs: ["fact:fact-nvda-1"],
    },
  };
}

async function fulfill(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ok: true, data }),
  });
}

async function fulfillTokenImage(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#121713"/><circle cx="20" cy="20" r="12" fill="#d99a28"/></svg>`,
  });
}

function statusData() {
  return {
    ok: true,
    reasons: [],
    handles: ["toly", "traderpow"],
    store: "postgresql",
    snapshot_gate: {},
    db: { ok: true },
    provider_states: {},
    workers: {
      collector: workerStatus({
        enabled: true,
        running: true,
        details: {
          started_at_ms: NOW - 120_000,
          frames_received: 88,
          twitter_events: 44,
          matched_twitter_events: 7,
          events_published: 7,
          duplicate_twitter_events: 0,
          duplicate_matched_twitter_events: 0,
          parse_errors: 0,
          last_frame_at_ms: NOW,
          last_event_at_ms: NOW,
          last_matched_event_at_ms: NOW,
        },
      }),
      enrichment: workerStatus({ enabled: true, running: true, queue_depth: 0 }),
      token_radar_projection: workerStatus({ enabled: true, running: true }),
      token_capture_tier: workerStatus({ enabled: true, running: true }),
      market_tick_stream: workerStatus({ enabled: false, running: false }),
      market_tick_poll: workerStatus({ enabled: true, running: true }),
      live_price_gateway: workerStatus({
        enabled: true,
        running: true,
        details: { configured: true },
      }),
      pulse_candidate: workerStatus(),
      handle_summary: workerStatus(),
      notification_rule: workerStatus({ enabled: true, running: true }),
      notification_delivery: workerStatus({ enabled: true, running: true, queue_depth: 0 }),
      asset_profile_refresh: workerStatus(),
      resolution_refresh: workerStatus(),
    },
  };
}

function workerStatus(overrides: Record<string, unknown> = {}) {
  return {
    enabled: false,
    running: false,
    last_started_at_ms: null,
    last_finished_at_ms: null,
    last_result: null,
    last_error: null,
    iteration_duration_p99_ms: null,
    queue_depth: null,
    pool_wait_ms_p99: null,
    details: {},
    ...overrides,
  };
}

function notificationSummary() {
  return {
    subscriber_key: "local",
    unread_count: 1,
    high_unread_count: 1,
    critical_unread_count: 0,
    highest_unread_severity: "high",
    account_unread_counts: { toly: 1 },
  };
}

function recentData() {
  return { scope: "all", events: [], items: [liveEvent()] };
}

function liveEvent() {
  return {
    type: "event",
    event: {
      event_id: "event-upeg-1",
      canonical_url: "https://x.com/traderpow/status/1",
      author_handle: "traderpow",
      received_at_ms: NOW,
      text_clean: "$UPEG watched account evidence",
      cashtags: ["UPEG"],
      is_watched: 1,
    },
    entities: [{ entity_type: "symbol", normalized_value: "UPEG", received_at_ms: NOW }],
    token_intents: [
      {
        intent_id: `intent:${TARGET_ID}`,
        event_id: "event-upeg-1",
        display_symbol: "UPEG",
        chain_hint: "eth",
        address_hint: ADDRESS,
        intent_status: "active",
        intent_confidence: 1,
      },
    ],
    token_resolutions: [
      {
        resolution_id: `resolution:${TARGET_ID}`,
        intent_id: `intent:${TARGET_ID}`,
        event_id: "event-upeg-1",
        target_type: "Asset",
        target_id: TARGET_ID,
        resolution_status: "EXACT",
        reason_codes_json: ["CHAIN_ADDRESS_EXACT"],
      },
    ],
    alerts: [],
  };
}

function tokenRadarData(url: URL) {
  const targets = shouldReturnLongMobileRadarList(url)
    ? Array.from({ length: 8 }, () => assetFlowRow())
    : [assetFlowRow()];
  return {
    window: url.searchParams.get("window") ?? "1h",
    scope: url.searchParams.get("scope") ?? "all",
    targets,
    attention: [],
    projection: {
      status: "fresh",
      version: "e2e-token-radar",
      source: "playwright",
      source_max_received_at_ms: NOW,
      computed_at_ms: NOW,
    },
  };
}

function shouldReturnLongMobileRadarList(url: URL) {
  return url.searchParams.get("window") === "24h" && url.searchParams.get("scope") === "matched";
}

function assetFlowRow() {
  const target = {
    target_type: "Asset",
    target_id: TARGET_ID,
    symbol: "UPEG",
    status: "candidate",
    chain_id: "eip155:1",
    token_standard: "erc20",
    address: ADDRESS,
    pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${ADDRESS.toLowerCase()}`,
  };
  const attention = {
    mentions_5m: 2,
    mentions_1h: 4,
    mentions_4h: 4,
    mentions_24h: 4,
    mentions_window: 4,
    unique_authors: 3,
    watched_mentions: 1,
    latest_seen_ms: NOW,
    previous_mentions: 0,
    mention_delta: 4,
    mention_delta_pct: null,
    z_score: null,
    new_burst_score: 80,
    stream_share: 0,
    baseline_status: "insufficient_history",
    baseline_sample_count: 0,
  };
  const market = marketContextFixture({
    event_anchor: marketObservationFixture({
      target_type: "Asset",
      target_id: TARGET_ID,
      source: "event_anchor",
      provider: "gmgn_dex_quote",
      price_usd: 0.001,
      market_cap_usd: 60_490,
      liquidity_usd: 250_000,
      observed_at_ms: NOW - 60_000,
      received_at_ms: NOW - 60_000,
    }),
    decision_latest: marketObservationFixture({
      target_type: "Asset",
      target_id: TARGET_ID,
      source: "decision_latest",
      provider: "okx_dex_price",
      price_usd: 0.00112,
      market_cap_usd: 66_000,
      liquidity_usd: 250_000,
      observed_at_ms: NOW,
      received_at_ms: NOW,
    }),
  });
  return {
    intent: {
      intent_id: `intent:${TARGET_ID}`,
      display_symbol: "UPEG",
      display_name: null,
      evidence: [],
    },
    target,
    attention,
    market,
    resolution: {
      status: "EXACT",
      resolution_status: "EXACT",
      target_type: "Asset",
      target_id: TARGET_ID,
      reason_codes: ["CHAIN_ADDRESS_EXACT"],
      candidate_ids: [TARGET_ID],
      lookup_keys: [],
    },
    factor_snapshot: factorSnapshot({ attention, market }),
    data_health: { identity: "EXACT", market: "ready", coverage: "public_stream" },
    source_event_ids: ["event-upeg-1", "event-upeg-2"],
  };
}

function factorSnapshot({ attention, market }: { attention: any; market: any }) {
  return {
    schema_version: "token_factor_snapshot_v3_social_attention",
    subject: {
      target_type: "Asset",
      target_id: TARGET_ID,
      symbol: "UPEG",
      chain: "eip155:1",
      address: ADDRESS,
      target_market_type: "dex",
    },
    market,
    gates: {
      eligible_for_high_alert: true,
      max_decision: "high_alert",
      blocked_reasons: [],
      risk_reasons: [],
    },
    data_health: { identity: "ready", market: "ready", social: "ready", alpha: "ready" },
    families: {
      social_heat: family(86, 0.35, {
        mentions_5m: attention.mentions_5m,
        mentions_1h: attention.mentions_1h,
        mentions_4h: attention.mentions_4h,
        mentions_24h: attention.mentions_24h,
        unique_authors: attention.unique_authors,
        watched_mentions: attention.watched_mentions,
        latest_seen_ms: attention.latest_seen_ms,
        previous_mentions: attention.previous_mentions,
        mention_delta: attention.mention_delta,
        mention_delta_pct: attention.mention_delta_pct,
        z_score: attention.z_score,
        new_burst_score: attention.new_burst_score,
        stream_share: attention.stream_share,
        baseline_status: attention.baseline_status,
        baseline_sample_count: attention.baseline_sample_count,
        status: "rising",
      }),
      social_propagation: family(72, 0.3, {
        mentions: attention.mentions_window,
        independent_authors: attention.unique_authors,
        duplicate_text_share: 0,
        informative_post_count: attention.mentions_window,
      }),
      semantic_catalyst: family(78, 0.25, {
        impact_mean: 0.78,
        novelty_mean: 0.7,
        confidence_mean: 0.9,
        direction_counts: { bullish: attention.mentions_window },
      }),
      timing_risk: family(50, 0.1, {
        social_signal_start_ms: NOW - 60_000,
        price_change_since_social_pct: 0.12,
        price_change_before_social_pct: null,
      }),
    },
    normalization: {
      status: "ready",
      cohort: { window: "1h" },
      factor_ranks: {},
      alpha_rank: 4,
      cohort_size: 80,
    },
    composite: {
      rank_score: 79,
      recommended_decision: "high_alert",
      family_scores: {
        social_heat: 86,
        social_propagation: 72,
        semantic_catalyst: 78,
        timing_risk: 50,
      },
    },
    provenance: { source_event_ids: ["event-upeg-1", "event-upeg-2"], computed_at_ms: NOW },
  };
}

function family(score: number, weight: number, facts: Record<string, unknown>) {
  return {
    raw_score: score,
    score,
    weight,
    facts,
    factors: {
      primary: {
        family: "e2e",
        key: "primary",
        raw_value: score,
        score,
        confidence: 0.95,
        data_health: "ready",
        source_refs: [],
        risk_flags: [],
      },
    },
    data_health: "ready",
  };
}

function tokenCaseData(url: URL) {
  const dossier = tokenCaseFixture();
  const targetType = url.searchParams.get("target_type") ?? dossier.target.target_type;
  const targetId = url.searchParams.get("target_id") ?? dossier.target.target_id;
  const window = url.searchParams.get("window") ?? dossier.timeline.query.window;
  const scope = url.searchParams.get("scope") ?? dossier.timeline.query.scope;
  return {
    ...dossier,
    target: { ...dossier.target, target_type: targetType, target_id: targetId },
    timeline: {
      ...dossier.timeline,
      query: {
        ...dossier.timeline.query,
        target_type: targetType,
        target_id: targetId,
        window,
        scope,
      },
    },
    posts: {
      ...dossier.posts,
      query: {
        ...dossier.posts.query,
        target_type: targetType,
        target_id: targetId,
        window,
        scope,
      },
    },
    market_live: {
      ...dossier.market_live,
      target_type: targetType,
      target_id: targetId,
    },
  };
}

function targetPostsData(url: URL) {
  const targetId = url.searchParams.get("target_id") ?? "";
  if (targetId.includes("FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump")) {
    return tokenCasePostsData(url);
  }
  return postsData();
}

function tokenCasePostsData(url: URL) {
  const posts = tokenCasePostsFixture();
  const cursor = url.searchParams.get("cursor");
  const targetType = url.searchParams.get("target_type") ?? posts.query.target_type;
  const targetId = url.searchParams.get("target_id") ?? posts.query.target_id;
  const window = url.searchParams.get("window") ?? posts.query.window;
  const scope = url.searchParams.get("scope") ?? posts.query.scope;
  const sort = url.searchParams.get("sort") ?? posts.query.sort ?? "recent";
  const nextItem = {
    ...posts.items[0],
    event_id: "event-hansa-4",
    tweet_id: "tweet-hansa-4",
    handle: "marketdesk",
    author_handle: "marketdesk",
    text: "Follow-up page adds fresh HANSA context after the first dossier page.",
    url: "https://x.com/marketdesk/status/event-hansa-4",
    is_watched: false,
    is_first_seen_by_watched_for_token: false,
  };
  const items = cursor ? [nextItem] : posts.items;
  return {
    ...posts,
    query: { ...posts.query, target_type: targetType, target_id: targetId, window, scope, sort },
    returned_count: items.length,
    total_count: posts.total_count + 1,
    has_more: false,
    next_cursor: null,
    items,
  };
}

function searchInspectData(url: URL) {
  const query = url.searchParams.get("q") ?? "";
  if (query.toLowerCase().includes("hansa")) {
    const dossier = tokenCaseData(url);
    return {
      query: {
        q: query,
        normalized_q: query.toLowerCase(),
        window: url.searchParams.get("window") ?? "24h",
        scope: url.searchParams.get("scope") ?? "all",
        result_kind: "token_result",
      },
      resolver: {
        confidence: 0.98,
        target_candidates: [dossier.target],
        selected_target: dossier.target,
        reasons: ["e2e_token_case_fixture"],
      },
      token_result: dossier,
      ambiguous_result: null,
      topic_result: null,
    };
  }
  return {
    query: {
      q: query,
      normalized_q: query.toLowerCase(),
      window: "24h",
      scope: "all",
      result_kind: "topic_result",
    },
    resolver: { confidence: 0.5, target_candidates: [], selected_target: null, reasons: ["e2e"] },
    token_result: null,
    ambiguous_result: null,
    topic_result: null,
  };
}

function signalPulseData(url: URL) {
  const item = pulseItem();
  return {
    query: {
      window: url.searchParams.get("window") ?? "1h",
      scope: url.searchParams.get("scope") ?? "all",
      status: url.searchParams.get("status") ?? "all",
      q: url.searchParams.get("q") ?? "",
    },
    health: { returned_count: 1 },
    summary: { trade_candidate: 1, token_watch: 0, risk_rejected_high_info: 0 },
    items: [item],
    returned_count: 1,
    has_more: false,
    next_cursor: null,
  };
}

function socialEventsByIds(url: URL) {
  const ids = (url.searchParams.get("ids") ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);
  const byId = new Map(postsData().items.map((item) => [item.event_id, sourceEvent(item)]));
  return {
    events: ids.map((id) => byId.get(id)).filter(Boolean),
    not_found: ids.filter((id) => !byId.has(id)),
  };
}

function pulseItem() {
  const row = assetFlowRow();
  return {
    candidate_id: "pulse-bnb",
    candidate_type: "token_target",
    subject_key: "BNB",
    target_type: "Asset",
    target_id: TARGET_ID,
    symbol: "BNB",
    window: "1h",
    scope: "all",
    evidence_status: "complete",
    decision_status: "trade_candidate",
    display_status: "display_trade_candidate",
    evidence_packet_hash: "sha256:e2e-pulse-bnb",
    verdict: "trade_candidate",
    social_phase: "ignition",
    candidate_score: 88,
    score_band: "trade",
    evidence_event_ids: ["event-upeg-1", "event-upeg-2"],
    source_event_ids: ["event-upeg-1", "event-upeg-2", "event-upeg-3"],
    factor_snapshot: {
      ...row.factor_snapshot,
      subject: { ...row.factor_snapshot.subject, symbol: "BNB" },
    },
    decision: {
      route: "meme",
      recommendation: "trade_candidate",
      confidence: 0.72,
      abstain_reason: null,
      stage_count: 3,
      summary_zh: "BNB social pulse is live for e2e.",
      narrative_archetype: "KOL 扩散",
      narrative_thesis_zh:
        "Watched-account seed followed by public amplification on $BNB; keep the thesis tied to fresh independent authors.",
      bull_view: {
        strength: "strong",
        thesis_zh:
          "Watched-account seed and public amplification align within the same pulse window.",
        supporting_event_ids: ["event-upeg-1"],
      },
      bear_view: {
        strength: "weak",
        thesis_zh:
          "Thin liquidity can unwind the setup if independent authors stop adding confirmation.",
        supporting_event_ids: ["event-upeg-2"],
      },
      playbook: {
        has_playbook: true,
        monitoring_horizon: "30m",
        watch_signals: [
          "Independent author count keeps rising",
          "GMGN liquidity holds above guardrail",
        ],
        exit_triggers: ["No fresh independent authors", "Liquidity drops below guardrail"],
      },
      evidence_event_urls: {
        "event-upeg-1": "https://x.com/upeg/status/1",
        "event-upeg-2": "https://x.com/upeg/status/2",
      },
      invalidation_conditions: [],
      residual_risks: [],
      evidence_event_ids: ["event-upeg-1", "event-upeg-2"],
      supporting_evidence_refs: ["event:event-upeg-1", "market:bnb-latest"],
      risk_evidence_refs: ["event:event-upeg-2"],
      data_gap_refs: [],
    },
    gate: {
      candidate_score: 88,
      score_band: "trade",
      blocked_reasons: [],
    },
    fact_card: {
      market_cap_usd: 66_000,
      liquidity_usd: 250_000,
      mentions_1h: 4,
      unique_authors: 3,
    },
    stages: {
      evidence_pack: null,
      evidence_completeness_gate: {
        stage: "evidence_completeness_gate",
        route: "meme",
        status: "ok",
        model: "deterministic",
        started_at_ms: NOW - 1_060,
        finished_at_ms: NOW - 1_060,
        attempt_index: 0,
        latency_ms: 0,
        response: {
          evidence_status: "complete",
          hard_blocked: false,
        },
        error: null,
      },
      signal_analyst: {
        stage: "signal_analyst",
        route: "meme",
        status: "ok",
        model: "gpt-5.2",
        started_at_ms: NOW - 1_050,
        finished_at_ms: NOW - 360,
        attempt_index: 0,
        latency_ms: 690,
        response: {
          what_changed_zh:
            "Sealed evidence packet supports watched-account seed plus independent amplification; risk evidence remains thin liquidity.",
          supporting_claims: [
            {
              claim_zh:
                "Watched-account seed and public amplification align within the same pulse window.",
              evidence_refs: ["event:event-upeg-1"],
            },
          ],
          risk_claims: [
            {
              claim_zh:
                "Thin liquidity can unwind the setup if independent authors stop adding confirmation.",
              evidence_refs: ["event:event-upeg-2", "market:bnb-latest"],
            },
          ],
          data_gaps: [],
        },
        error: null,
      },
      bear_case: {
        stage: "bear_case",
        route: "meme",
        status: "ok",
        model: "gpt-5.2",
        started_at_ms: NOW - 350,
        finished_at_ms: NOW - 180,
        attempt_index: 0,
        latency_ms: 170,
        response: {
          risk_claims: [
            {
              claim:
                "Thin liquidity can unwind the setup if independent authors stop adding confirmation.",
              evidence_refs: ["event:event-upeg-2", "market:bnb-latest"],
              stance: "risk",
            },
          ],
          confidence_ceiling: 0.78,
        },
        error: null,
      },
      risk_portfolio_judge: {
        stage: "risk_portfolio_judge",
        route: "meme",
        status: "ok",
        model: "gpt-5.2",
        started_at_ms: NOW - 170,
        finished_at_ms: NOW,
        attempt_index: 0,
        latency_ms: 170,
        response: {
          route: "meme",
          recommendation: "trade_candidate",
          confidence: 0.72,
          summary_zh: "Accept as trade candidate with liquidity risk noted.",
          residual_risks: ["Low-liquidity reversal."],
          invalidation_conditions: ["No fresh independent authors."],
          supporting_evidence_refs: ["event:event-upeg-1", "market:bnb-latest"],
          risk_evidence_refs: ["event:event-upeg-2"],
          data_gap_refs: [],
        },
        error: null,
      },
      claim_verifier: null,
      recommendation_clipper: null,
      deterministic_eval: null,
      write_gate: null,
    },
    agent_run_id: "run-pulse-bnb",
    pulse_version: "pulse-v1",
    gate_version: "gate-v1",
    prompt_version: "prompt-v1",
    schema_version: "signal-pulse-v1",
    created_at_ms: NOW,
    updated_at_ms: NOW,
    playbooks: [],
  };
}

function sourceEvent(item: ReturnType<typeof post>) {
  return {
    event_id: item.event_id,
    timestamp_ms: item.received_at_ms,
    source_provider: "gmgn",
    channel: "twitter_monitor_basic",
    action: item.reference?.type ?? "tweet",
    author_handle: item.author_handle,
    author_name: item.author_handle,
    author_followers: item.post_quality.score >= 80 ? 168_905 : 220,
    author_watched: item.is_watched,
    text_clean: item.text,
    canonical_url: item.url,
  };
}

function timelineData() {
  const posts = postsData().items.map((item, index) => ({
    ...item,
    bucket_start_ms: index < 2 ? NOW - 300_000 : NOW,
  }));
  return {
    query: { target_type: "Asset", target_id: TARGET_ID, window: "1h", scope: "all", bucket: "5m" },
    summary: {
      posts: 3,
      authors: 2,
      effective_authors: 1.8,
      first_seen_ms: NOW - 300_000,
      latest_seen_ms: NOW,
      watched_posts: 1,
      phase: "expansion",
      top_author_share: 0.5,
      duplicate_text_share: 0,
      peak_posts_per_bucket: 2,
      peak_new_authors_per_bucket: 1,
      reproduction_rate: 1.5,
    },
    buckets: [
      {
        start_ms: NOW - 300_000,
        end_ms: NOW - 60_000,
        posts: 2,
        authors: 1,
        new_authors: 1,
        watched_posts: 1,
        duplicate_text_share: 0,
        price: {
          status: "ready",
          provider: "okx_dex_price",
          pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${ADDRESS.toLowerCase()}`,
          price_usd: 0.00112,
          observed_at_ms: NOW - 60_000,
        },
        price_change_from_start_pct: 0.12,
      },
      {
        start_ms: NOW - 60_000,
        end_ms: NOW,
        posts: 1,
        authors: 1,
        new_authors: 1,
        watched_posts: 0,
        duplicate_text_share: 0,
        price: {
          status: "ready",
          provider: "okx_dex_price",
          pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${ADDRESS.toLowerCase()}`,
          price_usd: 0.00114,
          observed_at_ms: NOW,
        },
        price_change_from_start_pct: 0.14,
      },
    ],
    market_candles: {
      target_type: "Asset",
      target_id: TARGET_ID,
      chain_id: "eip155:1",
      address: ADDRESS,
      symbol: "UPEG",
      pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${ADDRESS.toLowerCase()}`,
    },
    stages: [
      {
        stage_id: "seed:1777746000000:1",
        phase: "seed",
        start_ms: NOW - 300_000,
        end_ms: NOW - 300_000,
        duration_ms: 0,
        trigger_reason: "first_token_evidence",
        confidence: 0.61,
        people: {
          posts: 1,
          authors: 1,
          new_authors: 1,
          watched_posts: 1,
          watched_authors: 1,
          top_author_share: 1,
        },
        representative_event_ids: ["event-upeg-1"],
        price: {
          status: "ready",
          start_price: 0.001,
          end_price: 0.00112,
          delta_pct: 0.12,
          observation_ids: ["observation-upeg-1"],
          max_observation_lag_ms: 60_000,
        },
        risks: [],
      },
    ],
    authors: [
      {
        handle: "traderpow",
        first_seen_ms: NOW - 300_000,
        latest_seen_ms: NOW - 300_000,
        posts: 1,
        followers: 168_905,
        role: "watched",
        quality_score: 86,
      },
      {
        handle: "alien19710628",
        first_seen_ms: NOW - 60_000,
        latest_seen_ms: NOW,
        posts: 2,
        followers: 220,
        role: "amplifier",
        quality_score: 74,
      },
    ],
    posts,
    cascade: {
      edges: [
        {
          event_id: "event-upeg-2",
          parent_event_id: "event-upeg-1",
          parent_tweet_id: "tweet-upeg-1",
          edge_type: "quote",
          parent_author_handle: "traderpow",
          resolved: true,
        },
      ],
      unresolved_parents: [],
    },
    returned_count: posts.length,
    has_more: false,
    next_cursor: null,
  };
}

function postsData() {
  return {
    items: [
      post("event-upeg-1", "traderpow", "$UPEG watched account evidence", true, 86),
      post("event-upeg-2", "alien19710628", "$UPEG public follow-through", false, 74),
      post("event-upeg-3", "alien19710628", "$UPEG another public post", false, 68),
    ],
    returned_count: 3,
    total_count: 3,
    has_more: false,
    next_cursor: null,
    score_window: { window: "1h" },
    query: {
      target_type: "Asset",
      target_id: TARGET_ID,
      window: "1h",
      scope: "all",
      range: "current_window",
      sort: "recent",
    },
  };
}

function post(eventId: string, handle: string, text: string, watched: boolean, score: number) {
  const phase = eventId.endsWith("-1") ? "seed" : "ignition";
  return {
    event_id: eventId,
    tweet_id: eventId.replace("event", "tweet"),
    handle,
    author_handle: handle,
    received_at_ms: NOW,
    text,
    url: `https://x.com/${handle}/status/${eventId}`,
    mention_source: "gmgn_token_payload",
    target_type: "Asset",
    target_id: TARGET_ID,
    attribution_status: "direct",
    attribution_confidence: 1,
    attribution_weight: 1,
    is_watched: watched,
    is_first_seen_by_watched_for_token: watched,
    event_type: watched ? "watched_token_call" : "public_followup",
    reference:
      eventId === "event-upeg-2"
        ? { tweet_id: "tweet-upeg-1", author_handle: "traderpow", type: "quote" }
        : null,
    catalyst_score: score,
    catalyst_components: {
      followup_count: watched ? 0 : 2,
      independent_authors: watched ? 1 : 2,
      explicit_cascade_followups: watched ? 0 : 1,
    },
    price: {
      status: "ready",
      provider: "okx_dex_price",
      pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${ADDRESS.toLowerCase()}`,
      price_usd: 0.00112,
      observed_at_ms: NOW,
    },
    stage_id: phase === "seed" ? "seed:1777746000000:1" : "ignition:1777746240000:1",
    stage_phase: phase,
    author_role: watched ? "watched" : "early_amplifier",
    is_stage_representative: watched,
    price_delta_from_previous_post_pct: null,
    post_quality: {
      score_version: "post_quality_v1",
      score,
      reasons: ["structured_token_payload"],
      risks: [],
      contributions: [
        { feature: "source_specificity", value: 18, reason: "structured_token_payload" },
      ],
      risk_caps: [],
    },
  };
}

function accountQualityData() {
  return { query: { handles: ["traderpow"] }, accounts: [] };
}

function notificationsData() {
  return {
    items: [
      {
        notification_id: "notification-1",
        dedup_key: "pulse-bnb",
        rule_id: "pulse_trade_candidate",
        severity: "high",
        title: "BNB pulse",
        body: "BNB is now a trade candidate",
        entity_type: "pulse_candidate",
        entity_key: "pulse-bnb",
        author_handle: null,
        symbol: "BNB",
        chain: "bnb",
        address: null,
        event_id: null,
        source_table: "pulse_candidates",
        source_id: "pulse-bnb",
        occurrence_count: 1,
        first_seen_at_ms: NOW,
        last_seen_at_ms: NOW,
        created_at_ms: NOW,
        updated_at_ms: NOW,
        read_at_ms: null,
        payload: { candidate_id: "pulse-bnb" },
        channels: ["in_app"],
      },
    ],
    summary: notificationSummary(),
  };
}

function stocksRadarData(url: URL) {
  return {
    window: url.searchParams.get("window") ?? "1h",
    scope: url.searchParams.get("scope") ?? "all",
    query: {
      window: "1h",
      scope: "all",
      limit: 48,
      window_start_ms: NOW - 3_600_000,
      window_end_ms: NOW,
    },
    rows: [
      {
        target: {
          target_type: "MarketInstrument",
          target_id: "market_instrument:us_equity:AAPL",
          symbol: "AAPL",
          market: "us_equity",
          exchange: "NASDAQ",
          instrument_type: "equity",
          name: "Apple Inc.",
        },
        attention: { mentions: 3, unique_authors: 2, watched_mentions: 1, latest_seen_ms: NOW },
        latest_event: {
          event_id: "event-aapl",
          author_handle: "toly",
          text: "$AAPL breakout",
          received_at_ms: NOW,
        },
        quote: {
          status: "ready",
          price: 291.87,
          reference_close_price: 293.25,
          change_pct: -0.004,
          asof: "2026-05-12T08:45:45+00:00",
          provider: "yahoo",
          provider_symbol: "AAPL",
          latency_class: "delayed_15m",
          freshness_class: "delayed_15m",
          error: null,
        },
        source_event_ids: ["event-aapl"],
        row_health: [],
      },
    ],
    health: { returned_count: 1, quote_ready_count: 1, quote_unavailable_count: 0 },
  };
}

function handleFromPath(path: string) {
  const parts = path.split("/");
  const handleIndex = parts.includes("handle")
    ? parts.indexOf("handle") + 1
    : parts.indexOf("handles") + 1;
  return decodeURIComponent(parts[handleIndex] ?? "toly");
}

function watchlistOverviewData() {
  return {
    window: "7d",
    items: [
      {
        handle: "toly",
        last_source_event_at_ms: NOW,
        recent_source_event_count: 3,
        recent_signal_event_count: 2,
        total_signal_event_count: 5,
        summary_status: "ready",
        summary_is_stale: false,
      },
      {
        handle: "marionawfal",
        last_source_event_at_ms: NOW - 60_000,
        recent_source_event_count: 42,
        recent_signal_event_count: 12,
        total_signal_event_count: 42,
        summary_status: "ready",
        summary_is_stale: false,
      },
    ],
  };
}

function watchlistHandleOverviewData(handle: string) {
  return {
    query: { handle, scope: "signal", window: "7d" },
    metrics: {
      source_event_count: 42,
      signal_event_count: 12,
      resolved_token_count: 1,
      candidate_mention_count: 3,
      narrative_count: 1,
      last_source_event_at_ms: NOW,
    },
    resolved_token_clusters: [
      {
        label: "$UPEG",
        count: 4,
        query: "$UPEG",
        kind: "resolved_token",
        source: "token_resolutions",
        target_type: "Asset",
        target_id: TARGET_ID,
      },
    ],
    candidate_mention_clusters: [
      {
        label: "$ALOY",
        count: 3,
        query: "$ALOY",
        kind: "candidate_mention",
        source: "social_event_candidates",
      },
    ],
    narrative_clusters: [
      { label: "Liquidity rotation", count: 2, query: "liquidity", kind: "narrative" },
    ],
    risk_notes: [],
  };
}

function watchlistHandleSummaryData(handle: string) {
  return {
    handle,
    status: "ready",
    generated_at_ms: NOW,
    staleness_ms: 0,
    is_stale: false,
    pending_recompute: false,
    signal_count: 12,
    input_event_count: 42,
    signal_count_at_generation: 12,
    model: "e2e-model",
    summary_zh: `${handle} has fresh deterministic watchlist context.`,
    topics: [
      {
        title: "UPEG",
        description: "UPEG is repeatedly mentioned by watched and public accounts.",
        event_count: 4,
        top_event_ids: ["event-upeg-1"],
        symbols: ["UPEG"],
        confidence: 0.86,
      },
    ],
  };
}

function watchlistHandleTimelineData(handle: string) {
  return {
    query: { handle, scope: "signal", limit: 80 },
    items: postsData().items.map((item) => ({
      event_id: item.event_id,
      received_at_ms: item.received_at_ms,
      author_handle: handle,
      action: "tweet",
      text_clean: item.text,
      canonical_url: item.url,
      cashtags: ["UPEG"],
      hashtags: [],
      mentions: [],
      social_event: {
        is_signal_event: true,
        summary_zh: item.text,
        confidence: 0.82,
        token_candidates: [{ symbol: "UPEG", target_id: TARGET_ID }],
      },
    })),
    has_more: false,
    next_cursor: null,
  };
}

function macroData() {
  return {
    snapshot: {
      snapshot_id: "macro-view:macro_regime_v4:e2e",
      projection_version: "macro_regime_v4",
      asof_date: "2026-05-20",
      status: "partial",
      regime: "funding_stress",
      overall_score: 7.25,
      computed_at_ms: NOW,
    },
    panels: {
      liquidity: {
        score: 9,
        regime: "funding_stress",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
      rates: {
        score: 7,
        regime: "term_premium_pressure",
        evidence: ["10y=4.70"],
        data_gaps: [],
      },
    },
    indicators: {
      sofr_iorb_spread_bps: {
        label: "SOFR minus IORB",
        value: 15,
        unit: "bps",
        observed_at: "2026-05-20",
        sources: ["nyfed", "fred"],
        concept_keys: ["liquidity:sofr", "fed:iorb"],
      },
    },
    triggers: [{ code: "sofr_above_iorb", description: "SOFR is above IORB", value: 15 }],
    data_gaps: [
      {
        code: "missing_required_concept",
        label: "标普500 数据缺失",
        severity: "warning",
        score_participation: false,
      },
    ],
    source_coverage: {
      observed_concept_count: 10,
      required_concept_count: 10,
      coverage_ratio: 1,
      latest_observed_at: "2026-05-20",
    },
    features: {
      "rates:dgs10": {
        latest: { value: 4.7, observed_at: "2026-05-20", unit: "percent" },
        freshness_days: 1,
        delta: { "5d": 0.1, "20d": 0.35, "60d": null },
        zscore: { lookback: 252, value: 1.4 },
        percentile: { lookback: 252, value: 0.82 },
        data_gaps: [],
      },
    },
    chain: {
      liquidity: {
        score: 8,
        regime: "funding_stress",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
      fed_corridor: {
        score: 7,
        regime: "corridor_pressure",
        evidence: ["sofr_iorb_spread_bps=15.0"],
        data_gaps: [],
      },
    },
    scenario: {
      current_regime: "funding_stress",
      confidence: 0.72,
      time_window: "1w",
      confirmations: [
        {
          code: "sofr_above_iorb",
          description: "SOFR is above IORB",
          indicator_keys: ["sofr_iorb_spread_bps"],
          value: 15,
        },
      ],
      contradictions: [{ code: "volatility_carry", node: "volatility" }],
      watch_triggers: [
        {
          code: "repo_pressure_persists_3d",
          description: "SOFR remains above IORB across multiple observations.",
        },
      ],
      invalidations: [
        {
          code: "sofr_iorb_normalizes",
          description: "SOFR trades back below or in line with IORB.",
        },
      ],
      trade_map: [
        {
          expression: "risk_down_credit_sensitive",
          time_window: "1w",
          confirms_on: ["sofr_above_iorb"],
          invalidates_on: ["sofr_iorb_normalizes"],
        },
      ],
    },
    scorecard: {
      projection_version: "macro_regime_v4",
      modules: {
        liquidity: { score: 9, regime: "funding_stress", evidence: [], data_gaps: [] },
      },
    },
  };
}

function macroModuleIdFromPath(path: string) {
  return decodeURIComponent(path.replace("/api/macro/modules/", "")) || "overview";
}

function isParentMacroModule(moduleId: string) {
  return new Set(["assets", "rates", "fed", "liquidity", "economy", "volatility", "credit"]).has(
    moduleId,
  );
}

function macroModuleData(moduleId: string) {
  if (moduleId === "overview") {
    return macroOverviewModuleFixture();
  }
  const base = macroModuleFixture();
  return macroModuleFixture({
    snapshot: {
      ...base.snapshot,
      module_id: moduleId,
      route_path: moduleId === "overview" ? "/macro" : `/macro/${moduleId}`,
      section: moduleId.split("/")[0] || "overview",
      title: moduleId === "overview" ? "总览" : base.snapshot.title,
    },
  });
}

function macroSeriesData(url: URL) {
  const conceptKeys = (url.searchParams.get("concept_keys") ?? "asset:spx")
    .split(",")
    .map((conceptKey) => conceptKey.trim())
    .filter(Boolean);
  return macroSeriesFixture(conceptKeys.length > 0 ? conceptKeys : ["asset:spx"]);
}

function macroCorrelationData(url: URL) {
  const fixture = macroCorrelationFixture();
  const requestedWindow = url.searchParams.get("window");
  if (requestedWindow === "20d" || requestedWindow === "60d" || requestedWindow === "120d") {
    return { ...fixture, window: requestedWindow };
  }
  return fixture;
}

function opsDiagnosticsData() {
  return {
    schema_version: "ops_diagnostics_v1",
    generated_at_ms: NOW,
    overall: { status: "ok", severity: "info", reasons: [], section_status_counts: { ok: 4 } },
    config: { status: "ok", config_path: "~/.gmgn-twitter-intel/config.yaml" },
    database: { status: "ok", latency_ms: 4 },
    collector: { status: "ok", frames_received: 88, matched_twitter_events: 7 },
    providers: [
      {
        provider: "gmgn",
        domain: "social",
        configured: true,
        capabilities: ["websocket"],
        state: "connected",
        status: "ok",
        reason: null,
      },
    ],
    workers: [
      {
        name: "collector",
        group: "ingest",
        enabled: true,
        running: true,
        queue_depth: 0,
        status: "ok",
        reason: null,
      },
    ],
    queues: [
      {
        queue_name: "asset_profile_refresh",
        table: "asset_profile_refresh_jobs",
        worker_name: "asset_profile_refresh",
        counts_by_status: { due: 0, running: 0, failed: 0, dead: 0 },
        due_count: 0,
        running_count: 0,
        failed_count: 0,
        dead_count: 0,
        status: "ok",
        reason: null,
      },
    ],
    agent_execution: { status: "ok", lanes: {} },
    domains: { token_intel: { status: "ok", reason: "ready", due_jobs: 0 } },
    suggested_checks: [],
  };
}

function opsQueueData(path: string) {
  const queueName = decodeURIComponent(path.split("/").pop() ?? "asset_profile_refresh");
  const summary = {
    queue_name: queueName,
    table: `${queueName}_jobs`,
    worker_name: queueName,
    counts_by_status: { due: 1, running: 0, failed: 0, dead: 0 },
    due_count: 1,
    running_count: 0,
    failed_count: 0,
    dead_count: 0,
    oldest_due_age_ms: 12_000,
    status: "ok",
    reason: null,
  };
  return {
    schema_version: "ops_queue_v1",
    queue_name: queueName,
    status_filter: null,
    counts_by_status: summary.counts_by_status,
    summary,
    items: [
      {
        id: "job-e2e-1",
        status: "due",
        attempt_count: 0,
        max_attempts: 3,
        created_at_ms: NOW - 60_000,
        updated_at_ms: NOW - 30_000,
        next_run_at_ms: NOW,
        last_error_type: null,
        last_error_preview: null,
        source: { target_id: TARGET_ID },
      },
    ],
  };
}
