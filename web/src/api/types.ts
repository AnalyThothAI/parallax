export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "5m" | "1h" | "4h" | "24h";
export type ScopeKey = "matched" | "all";
export type Decision = "driver" | "watch" | "discard";
export type RadarSortMode = "opportunity" | "heat" | "quality" | "propagation" | "timing";
export type TokenDetailTab = "timeline" | "posts" | "score" | "lab" | "accounts";
export type TimelineBucket = "30s" | "5m" | "15m" | "1h";
export type TokenPostRange = "current_window" | "since_ignition" | "all_history";

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

export type LivePayload = {
  type: "event";
  event: EventRecord;
  entities: EntityRecord[];
  alerts: AlertRecord[];
  token_attributions?: TokenAttributionRecord[];
  harness?: HarnessEventState | null;
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
  mentions_4h?: number;
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
  token_id?: string | null;
  chain?: string | null;
  address?: string | null;
  window: WindowKey;
  scope: ScopeKey;
  range?: TokenPostRange;
  sort?: "recent" | string;
};

export type TokenSocialTimelineQuery = {
  token_id?: string | null;
  chain?: string | null;
  address?: string | null;
  window: WindowKey;
  bucket?: TimelineBucket;
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
  watch: WatchBlock;
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
  score_window?: { window: WindowKey };
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
    peak_posts_per_bucket?: number;
    peak_new_authors_per_bucket?: number;
    reproduction_rate?: number | null;
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

export type AnchorTerm = {
  term: string;
  role: "subject" | "meme_phrase" | "product" | "asset" | "person" | "venue" | string;
  evidence: string;
};

export type SocialTokenCandidate = {
  symbol?: string | null;
  project_name?: string | null;
  chain?: string | null;
  address?: string | null;
  evidence: string;
  confidence: number;
};

export type SocialEventItem = {
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  schema_version: string;
  event_type: string;
  source_action: string;
  subject: string;
  direction_hint: string;
  attention_mechanism: string;
  impact_hint: number;
  semantic_novelty_hint: number;
  confidence: number;
  is_signal_event: boolean;
  anchor_terms: AnchorTerm[];
  token_candidates: SocialTokenCandidate[];
  semantic_risks: string[];
  summary_zh: string;
  event?: EventRecord | null;
};

export type HarnessEventState = {
  social_event?: SocialEventItem | null;
  attention_seed?: AttentionSeedItem | null;
  clusters?: HarnessClusterSummary[];
  snapshots?: HarnessSnapshotItem[];
};

export type AttentionSeedItem = {
  seed_id: string;
  extraction_id: string;
  event_id: string;
  author_handle?: string | null;
  received_at_ms: number;
  event_type: string;
  subject: string;
  anchor_terms: AnchorTerm[];
  token_uptake_count: number;
  top_linked_symbols: string[];
  seed_status: "seed_only" | "linked" | "snapshot_ready" | "outcome_pending" | "settled" | string;
  risks: string[];
};

export type HarnessClusterSummary = {
  cluster_id: string;
  event_type: string;
  source?: string | null;
  event_score: number;
};

export type HarnessVersionBlock = {
  config_version: string;
  prompt_version: string;
  schema_version: string;
  scoring_version: string;
  weight_version: string;
  policy_version: string;
  risk_version: string;
  baseline_version: string;
};

export type HarnessSnapshotItem = {
  snapshot_id: string;
  source_event_id?: string | null;
  seed_id?: string | null;
  asset: string;
  decision_time_ms: number;
  horizon: "6h" | "24h" | string;
  combined_score: number;
  policy_signal: "NO_TRADE" | "LONG" | "SHORT_OR_AVOID" | string;
  shadow_signal: "NO_TRADE" | "LONG_SMALL" | "SHORT_SMALL" | string;
  event_clusters: HarnessClusterSummary[];
  market_state: Record<string, unknown>;
  versions: HarnessVersionBlock;
  outcome_status: "pending" | "settled" | "missing_market" | "insufficient_market_data" | string;
  credit_status: "none" | "assigned" | string;
  risks: string[];
};

export type HarnessOutcomeItem = {
  snapshot_id: string;
  settled_at_ms: number;
  actual_return: number;
  expected_return: number;
  abnormal_return: number;
  realized_vol: number;
  normalized_outcome: number;
  baseline_version: string;
};

export type HarnessCreditItem = {
  credit_id: string;
  snapshot_id: string;
  cluster_id: string;
  asset: string;
  event_type: string;
  source: string;
  horizon: string;
  event_score: number;
  responsibility: number;
  credit: number;
  created_at_ms: number;
};

export type HarnessHealth = {
  llm_configured: boolean;
  extractor_running: boolean;
  schema_success_rate?: number | null;
  pending_jobs: number;
  snapshots_24h: number;
  pending_outcomes: number;
  settlement_coverage?: number | null;
};

export type ScoreBucketItem = {
  bucket: string;
  sample_count: number;
  avg_normalized_outcome: number;
  avg_abnormal_return: number;
  hit_rate: number;
  settled_count: number;
  pending_count: number;
};

export type HarnessWeightItem = {
  key: string;
  weight_type: string;
  asset?: string | null;
  horizon: string;
  n: number;
  mean_credit: number;
  weight: number;
  status: "report_only" | "candidate" | "active" | string;
};

export type SocialEventsData = {
  items: SocialEventItem[];
};

export type AttentionSeedsData = {
  items: AttentionSeedItem[];
};

export type HarnessSnapshotsData = {
  items: HarnessSnapshotItem[];
};

export type HarnessOutcomesData = {
  items: HarnessOutcomeItem[];
};

export type HarnessCreditsData = {
  items: HarnessCreditItem[];
};

export type HarnessHealthData = HarnessHealth;

export type SignalLabStage = "extracted" | "seeded" | "frozen" | "settled" | "credited";
export type SignalLabStageFilter = "all" | SignalLabStage;
export type SignalLabInspectorTab = "trace" | "snapshot" | "outcome" | "credit";

export type SignalLabStageSummary = Record<SignalLabStage, number>;

export type SignalLabChain = {
  chain_id: string;
  stage: SignalLabStage;
  received_at_ms: number;
  updated_at_ms: number;
  asset?: string | null;
  horizon?: string | null;
  source?: string | null;
  event_type?: string | null;
  title: string;
  summary: string;
  score?: number | null;
  outcome_status?: string | null;
  credit_status?: string | null;
  risks: string[];
  evidence_chips?: string[];
  lineage: {
    extraction_id?: string | null;
    event_id?: string | null;
    seed_id?: string | null;
    snapshot_id?: string | null;
    source_event_id?: string | null;
  };
  social_event?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
};

export type SignalLabChainsData = {
  query: {
    window: WindowKey;
    horizon: string;
    scope: ScopeKey;
    stage?: SignalLabStage | null;
    asset?: string | null;
    handle?: string | null;
    q?: string | null;
  };
  summary: SignalLabStageSummary;
  items: SignalLabChain[];
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
  market_observations?: Record<string, number | boolean>;
};
