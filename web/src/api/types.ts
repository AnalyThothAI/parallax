export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "5m" | "1h" | "24h";
export type ScopeKey = "matched" | "all";
export type Decision = "driver" | "watch" | "discard";
export type RadarSortMode = "opportunity" | "heat" | "quality" | "propagation" | "timing";
export type TokenDetailTab = "timeline" | "posts" | "score" | "narratives" | "accounts";
export type TimelineBucket = "30s" | "1m" | "5m";

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

export type TokenAttributionRecord = {
  attribution_id?: string | null;
  mention_identity_key?: string | null;
  identity_key?: string | null;
  token_id?: string | null;
  identity_status?: string | null;
  chain?: string | null;
  address?: string | null;
  symbol?: string | null;
  source?: string | null;
  attribution_status?: string | null;
  attribution_confidence?: number | null;
  attribution_weight?: number | null;
  attribution_rank?: number | null;
  candidate_count?: number | null;
  received_at_ms?: number | null;
  author_handle?: string | null;
  author_followers?: number | null;
  is_watched?: number | boolean | null;
};

export type EnrichmentRecord = {
  summary?: string | null;
  summary_zh?: string | null;
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
  token_attributions?: TokenAttributionRecord[];
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
  total_count: number;
  returned_count: number;
  has_more: boolean;
  items: SearchItem[];
};

export type ScoreContribution = {
  feature: string;
  value: number;
  reason: string;
};

export type RiskCap = {
  risk: string;
  cap: number;
};

export type ScoreBlock = {
  score: number;
  score_version: string;
  reasons: string[];
  risks: string[];
  contributions: ScoreContribution[];
  risk_caps: RiskCap[];
};

export type TokenIdentityBlock = {
  identity_key: string;
  identity_status: "resolved_ca" | string;
  token_id?: string | null;
  chain?: string | null;
  address?: string | null;
  symbol?: string | null;
};

export type TokenMarketBlock = {
  market_status: "fresh" | "stale" | "missing" | string;
  price?: number | null;
  market_cap?: number | null;
  liquidity?: number | null;
  pool_status?: "ready" | "missing" | string;
  holder_count?: number | null;
  volume_24h?: number | null;
  snapshot_age_ms?: number | null;
  snapshot_received_at_ms?: number | null;
  social_signal_start_ms?: number | null;
  reference_ms?: number | null;
  price_at_social_start?: number | null;
  price_at_reference?: number | null;
  price_change_since_social_pct?: number | null;
  price_before_social_start?: number | null;
  price_change_before_social_pct?: number | null;
  market_observation_status?: "ready" | "pending" | "running" | "provider_not_configured" | "provider_not_found" | "provider_error" | "rate_limited" | "dead" | string;
  price_change_status: "ready" | "pending_observation" | "insufficient_history" | "missing_market" | "provider_not_configured" | "provider_not_found" | "provider_error" | "rate_limited" | "dead" | string;
};

