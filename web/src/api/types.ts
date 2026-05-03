export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "1m" | "5m" | "1h" | "24h";
export type ScopeKey = "matched" | "all";

export type BootstrapData = {
  ws_token: string;
  handles: string[];
  replay_limit: number;
};

export type EventRecord = {
  event_id: string;
  action?: string | null;
  canonical_url?: string | null;
  received_at_ms?: number | null;
  author_handle?: string | null;
  text_clean?: string | null;
  search_text?: string | null;
  cashtags?: string[];
  hashtags?: string[];
  mentions?: string[];
  urls?: string[];
  is_watched?: number | boolean | null;
  source?: {
    provider?: string | null;
    transport?: string | null;
    coverage?: string | null;
    channel?: string | null;
  } | null;
  author?: {
    handle?: string | null;
    name?: string | null;
    avatar?: string | null;
    followers?: number | null;
    tags?: string[];
  } | null;
  content?: {
    text?: string | null;
  } | null;
};

export type EntityRecord = {
  entity_type: string;
  normalized_value: string;
  chain?: string | null;
  author_handle?: string | null;
  received_at_ms?: number | null;
};

export type AlertRecord = {
  alert_type: string;
  event_id: string;
  author_handle?: string | null;
  entity_key?: string | null;
  entity_type?: string | null;
  normalized_value?: string | null;
  chain?: string | null;
  token_resolution_status?: string | null;
  narrative_label?: string | null;
  received_at_ms?: number | null;
  is_first_seen_global?: number | boolean | null;
  is_first_seen_by_author?: number | boolean | null;
  confidence?: number | null;
  summary?: string | null;
  evidence?: string | null;
};

export type EnrichmentRecord = {
  summary?: string | null;
  stance?: string | null;
  intent?: string | null;
  confidence?: number | null;
  token_candidates?: Array<Record<string, unknown>>;
  narratives?: Array<Record<string, unknown>>;
  alerts?: AlertRecord[];
};

export type LivePayload = {
  type: "event";
  event: EventRecord;
  entities: EntityRecord[];
  alerts: AlertRecord[];
  enrichment?: EnrichmentRecord | null;
};

export type RecentData = {
  scope: ScopeKey;
  events: EventRecord[];
  items: LivePayload[];
};

export type SearchItem = {
  event: EventRecord;
  match_type: string;
  score: number;
};

export type SearchData = {
  query: Record<string, unknown>;
  result_count: number;
  items: SearchItem[];
};

export type TokenFlowItem = {
  identity: {
    identity_key: string;
    identity_status: "resolved_ca" | "resolved_alias" | "unresolved_symbol" | "ambiguous_symbol" | string;
    token_id?: string | null;
    chain?: string | null;
    address?: string | null;
    symbol?: string | null;
  };
  social: {
    window: WindowKey;
    window_start_ms?: number | null;
    window_end_ms?: number | null;
    mention_count: number;
    watched_mention_count: number;
    unique_author_count: number;
    weighted_reach?: number | null;
    market_mindshare: number;
    watched_mindshare: number;
    velocity?: number | null;
    top_authors?: Array<{ handle?: string; count?: number; followers?: number | null }>;
  };
  baseline: {
    baseline_status: "ready" | "insufficient_history" | string;
    sample_count: number;
    baseline_mean?: number | null;
    baseline_stddev?: number | null;
    delta_pct?: number | null;
    z_score?: number | null;
    percentile?: number | null;
    acceleration?: number | null;
  };
  anomaly: {
    score: number;
    reasons: string[];
  };
  market: {
    market_status: "fresh" | "stale" | "missing" | string;
    market_confirmed: boolean;
    price?: number | null;
    previous_price?: number | null;
    price_change_pct?: number | null;
    market_cap?: number | null;
    snapshot_age_ms?: number | null;
    snapshot_received_at_ms?: number | null;
  };
  confidence: {
    score: number;
    coverage: string;
    coverage_boundary: string;
    identity_status: string;
    market_status: string;
    baseline_status: string;
    reasons: string[];
  };
  evidence: Array<{
    event_id?: string;
    author_handle?: string | null;
    received_at_ms?: number | null;
    text_clean?: string | null;
    canonical_url?: string | null;
  }>;
};

export type TokenFlowData = {
  window: WindowKey;
  items: TokenFlowItem[];
};

export type AccountAlertsData = {
  window: WindowKey;
  alert_type?: string | null;
  items: AlertRecord[];
};

export type NarrativeFlowItem = {
  narrative_label: string;
  window: WindowKey;
  mention_count: number;
  watched_mention_count: number;
  unique_author_count: number;
  velocity?: number | null;
  top_authors?: Array<{ handle?: string; count?: number; followers?: number | null }>;
  top_events?: Array<{ event_id?: string; author_handle?: string; received_at_ms?: number }>;
};

export type NarrativeFlowData = {
  window: WindowKey;
  items: NarrativeFlowItem[];
};

export type EnrichmentJobsData = {
  items: Array<Record<string, unknown>>;
  counts: Record<string, number>;
};

export type StatusData = {
  ok: boolean;
  reasons: string[];
  handles: string[];
  store: string;
  collector: {
    started_at_ms: number;
    frames_received: number;
    twitter_events: number;
    matched_twitter_events: number;
    events_published: number;
    duplicate_twitter_events: number;
    duplicate_matched_twitter_events: number;
    parse_errors: number;
    last_frame_at_ms?: number | null;
    last_event_at_ms?: number | null;
    last_matched_event_at_ms?: number | null;
  };
  enrichment: {
    llm_configured: boolean;
    worker_running: boolean;
    job_counts: Record<string, number>;
  };
};
