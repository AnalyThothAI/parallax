export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "5m" | "1h" | "4h" | "24h";
export type ScopeKey = "matched" | "all";
export type Decision = "driver" | "watch" | "investigate" | "discard";
export type RadarSortMode = "opportunity" | "heat" | "quality" | "propagation" | "timing";
export type TokenDetailTab = "timeline" | "posts" | "score" | "lab" | "accounts";
export type TimelineBucket = "30s" | "5m" | "15m" | "1h";
export type TokenPostRange = "current_window" | "since_ignition" | "all_history";
export type TokenPostSortMode = "recent" | "quality" | "catalyst";
export type TokenPostServerSort = "recent" | "catalyst";
export type TokenDetailMode = "compact" | "replay";

export type BootstrapData = {
  ws_token: string;
  handles: string[];
  replay_limit: number;
};

export type EventRecord = {
  event_id: string;
  tweet_id?: string | null;
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
  received_at_ms?: number | null;
  is_first_seen_global?: number | boolean | null;
  is_first_seen_by_author?: number | boolean | null;
  confidence?: number | null;
  summary?: string | null;
  evidence?: string | null;
};

export type TokenIntentRecord = {
  intent_id?: string | null;
  event_id?: string | null;
  display_symbol?: string | null;
  display_name?: string | null;
  chain_hint?: string | null;
  address_hint?: string | null;
  intent_status?: string | null;
  intent_confidence?: number | null;
};

export type TokenResolutionRecord = {
  resolution_id?: string | null;
  intent_id?: string | null;
  event_id?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  pricefeed_id?: string | null;
  resolution_status?: string | null;
  reason_codes_json?: string[];
  candidate_ids_json?: string[];
  lookup_keys_json?: string[];
};

export type LivePayload = {
  type: "event";
  event: EventRecord;
  entities: EntityRecord[];
  alerts: AlertRecord[];
  token_intents?: TokenIntentRecord[];
  token_resolutions?: TokenResolutionRecord[];
  harness?: unknown | null;
};

export type NotificationSeverity = "info" | "warning" | "high" | "critical";

export type NotificationItem = {
  notification_id: string;
  dedup_key: string;
  rule_id: string;
  severity: NotificationSeverity | string;
  title: string;
  body: string;
  entity_type?: string | null;
  entity_key?: string | null;
  author_handle?: string | null;
  symbol?: string | null;
  chain?: string | null;
  address?: string | null;
  event_id?: string | null;
  source_table: string;
  source_id: string;
  occurrence_count: number;
  first_seen_at_ms: number;
  last_seen_at_ms: number;
  created_at_ms: number;
  updated_at_ms: number;
  read_at_ms?: number | null;
  payload: Record<string, unknown>;
  channels: string[];
};

export type NotificationSummary = {
  subscriber_key: string;
  unread_count: number;
  high_unread_count: number;
  critical_unread_count: number;
  highest_unread_severity?: NotificationSeverity | string | null;
  account_unread_counts: Record<string, number>;
};

export type NotificationsData = {
  items: NotificationItem[];
  summary: NotificationSummary;
};

export type NotificationLivePayload = {
  type: "notification";
  notification: NotificationItem;
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
  candidates?: TokenIdentityBlock[];
  items: SearchItem[];
};

export type AssetFlowAssetBlock = {
  asset_id?: string | null;
  symbol?: string | null;
  asset_type?: string | null;
  identity_status?: string | null;
};

export type AssetFlowTargetBlock = {
  target_type?: "Asset" | "CexToken" | "Project" | string | null;
  target_id?: string | null;
  symbol?: string | null;
  name?: string | null;
  status?: string | null;
  chain_id?: string | null;
  token_standard?: string | null;
  address?: string | null;
  pricefeed_id?: string | null;
  native_market_id?: string | null;
  quote_symbol?: string | null;
  feed_type?: string | null;
  provider?: string | null;
};

export type AssetFlowVenueBlock = {
  venue_id?: string | null;
  venue_type?: "cex" | "dex" | string | null;
  exchange?: string | null;
  chain?: string | null;
  address?: string | null;
  inst_id?: string | null;
  base_symbol?: string | null;
  quote_symbol?: string | null;
  inst_type?: string | null;
};

export type AssetFlowAttentionBlock = {
  mentions_5m: number;
  mentions_1h: number;
  mentions_window: number;
  unique_authors: number;
  watched_mentions: number;
  latest_seen_ms?: number | null;
  previous_mentions?: number | null;
  mention_delta?: number | null;
  mention_delta_pct?: number | null;
  z_score?: number | null;
  new_burst_score?: number | null;
  stream_share?: number | null;
  baseline_status?: string | null;
  baseline_sample_count?: number | null;
};

