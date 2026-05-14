import type { AssetFlowData, RecentData, SignalPulseData, StatusData } from "@lib/types";

const NOW = 1_777_770_000_000;

export function appStatusFixture(overrides: Partial<StatusData> = {}): StatusData {
  return {
    ok: true,
    reasons: [],
    handles: ["toly", "traderpow"],
    store: "postgresql",
    collector: {
      started_at_ms: NOW,
      frames_received: 88,
      twitter_events: 44,
      matched_twitter_events: 7,
      events_published: 7,
      duplicate_twitter_events: 2,
      duplicate_matched_twitter_events: 0,
      parse_errors: 0,
      last_frame_at_ms: NOW,
      last_event_at_ms: NOW,
      last_matched_event_at_ms: NOW,
    },
    enrichment: {
      llm_configured: true,
      worker_running: true,
      job_counts: { pending: 0, running: 0, failed: 0, dead: 0, done: 8 },
    },
    token_radar_projection: {
      worker_running: true,
      last_started_at_ms: NOW,
      last_run_at_ms: NOW,
      last_result: { rows_written: 0, source_rows: 0 },
    },
    anchor_price: {
      worker_running: true,
      last_started_at_ms: NOW,
      last_run_at_ms: NOW,
      last_result: { anchor_observations_written: 0 },
    },
    live_price_gateway: {
      configured: true,
      worker_running: true,
      subscription_limit: 200,
      last_started_at_ms: NOW,
      last_run_at_ms: NOW,
      last_result: { live_market_updates_published: 0 },
    },
    notifications: {
      enabled: true,
      worker_running: true,
      summary: {
        subscriber_key: "local",
        unread_count: 0,
        high_unread_count: 0,
        critical_unread_count: 0,
        highest_unread_severity: null,
        account_unread_counts: {},
      },
    },
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
    targets: [],
    attention: [],
    projection: {
      status: "fresh",
      version: "token-radar-route-fixture",
      source: "route_test",
      row_count: 0,
      source_rows: 0,
      computed_at_ms: NOW,
    },
    ...overrides,
  };
}

export function signalPulseFixture(overrides: Partial<SignalPulseData> = {}): SignalPulseData {
  return {
    query: { window: "1h", scope: "all" },
    health: {
      pulse_ready: true,
      agent_worker_running: true,
      candidate_count: 0,
      blocked_low_information_count: 0,
      dead_job_count: 0,
      market_ready_rate: 1,
      settlement_coverage: null,
    },
    summary: {
      trade_candidate: 0,
      token_watch: 0,
      theme_watch: 0,
      risk_rejected_high_info: 0,
      blocked_low_information: 0,
    },
    items: [],
    returned_count: 0,
    has_more: false,
    next_cursor: null,
    ...overrides,
  };
}
