import type { Page, Route } from "@playwright/test";

import { marketContextFixture, marketObservationFixture } from "../../src/test/marketFixtures";

const NOW = 1_777_746_300_000;
const ADDRESS = "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
const TARGET_ID = `asset:dex:eth:${ADDRESS.toLowerCase()}`;

export async function installMockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

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
    if (path === "/api/search/inspect")
      return fulfill(route, searchInspectData(url.searchParams.get("q") ?? ""));
    if (path === "/api/signal-lab/pulse") return fulfill(route, signalPulseData(url));
    if (path.startsWith("/api/signal-lab/pulse/")) return fulfill(route, pulseItem());
    if (path === "/api/target-social-timeline") return fulfill(route, timelineData());
    if (path === "/api/target-posts") return fulfill(route, postsData());
    if (path === "/api/account-quality") return fulfill(route, accountQualityData());
    if (path === "/api/notification-summary") return fulfill(route, notificationSummary());
    if (path === "/api/notifications") return fulfill(route, notificationsData());
    if (path.endsWith("/read"))
      return fulfill(route, { notification_id: "notification-1", updated: true });
    if (path === "/api/notifications/read-all") return fulfill(route, { updated: true });
    if (path === "/api/stocks-radar") return fulfill(route, stocksRadarData(url));

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, error: `unhandled ${path}` }),
    });
  });
}

async function fulfill(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ok: true, data }),
  });
}

function statusData() {
  return {
    ok: true,
    reasons: [],
    handles: ["toly", "traderpow"],
    store: "postgresql",
    collector: {
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
    enrichment: { llm_configured: true, worker_running: true, job_counts: {} },
    token_radar_projection: { worker_running: true },
    anchor_price: { worker_running: true },
    live_price_gateway: { configured: true, worker_running: true },
    notifications: { enabled: true, worker_running: true, summary: notificationSummary() },
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
  return {
    window: url.searchParams.get("window") ?? "1h",
    scope: url.searchParams.get("scope") ?? "all",
    targets: [assetFlowRow()],
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
    factor_snapshot: factorSnapshot({ target, attention, market }),
    data_health: { identity: "EXACT", market: "ready", coverage: "public_stream" },
    source_event_ids: ["event-upeg-1", "event-upeg-2"],
  };
}

function factorSnapshot({
  target,
  attention,
  market,
}: {
  target: any;
  attention: any;
  market: any;
}) {
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

function searchInspectData(query: string) {
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
    summary: { trade_candidate: 1, token_watch: 0, theme_watch: 0, risk_rejected_high_info: 0 },
    items: [item],
    returned_count: 1,
    has_more: false,
    next_cursor: null,
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
    pulse_status: "trade_candidate",
    verdict: "trade_candidate",
    social_phase: "ignition",
    narrative_type: "direct_token",
    candidate_score: 88,
    score_band: "trade",
    evidence_event_ids: ["event-upeg-1"],
    source_event_ids: ["event-upeg-1"],
    factor_snapshot: {
      ...row.factor_snapshot,
      subject: { ...row.factor_snapshot.subject, symbol: "BNB" },
    },
    agent_recommendation: {
      schema_version: "pulse_recommendation_v1",
      recommendation: "trade_candidate",
      summary_zh: "BNB social pulse is live for e2e.",
      primary_reasons: [],
      upgrade_conditions: [],
      invalidation_conditions: [],
      residual_risks: [],
    },
    gate: {
      pulse_status: "trade_candidate",
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
    agent_run_id: null,
    created_at_ms: NOW,
    updated_at_ms: NOW,
    playbooks: [],
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
    market_overlay: {
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