export type TokenRadarIntentBlock = {
  intent_id?: string | null;
  display_symbol?: string | null;
  display_name?: string | null;
  evidence?: unknown[];
};

export type TokenRadarScoreBlock = {
  score: number;
  score_version?: string | null;
  reasons?: string[];
  risks?: string[];
  hard_risks?: string[];
  contributions?: ScoreContribution[];
  risk_caps?: RiskCap[];
};

export type TokenRadarScoreSet = {
  heat?: TokenRadarScoreBlock;
  quality?: TokenRadarScoreBlock;
  propagation?: TokenRadarScoreBlock;
  tradeability?: TokenRadarScoreBlock;
  timing?: TokenRadarScoreBlock & {
    status?: string | null;
    chase_risk?: boolean | null;
  };
  opportunity?: TokenRadarScoreBlock & {
    components?: {
      heat?: number | null;
      quality?: number | null;
      propagation?: number | null;
      tradeability?: number | null;
      timing?: number | null;
    };
  };
};

export type TokenRadarDataHealth = {
  identity?: string | null;
  market?: string | null;
  coverage?: string | null;
  [key: string]: unknown;
};

export type AssetFlowRow = {
  intent?: TokenRadarIntentBlock;
  target?: AssetFlowTargetBlock;
  attention: AssetFlowAttentionBlock;
  source_event_ids?: string[];
  price?: {
    market_status: "fresh" | "stale" | "missing" | string;
    provider?: string | null;
    price_usd?: number | null;
    price_quote?: number | null;
    quote_symbol?: string | null;
    price_basis?: string | null;
    market_cap_usd?: number | null;
    liquidity_usd?: number | null;
    volume_24h_usd?: number | null;
    open_interest_usd?: number | null;
    holders?: number | null;
    snapshot_age_ms?: number | null;
    snapshot_observed_at_ms?: number | null;
    social_signal_start_ms?: number | null;
    price_change_5m_pct?: number | null;
    price_change_1h_pct?: number | null;
    price_change_24h_pct?: number | null;
    price_at_social_start?: number | null;
    price_at_reference?: number | null;
    price_before_social_start?: number | null;
    price_change_since_social_pct?: number | null;
    price_change_before_social_pct?: number | null;
    price_at_first_snapshot?: number | null;
    first_snapshot_observed_at_ms?: number | null;
    price_change_since_first_snapshot_pct?: number | null;
    market_observation_status?: string | null;
    price_change_status?: string | null;
  };
  resolution: {
    status: "EXACT" | "UNIQUE_BY_CONTEXT" | "NIL" | "AMBIGUOUS" | string;
    resolution_status?: string | null;
    target_type?: string | null;
    target_id?: string | null;
    pricefeed_id?: string | null;
    reason_codes?: string[];
    candidate_ids?: string[];
    lookup_keys?: string[];
    discovery?: TokenDiscoveryAudit[];
    confidence?: number | null;
    reasons?: string[];
    risks?: string[];
    candidates?: unknown[];
  };
  score?: TokenRadarScoreSet;
  decision: Decision | string;
  data_health?: TokenRadarDataHealth;
};

export type TokenDiscoveryAudit = {
  lookup_key?: string | null;
  lookup_type?: string | null;
  status?: "running" | "found" | "not_found" | "error" | string | null;
  candidate_count?: number | null;
  last_lookup_at_ms?: number | null;
  next_refresh_at_ms?: number | null;
  last_error?: string | null;
  error_count?: number | null;
};

export type AssetFlowData = {
  window: WindowKey;
  scope: ScopeKey;
  targets: AssetFlowRow[];
  attention: AssetFlowRow[];
  projection: {
    status: "fresh" | "stale" | string;
    version: string;
    source: string;
    source_max_received_at_ms?: number | null;
    computed_at_ms?: number | null;
  };
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
  data_health?: Record<string, unknown>;
};

