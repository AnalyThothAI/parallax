import type {
  AssetFlowData,
  NotificationItem,
  NotificationSummary,
  RecentData,
  SearchInspectData,
  StatusData,
  TokenPostsData,
  TokenSocialTimelineData,
} from "@lib/types";

const NOW = 1_777_770_000_000;

export function appStatusFixture(overrides: Partial<StatusData> = {}): StatusData {
  return {
    ok: true,
    reasons: [],
    handles: ["toly", "traderpow"],
    store: "postgresql",
    snapshot_gate: {},
    db: { ok: true },
    provider_states: {},
    agent_execution: null,
    news_provider_contract: { ok: true },
    workers: {
      collector: workerStatusFixture({
        enabled: true,
        running: true,
      }),
      token_radar_projection: workerStatusFixture({
        enabled: true,
        running: true,
        last_started_at_ms: NOW,
        last_finished_at_ms: NOW,
        last_result: {
          processed: 0,
          failed: 0,
          dead: 0,
          skipped: 0,
          notes: { rows_written: 0, source_rows: 0 },
        },
      }),
      market_tick_stream: workerStatusFixture({ enabled: false, running: false }),
      market_tick_poll: workerStatusFixture({
        enabled: true,
        running: true,
        last_started_at_ms: NOW,
      }),
      notification_rule: workerStatusFixture({ enabled: true, running: true }),
      notification_delivery: workerStatusFixture({ enabled: true, running: true }),
      asset_profile_refresh: workerStatusFixture(),
      resolution_refresh: workerStatusFixture(),
    },
    ...overrides,
  };
}

function workerStatusFixture(overrides: Partial<StatusData["workers"]["collector"]> = {}) {
  const enabled = overrides.enabled ?? false;
  const running = overrides.running ?? false;
  return {
    enabled,
    running,
    effective_status:
      overrides.effective_status ?? (!enabled ? "disabled" : running ? "running" : "stopped"),
    unavailable_reason: null,
    last_started_at_ms: null,
    last_finished_at_ms: null,
    last_result: null,
    last_error: null,
    iteration_duration_p99_ms: null,
    ...overrides,
  };
}

export function notificationSummaryFixture(
  overrides: Partial<NotificationSummary> = {},
): NotificationSummary {
  return {
    subscriber_key: "local",
    unread_count: 0,
    high_unread_count: 0,
    critical_unread_count: 0,
    highest_unread_severity: null,
    account_unread_counts: {},
    ...overrides,
  };
}

export function recentReplayFixture(overrides: Partial<RecentData> = {}): RecentData {
  return {
    scope: "all",
    events: [],
    items: [],
    ...overrides,
  };
}

export function tokenRadarFixture(overrides: Partial<AssetFlowData> = {}): AssetFlowData {
  return {
    window: "1h",
    scope: "all",
    venue: "all",
    targets: [],
    attention: [],
    projection: {
      status: "fresh",
      version: "token-radar-route-fixture",
      source: "token_radar_current_rows",
      venue: "all",
      reason: null,
      latest_attempt_status: "ready",
      row_count: 0,
      source_rows: 0,
      source_max_received_at_ms: 0,
      source_frontier_ms: null,
      computed_at_ms: NOW,
      error: null,
      anchor_coverage: { status: "fresh", ready: 0, missing: 0, total: 0 },
      quality_status: "ready",
      degraded_reasons: [],
      unresolved: {
        identity_missing_count: 0,
        nil_count: 0,
        ambiguous_count: 0,
        sample_symbols: [],
      },
    },
    ...overrides,
  };
}

export function searchInspectFixture(
  overrides: Partial<SearchInspectData> = {},
): SearchInspectData {
  return {
    query: {
      q: "$RKC",
      normalized_q: "rkc",
      window: "24h",
      scope: "all",
      result_kind: "empty_result",
    },
    resolver: {
      confidence: 0,
      target_candidates: [],
      selected_target: null,
      reasons: ["route_fixture_empty"],
    },
    token_result: null,
    topic_result: null,
    ambiguous_result: null,
    ...overrides,
  };
}

export function targetSocialTimelineFixture(
  overrides: Partial<TokenSocialTimelineData> = {},
): TokenSocialTimelineData {
  return {
    query: { window: "1h", scope: "all", bucket: "5m" },
    summary: {
      posts: 0,
      authors: 0,
      effective_authors: 0,
      watched_posts: 0,
      phase: "seed",
      top_author_share: 0,
      latest_seen_ms: null,
    },
    market_candles: {
      price_series_type: "anchor_line",
      candle_status: "missing_market_id",
      candle_bar: "1H",
    },
    stages: [],
    buckets: [],
    authors: [],
    posts: [],
    cascade: { edges: [], unresolved_parents: [] },
    ...overrides,
  } as TokenSocialTimelineData;
}

export function targetPostsFixture(overrides: Partial<TokenPostsData> = {}): TokenPostsData {
  return {
    items: [],
    returned_count: 0,
    total_count: 0,
    has_more: false,
    score_window: { window: "1h" },
    query: { sort: "recent" },
    ...overrides,
  } as TokenPostsData;
}

export function notificationFixture(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    notification_id: "notification-route-1",
    dedup_key: "route:notification:1",
    rule_id: "watched_account_token_alert",
    severity: "high",
    title: "Watched token alert",
    body: "$RKC was mentioned by a watched account",
    entity_type: "token",
    entity_key: "token:rkc",
    author_handle: "traderpow",
    symbol: "RKC",
    chain: null,
    address: null,
    event_id: null,
    source_table: "events",
    source_id: "event:rkc",
    occurrence_count: 1,
    first_seen_at_ms: NOW,
    last_seen_at_ms: NOW,
    created_at_ms: NOW,
    updated_at_ms: NOW,
    read_at_ms: null,
    payload: { event_id: "event:rkc" },
    channels: ["in_app"],
    ...overrides,
  };
}