export type TokenFlowBlock = {
  window: WindowKey;
  window_start_ms?: number | null;
  window_end_ms?: number | null;
  mentions: number;
  direct_mentions?: number;
  symbol_mentions?: number;
  weighted_mentions?: number;
  avg_attribution_confidence?: number;
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

export type SocialHeatBlock = ScoreBlock & {
  window: WindowKey;
  mentions: number;
  mentions_5m?: number;
  mentions_1h?: number;
  mentions_24h?: number;
  weighted_mentions: number;
  previous_mentions: number;
  mention_delta: number;
  mention_delta_pct?: number | null;
  z_score?: number | null;
  new_burst_score?: number | null;
  stream_share: number;
  watched_share: number;
  status: "cold" | "rising" | "burst" | "new_burst" | "insufficient_history" | string;
};

export type DiscussionQualityBlock = ScoreBlock & {
  evidence_specificity: number;
  avg_post_quality: number;
  avg_attribution_confidence: number;
  duplicate_text_share: number;
  informative_post_count: number;
  watched_source_count: number;
};

export type PropagationBlock = ScoreBlock & {
  independent_authors: number;
  effective_authors: number;
  new_authors: number;
  top_author_share: number;
  duplicate_text_share: number;
  author_entropy: number;
  reproduction_rate?: number | null;
  phase: "seed" | "ignition" | "expansion" | "concentration" | "fade" | string;
  top_authors: Array<{ handle?: string | null; count?: number; posts?: number; followers?: number | null; watched_count?: number; role?: string | null }>;
};

export type TradeabilityBlock = ScoreBlock & {
  identity_tradeable: boolean;
  market_fresh: boolean;
  market_cap_present: boolean;
  liquidity_present: boolean;
  pool_present: boolean;
  hard_risks?: string[];
};

export type TimingBlock = {
  score: number;
  score_version: string;
  status: "social_leads_price" | "social_confirms_price" | "price_leads_social" | "social_fades" | "market_pending" | "market_unavailable" | "insufficient_history" | string;
  social_signal_start_ms?: number | null;
  price_change_since_social_pct?: number | null;
  price_change_before_social_pct?: number | null;
  market_observation_status?: string | null;
  chase_risk: boolean;
  reasons: string[];
  risks: string[];
  contributions?: ScoreContribution[];
  risk_caps?: RiskCap[];
};

export type OpportunityBlock = ScoreBlock & {
  decision: Decision;
  decision_priority?: number;
  hard_risks?: string[];
  components: {
    heat: number;
    quality: number;
    propagation: number;
    tradeability: number;
    timing: number;
  };
};

export type TokenPostsQuery = {
  token_id?: string | null;
  chain?: string | null;
  address?: string | null;
  window: WindowKey;
  scope: ScopeKey;
  sort?: "recent" | string;
};

export type TokenSocialTimelineQuery = {
  token_id?: string | null;
  chain?: string | null;
  address?: string | null;
  window: WindowKey;
  bucket: TimelineBucket;
  scope: ScopeKey;
};

export type TokenFlowItem = {
  identity: TokenIdentityBlock;
  market: TokenMarketBlock;
  flow: TokenFlowBlock;
  social_heat: SocialHeatBlock;
  discussion_quality: DiscussionQualityBlock;
  propagation: PropagationBlock;
  tradeability: TradeabilityBlock;
  timing: TimingBlock;
  opportunity: OpportunityBlock;
  evidence_total_count: number;
  posts_query: TokenPostsQuery;
  timeline_query: TokenSocialTimelineQuery;
};

export type TokenPostItem = {
  event_id: string;
  handle?: string | null;
  text?: string | null;
  url?: string | null;
  received_at_ms?: number | null;
  mention_source?: string | null;
  attribution_status?: string | null;
  attribution_confidence?: number | null;
  attribution_weight?: number | null;
  is_watched?: boolean | number | null;
  post_quality: ScoreBlock;
};

export type TokenPostsData = {
  query: TokenPostsQuery;
  total_count: number;
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
  items: TokenPostItem[];
};

export type TokenFlowData = {
  window: WindowKey;
  scope?: ScopeKey;
  items: TokenFlowItem[];
};

export type TokenTimelineBucket = {
  start_ms: number;
  end_ms: number;
  posts: number;
  new_authors: number;
  watched_posts: number;
  duplicate_text_share: number;
  price?: number | null;
  price_change_from_start_pct?: number | null;
};

export type TokenTimelineAuthor = {
  handle: string;
  first_seen_ms?: number | null;
  latest_seen_ms?: number | null;
  posts: number;
  followers?: number | null;
  role?: "seed" | "early_amplifier" | "amplifier" | "repeater" | "watched" | string | null;
  quality_score?: number | null;
};

export type TokenTimelinePost = {
  event_id: string;
  handle?: string | null;
  received_at_ms?: number | null;
  bucket_start_ms?: number | null;
  text?: string | null;
  url?: string | null;
  attribution_status?: string | null;
  is_watched?: boolean | number | null;
  post_quality: ScoreBlock;
};

export type TokenSocialTimelineData = {
  query: TokenSocialTimelineQuery;
  summary: {
    posts: number;
    authors: number;
    effective_authors: number;
    first_seen_ms?: number | null;
    latest_seen_ms?: number | null;
    phase: string;
    top_author_share: number;
    duplicate_text_share: number;
  };
  buckets: TokenTimelineBucket[];
  authors: TokenTimelineAuthor[];
  posts: TokenTimelinePost[];
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
};

export type AccountAlertsData = {
  window: WindowKey;
  alert_type?: string | null;
  items: AlertRecord[];
};

export type NarrativeDisplay = {
  name_zh: string;
  headline_zh: string;
  summary_zh: string;
  market_interpretation_zh: string;
  readability_status: "ready" | "narrative_display_missing" | string;
};

export type NarrativeFlowItem = {
  narrative_label: string;
  window: WindowKey;
  display: NarrativeDisplay;
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
  display: NarrativeDisplay;
  seed_family?: string | null;
  seed_terms?: string[];
  market_interpretation?: string | null;
  author_handle?: string | null;
  evidence?: string | null;
  summary?: string | null;
  received_at_ms?: number | null;
};

export type NarrativeTokenLinkItem = {
  identity: TokenIdentityBlock;
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
    decision: Decision;
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

export type AccountQualityItem = {
  profile: {
    handle: string;
    first_seen_ms: number;
    latest_seen_ms: number;
    follower_max?: number | null;
    watched_status: string;
  } | null;
  summary: {
    status: "ready" | "insufficient_sample" | string;
    sample_size: number;
    precision_score?: number | null;
    early_call_score?: number | null;
    spam_risk_score?: number | null;
    avg_realized_return?: number | null;
  };
  token_call_stats: Array<Record<string, unknown>>;
  quality_snapshots: Array<Record<string, unknown>>;
};

export type AccountQualityData = {
  query: { handles: string[] };
  accounts: AccountQualityItem[];
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
  market_observations?: Record<string, number | boolean>;
};