export type TokenIdentityBlock = {
  identity_key: string;
  identity_status: "resolved_ca" | string;
  target_type?: string | null;
  target_id?: string | null;
  asset_id?: string | null;
  asset_type?: string | null;
  venue_type?: string | null;
  exchange?: string | null;
  inst_id?: string | null;
  inst_type?: string | null;
  chain?: string | null;
  address?: string | null;
  symbol?: string | null;
  resolution_reasons?: string[];
  lookup_keys?: string[];
  candidate_count?: number;
  discovery_status?: string | null;
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
  price_at_first_snapshot?: number | null;
  first_snapshot_observed_at_ms?: number | null;
  price_change_since_first_snapshot_pct?: number | null;
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
  mentions_5m: number;
  mentions_1h: number;
  mentions_4h: number;
  mentions_24h: number;
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
  status: "neutral" | "market_pending" | "market_unavailable" | "chase_risk";
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

export type WatchBlock = {
  status: "direct_watch" | "seed_linked" | "public_only" | string;
  direct_mentions: number;
  direct_authors: number;
  seed_link_count: number;
  top_seed?: Record<string, unknown> | null;
  reasons: string[];
  risks: string[];
};

export type TokenPostsQuery = {
  target_type?: string | null;
  target_id?: string | null;
  window: WindowKey;
  scope: ScopeKey;
  range: TokenPostRange;
  sort?: TokenPostServerSort;
};

export type TokenSocialTimelineParams = {
  target_type?: string | null;
  target_id?: string | null;
  window: WindowKey;
  scope: ScopeKey;
};

export type TokenSocialTimelineQuery = TokenSocialTimelineParams & {
  bucket: TimelineBucket;
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
  watch: WatchBlock;
  evidence_total_count: number;
  posts_query: TokenPostsQuery;
  timeline_query: TokenSocialTimelineParams;
};

export type TokenPostItem = {
  event_id: string;
  tweet_id?: string | null;
  handle?: string | null;
  text?: string | null;
  url?: string | null;
  received_at_ms?: number | null;
  mention_source?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  attribution_status?: string | null;
  attribution_confidence?: number | null;
  attribution_weight?: number | null;
  is_watched?: boolean | number | null;
  is_first_seen_by_watched_for_token?: boolean | number | null;
  event_type?: string | null;
  reference?: TokenReference | null;
  catalyst_score?: number | null;
  catalyst_components?: CatalystComponents | null;
  price?: TokenMessagePrice | null;
  stage_id?: string | null;
  stage_phase?: string | null;
  author_role?: string | null;
  is_stage_representative?: boolean | number | null;
  price_delta_from_previous_post_pct?: number | null;
  post_quality: ScoreBlock;
};

export type TokenMessagePrice = {
  status: "ready" | "stale" | "pending_observation" | string;
  provider?: string | null;
  pricefeed_id?: string | null;
  price_usd?: number | null;
  price_quote?: number | null;
  quote_symbol?: string | null;
  observed_at_ms?: number | null;
  observation_lag_ms?: number | null;
  observation_id?: string | null;
  observation_kind?: string | null;
};

export type TokenPostsData = {
  query: TokenPostsQuery;
  score_window: { window: WindowKey };
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
  authors?: number;
  new_authors: number;
  watched_posts: number;
  duplicate_text_share: number;
  price?: TokenMessagePrice | null;
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
  tweet_id?: string | null;
  handle?: string | null;
  received_at_ms?: number | null;
  bucket_start_ms?: number | null;
  text?: string | null;
  url?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  attribution_status?: string | null;
  is_watched?: boolean | number | null;
  is_first_seen_by_watched_for_token?: boolean | number | null;
  event_type?: string | null;
  reference?: TokenReference | null;
  price?: TokenMessagePrice | null;
  attribution_confidence?: number | null;
  attribution_weight?: number | null;
  mention_source?: string | null;
  catalyst_score?: number | null;
  catalyst_components?: CatalystComponents | null;
  stage_id?: string | null;
  stage_phase?: string | null;
  author_role?: string | null;
  is_stage_representative?: boolean | number | null;
  price_delta_from_previous_post_pct?: number | null;
  post_quality: ScoreBlock;
};

export type TokenReference = {
  tweet_id?: string | null;
  author_handle?: string | null;
  type?: string | null;
};

export type TokenTimelineCascadeEdge = {
  event_id?: string | null;
  parent_event_id?: string | null;
  parent_tweet_id?: string | null;
  edge_type?: string | null;
  parent_author_handle?: string | null;
  resolved: boolean;
};

export type TokenTimelineCascade = {
  edges: TokenTimelineCascadeEdge[];
  unresolved_parents: TokenTimelineCascadeEdge[];
};

export type CatalystComponents = {
  observation_window_ms?: number;
  baseline_window_ms?: number;
  followup_count?: number;
  independent_authors?: number;
  baseline_mentions_per_min?: number;
  excess_followups?: number;
  excess_score?: number;
  independence_score?: number;
  explicit_cascade_followups?: number;
  cascade_grip?: number;
  time_to_k_authors?: number;
  time_to_k_authors_ms?: number | null;
  time_to_k_score?: number;
  structural_virality_score?: number;
  avg_followup_quality?: number;
};

export type TokenTimelineMarketOverlay = {
  target_type?: string | null;
  target_id?: string | null;
  chain_id?: string | null;
  address?: string | null;
  symbol?: string | null;
  pricefeed_id?: string | null;
  provider?: string | null;
  native_market_id?: string | null;
  quote_symbol?: string | null;
  feed_type?: string | null;
};

export type TokenTimelineStage = {
  stage_id: string;
  phase: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  trigger_reason: string;
  confidence: number;
  people: {
    posts: number;
    authors: number;
    new_authors: number;
    watched_posts: number;
    watched_authors: number;
    top_author_share: number;
  };
  representative_event_ids: string[];
  price: {
    status: string;
    start_price?: number | null;
    end_price?: number | null;
    delta_pct?: number | null;
    observation_ids: string[];
    max_observation_lag_ms?: number | null;
  };
  risks: string[];
};

export type TokenSocialTimelineData = {
  query: TokenSocialTimelineQuery;
  summary: {
    posts: number;
    authors: number;
    effective_authors: number;
    first_seen_ms?: number | null;
    latest_seen_ms?: number | null;
    watched_posts?: number | null;
    phase: string;
    top_author_share: number;
    duplicate_text_share: number;
    peak_posts_per_bucket: number;
    peak_new_authors_per_bucket: number;
    reproduction_rate: number | null;
  };
  market_overlay?: TokenTimelineMarketOverlay | null;
  stages: TokenTimelineStage[];
  buckets: TokenTimelineBucket[];
  authors: TokenTimelineAuthor[];
  posts: TokenTimelinePost[];
  cascade: TokenTimelineCascade;
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
};

export type TradingAttentionKind =
  | "direct_token"
  | "topic_heat"
  | "ecosystem_signal"
  | "market_structure"
  | "risk_alert"
  | "low_signal";
export type TradingAttentionKindFilter = "all" | TradingAttentionKind;
export type TradingAttentionPriority = "hot" | "watch" | "context" | "muted";

export type TradingAttentionToken = {
  asset_id?: string | null;
  venue_id?: string | null;
  identity_key?: string | null;
  symbol?: string | null;
  asset_type?: string | null;
  venue_type?: string | null;
  exchange?: string | null;
  chain?: string | null;
  address?: string | null;
  inst_id?: string | null;
  base_symbol?: string | null;
  quote_symbol?: string | null;
  inst_type?: string | null;
  relation: string;
  confidence: number;
  status: string;
  source?: string | null;
};

export type TradingAttentionTopic = {
  key: string;
  label: string;
  role: string;
};

export type TradingAttentionItem = {
  item_id: string;
  kind: TradingAttentionKind;
  kind_label: string;
  priority: TradingAttentionPriority;
  heat_score: number;
  received_at_ms: number;
  updated_at_ms: number;
  source: {
    handle?: string | null;
    followers?: number | null;
  };
  event: {
    event_id: string;
    tweet_id?: string | null;
    canonical_url?: string | null;
    author_handle?: string | null;
    text?: string | null;
    received_at_ms?: number | null;
  };
  event_type?: string | null;
  direction_hint?: string | null;
  attention_mechanism?: string | null;
  title: string;
  summary: string;
  why_it_matters: string;
  linked_tokens: TradingAttentionToken[];
  linked_topics: TradingAttentionTopic[];
  metrics: {
    impact: number;
    novelty: number;
    confidence: number;
    direct_token_count: number;
    topic_count: number;
    account_alert_count: number;
    window_mentions: number;
    watched_author_count: number;
  };
  risks: string[];
  next_action: string;
};

export type TradingAttentionSummary = Record<TradingAttentionKind | TradingAttentionPriority, number>;

export type TradingAttentionData = {
  query: {
    window: WindowKey;
    scope: ScopeKey;
    kind?: TradingAttentionKind | null;
    handle?: string | null;
    q?: string | null;
  };
  summary: TradingAttentionSummary;
  items: TradingAttentionItem[];
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
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
  harness_ops?: {
    worker_running: boolean;
    last_run_at_ms?: number | null;
    last_result?: Record<string, unknown> | null;
  };
  token_radar_projection?: {
    worker_running: boolean;
    last_started_at_ms?: number | null;
    last_run_at_ms?: number | null;
    last_result?: Record<string, unknown> | null;
    last_error?: string | null;
  };
  asset_market_sync?: {
    okx_cex_sync_enabled?: boolean;
    worker_running: boolean;
    last_started_at_ms?: number | null;
    last_run_at_ms?: number | null;
    last_result?: Record<string, unknown> | null;
    last_error?: string | null;
    providers?: Record<string, Record<string, unknown>>;
  };
  notifications?: {
    enabled: boolean;
    worker_running: boolean;
    delivery_worker_running?: boolean;
    summary: NotificationSummary;
  };
};
