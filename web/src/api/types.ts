export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "5m" | "1h" | "24h";
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
  market: {
    market_status: "fresh" | "stale" | "missing" | string;
    price?: number | null;
    market_cap?: number | null;
    snapshot_age_ms?: number | null;
    snapshot_received_at_ms?: number | null;
    price_change_window_pct?: number | null;
    price_at_window_start?: number | null;
    price_at_window_end?: number | null;
    price_change_status: "ready" | "insufficient_history" | "missing_market" | string;
  };
  flow: {
    window: WindowKey;
    window_start_ms?: number | null;
    window_end_ms?: number | null;
    mentions: number;
    watched_mentions: number;
    previous_mentions: number;
    mention_delta: number;
    mention_delta_pct?: number | null;
    z_score?: number | null;
    new_burst_score?: number | null;
    stream_dominance: number;
    baseline_status: "ready" | "insufficient_history" | string;
    baseline_sample_count: number;
  };
  baseline: {
    baseline_status: "ready" | "insufficient_history" | string;
    sample_count: number;
    zero_slot_count: number;
    ewma_mean?: number | null;
    ewma_stddev?: number | null;
    simple_mean?: number | null;
    z_score?: number | null;
    new_burst_score?: number | null;
  };
  diffusion: {
    score: number;
    status: "healthy" | "thin" | "concentrated" | "repeated" | "shill_risk" | string;
    independent_authors: number;
    effective_authors: number;
    top_author_share: number;
    duplicate_text_share: number;
    repeated_cluster_count: number;
    shill_author_count: number;
    top_authors?: Array<{ handle?: string | null; count?: number; followers?: number | null; watched_count?: number }>;
    reasons: string[];
    risks: string[];
  };
  watch: {
    status: "direct_watch" | "seed_linked" | "public_only" | string;
    direct_mentions: number;
    direct_authors: number;
    seed_link_count: number;
    top_seed?: Record<string, unknown> | null;
    reasons: string[];
    risks: string[];
  };
  fresh: {
    latest_evidence_age_ms?: number | null;
    first_seen_age_ms?: number | null;
    market_snapshot_age_ms?: number | null;
    is_new_token: boolean;
    is_first_seen_by_watched: boolean;
  };
  signal: {
    decision: "driver" | "watch" | "discard";
    score: number;
    reasons: string[];
    risks: string[];
    evidence_id?: string | null;
  };
  evidence_best?: TokenEvidence | null;
  evidence: TokenEvidence[];
};

export type TokenEvidence = {
  event_id?: string;
  evidence_type?: string;
  score?: number;
  handle?: string | null;
  text?: string | null;
  received_at_ms?: number | null;
  url?: string | null;
  reasons?: string[];
};

export type TokenFlowData = {
  window: WindowKey;
  scope?: ScopeKey;
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

export type NarrativeSeed = {
  seed_id: string;
  narrative_label: string;
  seed_family?: string | null;
  seed_terms?: string[];
  market_interpretation?: string | null;
  author_handle?: string | null;
  evidence?: string | null;
  summary?: string | null;
  received_at_ms?: number | null;
};

export type NarrativeTokenLinkItem = {
  identity: {
    identity_key: string;
    identity_status: string;
    token_id?: string | null;
    chain?: string | null;
    address?: string | null;
    symbol?: string | null;
  };
  flow: {
    window: WindowKey;
    mentions: number;
    watched_mentions: number;
    unique_authors: number;
    weighted_reach?: number | null;
    lag_ms?: number | null;
  };
  market: {
    market_status: string;
    market_cap?: number | null;
    price_change_after_seed_pct?: number | null;
  };
  scores: {
    seed: number;
    diffusion: number;
    token_link: number;
    tradeability: number;
  };
  signal: {
    decision: "driver" | "watch" | "discard";
    reasons: string[];
    risks: string[];
  };
  evidence: {
    first_linked_event_id?: string | null;
    best_evidence_event_id?: string | null;
    link_reason?: string | null;
    matched_terms?: string[];
    link_confidence?: number | null;
  };
};

export type AttentionFrontierItem = {
  seed: NarrativeSeed;
  link: NarrativeTokenLinkItem;
};

export type AttentionFrontierData = {
  window: WindowKey;
  items: AttentionFrontierItem[];
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
