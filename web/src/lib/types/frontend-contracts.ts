import type { components } from "./openapi";

export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
};

export type WindowKey = "5m" | "1h" | "4h" | "24h";
export type ScopeKey = "matched" | "all";
export type TokenCaseApiScope = ScopeKey | "watched";
export type Decision = "driver" | "watch" | "investigate" | "discard";
export type RadarSortMode = "opportunity" | "heat" | "quality" | "propagation" | "timing";
export type TokenDetailTab = "timeline" | "posts" | "score" | "lab" | "accounts";
export type TimelineBucket = "30s" | "5m" | "15m" | "1h";
export type TokenPostRange = "current_window" | "since_ignition" | "all_history";
export type TokenPostSortMode = "recent" | "quality" | "catalyst";
export type TokenPostServerSort = "recent" | "catalyst";
export type TokenDetailMode = "compact" | "replay";
export type WatchlistTimelineScope = "signal" | "all";

export type MacroSnapshotSummary = {
  snapshot_id: string;
  projection_version: string;
  asof_date: string;
  status: string;
  regime: string;
  overall_score?: number | null;
  computed_at_ms: number;
};

export type MacroPanel = {
  score?: number | null;
  regime: string;
  evidence: string[];
  data_gaps: string[];
};

export type MacroIndicator = {
  label: string;
  value?: number | string | null;
  unit?: string | null;
  observed_at?: string | null;
  sources?: string[];
  concept_keys?: string[];
};

export type MacroTrigger = {
  code: string;
  description?: string | null;
  value?: number | string | null;
};

export type MacroFeatureSnapshot = {
  latest?: {
    value?: number | string | null;
    observed_at?: string | null;
    unit?: string | null;
  };
  history?: Array<{
    observed_at?: string | null;
    value?: number | string | null;
  }>;
  freshness_days?: number | null;
  delta?: Record<string, number | null | undefined>;
  zscore?: {
    lookback?: number | null;
    value?: number | null;
  };
  percentile?: {
    lookback?: number | null;
    value?: number | null;
  };
  data_gaps?: string[];
};

export type MacroChainNode = {
  score?: number | null;
  regime?: string | null;
  evidence?: string[];
  data_gaps?: string[];
};

export type MacroScenarioSignal = {
  code?: string | null;
  description?: string | null;
  node?: string | null;
  regime?: string | null;
  evidence?: string[];
  indicator_keys?: string[];
  value?: number | string | null;
  data_gap_count?: number | null;
  delta_5d?: number | null;
};

export type MacroTradeMapAction = {
  kind?: string | null;
  label?: string | null;
  description?: string | null;
};

export type MacroTradeMapEntry = {
  expression?: string | null;
  label?: string | null;
  time_window?: string | null;
  action_checklist?: MacroTradeMapAction[];
};

export type MacroScenarioQualityBlocker = {
  code?: string | null;
  description?: string | null;
  label?: string | null;
  severity?: string | null;
};

export type MacroScenarioCase = {
  case?: string | null;
  entry_condition?: string | null;
  invalidation?: string | null;
  label?: string | null;
  probability?: number | null;
  probability_label?: string | null;
  stop?: string | null;
  thesis?: string | null;
  time_window?: string | null;
  trade?: string | null;
};

export type MacroScenario = {
  current_regime?: string | null;
  confidence?: number | null;
  time_window?: string | null;
  confirmations?: MacroScenarioSignal[];
  contradictions?: MacroScenarioSignal[];
  watch_triggers?: MacroScenarioSignal[];
  invalidations?: MacroScenarioSignal[];
  trade_map?: MacroTradeMapEntry[];
  top_changes?: MacroScenarioSignal[];
  quality_blockers?: MacroScenarioQualityBlocker[];
  scenario_cases?: MacroScenarioCase[];
};

export type MacroScorecard = {
  projection_version?: string | null;
  overall_score?: number | null;
  chain_average?: number | null;
  observed_concept_count?: number | null;
  required_concept_count?: number | null;
  coverage_ratio?: number | null;
  data_gap_count?: number | null;
  chain_regimes?: Record<string, string | null | undefined>;
  [key: string]: unknown;
};

export type MacroData = {
  snapshot: MacroSnapshotSummary | null;
  panels: Record<string, MacroPanel>;
  indicators: Record<string, MacroIndicator>;
  triggers: MacroTrigger[];
  data_gaps: string[];
  source_coverage: Record<string, number | string | null | undefined>;
  features: Record<string, MacroFeatureSnapshot>;
  chain: Record<string, MacroChainNode>;
  scenario: MacroScenario;
  scorecard: MacroScorecard;
};

export type MacroSemanticRecord = Record<string, unknown>;

export type MacroModuleSnapshot = {
  module_id: string;
  route_path: string;
  title: string;
  asof_label?: string | null;
  question?: string | null;
  section?: string | null;
  projection_version?: string | null;
  status?: string | null;
  status_label?: string | null;
  subtitle?: string | null;
  asof_date?: string | null;
  source_snapshot_id?: string | null;
  source_projection_version?: string | null;
  computed_at_ms?: number | null;
  [key: string]: unknown;
};

export type MacroModuleTile = {
  concept_key?: string | null;
  description?: string | null;
  delta_label?: string | null;
  display_value?: string | null;
  history_points?: number | null;
  label?: string | null;
  observed_at?: string | null;
  observed_at_label?: string | null;
  quality?: string | null;
  quality_label?: string | null;
  score_participation?: boolean | null;
  short_label?: string | null;
  source_label?: string | null;
  unit?: string | null;
  unit_label?: string | null;
  value?: number | string | null;
  data_gaps?: unknown[];
  [key: string]: unknown;
};

export type MacroModuleChart = {
  id: string;
  kind?: string | null;
  min_points?: number | null;
  status?: string | null;
  status_label?: string | null;
  subtitle?: string | null;
  title?: string | null;
  missing_concept_keys?: string[];
  series?: MacroSemanticRecord[];
  [key: string]: unknown;
};

export type MacroModuleTable = {
  id: string;
  columns?: MacroSemanticRecord[];
  source?: MacroSemanticRecord;
  status?: string | null;
  title?: string | null;
  missing_concept_keys?: string[];
  rows?: MacroSemanticRecord[];
  [key: string]: unknown;
};

export type MacroRelatedRoute = {
  href: string;
  label: string;
};

export type MacroDataHealth = {
  summary_status?: string | null;
  summary_label?: string | null;
  module_gaps: MacroSemanticRecord[];
  chart_gaps: MacroSemanticRecord[];
  global_gaps: MacroSemanticRecord[];
};

export type MacroTransmissionNode = {
  key?: string | null;
  label?: string | null;
  value?: unknown;
  kind?: string | null;
  status?: string | null;
  status_label?: string | null;
};

export type MacroModuleView = {
  snapshot: MacroModuleSnapshot;
  tiles: MacroModuleTile[];
  primary_chart: MacroModuleChart;
  tables: MacroModuleTable[];
  module_read: MacroSemanticRecord;
  module_evidence: Record<string, MacroSemanticRecord[]>;
  transmission: MacroTransmissionNode[];
  data_health: MacroDataHealth;
  provenance: MacroSemanticRecord;
  related_routes: MacroRelatedRoute[];
  [key: string]: unknown;
};

export type MacroSeriesPoint = {
  observed_at?: string | null;
  value?: number | string | null;
  source_name?: string | null;
  data_quality?: string | null;
  [key: string]: unknown;
};

export type MacroSeriesPayload = {
  concept_key: string;
  unit?: string | null;
  sources?: string[];
  latest_observed_at?: string | null;
  data_quality?: string | null;
  points?: MacroSeriesPoint[];
  data_gaps?: unknown[];
  [key: string]: unknown;
};

export type MacroSeriesData = {
  window: string;
  series: Record<string, MacroSeriesPayload>;
  data_gaps: unknown[];
};

export type MacroAssetCorrelationAsset = {
  concept_key: string;
  title: string;
  observations_count: number;
  return_count: number;
  start_date?: string | null;
  end_date?: string | null;
  latest_observed_at?: string | null;
  sources: string[];
};

export type MacroAssetCorrelationMatrixRow = {
  concept_key: string;
  correlations: Record<string, number | null>;
};

export type MacroAssetCorrelationPair = {
  left: string;
  right: string;
  correlation: number | null;
  sample_size: number;
  start_date?: string | null;
  end_date?: string | null;
  available: boolean;
  reason?: string | null;
};

export type MacroAssetCorrelationGap = {
  code: string;
  concept_key?: string | null;
  label?: string | null;
  left?: string | null;
  right?: string | null;
  sample_size?: number | null;
};

export type MacroAssetCorrelationWindow = "20d" | "60d" | "120d";

export type MacroAssetCorrelationData = {
  window: MacroAssetCorrelationWindow;
  assets: MacroAssetCorrelationAsset[];
  matrix: MacroAssetCorrelationMatrixRow[];
  pairs: MacroAssetCorrelationPair[];
  data_gaps: MacroAssetCorrelationGap[];
  asof_date?: string | null;
};

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
  symbol?: string | null;
  pricefeed_id?: string | null;
  price?: TokenMessagePrice | null;
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

export type LiveMarketUpdatePayload = {
  type: "live_market_update";
  target_type: string;
  target_id: string;
  provider?: string | null;
  observed_at_ms?: number | null;
  market: {
    decision_latest: MarketObservationSnapshot;
  };
};

export type RecentData = {
  scope: ScopeKey;
  events: EventRecord[];
  items: LivePayload[];
};

export type WatchlistHandleRowOverview = components["schemas"]["WatchlistHandleRowOverview"];
export type WatchlistHandlesOverviewData = components["schemas"]["WatchlistHandlesOverviewData"];
export type WatchlistOverviewCluster = components["schemas"]["WatchlistOverviewCluster"];
export type WatchlistHandleOverviewData = components["schemas"]["WatchlistHandleOverviewData"];

export type WatchlistSocialEvent = {
  event_type?: string | null;
  source_action?: string | null;
  subject?: string | null;
  direction_hint?: string | null;
  attention_mechanism?: string | null;
  impact_hint?: number | null;
  semantic_novelty_hint?: number | null;
  confidence?: number | null;
  is_signal_event?: boolean | null;
  anchor_terms?: Array<Record<string, unknown>>;
  token_candidates?: Array<Record<string, unknown>>;
  semantic_risks?: string[];
  summary_zh?: string | null;
};

export type WatchlistTimelineItem = {
  event_id: string;
  received_at_ms: number;
  author_handle?: string | null;
  action?: string | null;
  text_clean?: string | null;
  canonical_url?: string | null;
  cashtags?: string[];
  hashtags?: string[];
  mentions?: string[];
  event?: EventRecord;
  token_resolutions?: TokenResolutionRecord[];
  social_event?: WatchlistSocialEvent | null;
};

export type WatchlistHandleTimelineData = {
  query: {
    handle: string;
    scope: WatchlistTimelineScope;
    limit: number;
  };
  items: WatchlistTimelineItem[];
  has_more: boolean;
  next_cursor?: string | null;
};

export type SearchItem = {
  event: EventRecord;
  match_type: string;
  score: number;
  match_reasons: string[];
  target?: SearchTargetCandidate | null;
  route_scores: Record<string, number>;
};

export type SearchTargetCandidate = {
  target_type: "Asset" | "CexToken" | string;
  target_id: string;
  symbol?: string | null;
  chain_id?: string | null;
  address?: string | null;
  status: string;
  source: string;
  reason: string;
};

export type SearchData = {
  query: Record<string, unknown>;
  page: {
    returned_count: number;
    has_more: boolean;
    next_cursor?: string | null;
  };
  target_candidates: SearchTargetCandidate[];
  items: SearchItem[];
};

export type SearchInspectResultKind =
  | "token_result"
  | "topic_result"
  | "ambiguous_result"
  | "empty_result";

export type SearchAgentBrief = {
  schema_version: "search_agent_brief_v1" | string;
  generated_by: "deterministic" | string;
  project_summary: {
    one_liner: string;
    summary_zh: string;
    current_state: string;
    data_gaps: string[];
    evidence_event_ids: string[];
  };
  propagation: {
    summary_zh: string;
    phases: Array<{
      phase: string;
      window_label: string;
      tweets: number;
      authors: number;
      lead_accounts: string[];
      read_zh: string;
      evidence_event_ids: string[];
    }>;
    key_accounts: Array<{
      handle: string;
      role: string;
      posts: number;
      first_seen_ms?: number | null;
    }>;
  };
  bull_bear: {
    stance: "watch" | "research" | "avoid" | "unknown" | string;
    bull: {
      thesis_zh: string;
      evidence_event_ids: string[];
      triggers_zh: string[];
    };
    bear: {
      thesis_zh: string;
      evidence_event_ids: string[];
      invalidations_zh: string[];
    };
  };
};

export type NarrativeStatus =
  | "ready"
  | "pending"
  | "insufficient"
  | "semantic_unavailable"
  | string;

export type NarrativeCurrentnessDisplayStatus =
  | "current"
  | "updating"
  | "stale"
  | "not_ready"
  | "out_of_frontier"
  | "unsupported_window"
  | string;

export type NarrativeCurrentness = {
  display_status: NarrativeCurrentnessDisplayStatus;
  epoch_id?: string | null;
  epoch_policy_version?: string | null;
  ready_source_fingerprint?: string | null;
  current_source_fingerprint?: string | null;
  ready_source_event_count?: number | null;
  current_source_event_count?: number | null;
  delta_source_event_count?: number | null;
  delta_independent_author_count?: number | null;
  delta_since_ms?: number | null;
  last_ready_computed_at_ms?: number | null;
  next_refresh_due_at_ms?: number | null;
  reason?: string | null;
  [key: string]: unknown;
};

export type EvidenceRef = {
  ref_id?: string | null;
  ref_type:
    | "event"
    | "author"
    | "market"
    | "data_gap"
    | "narrative_cluster"
    | "pulse_packet"
    | string;
  event_id?: string | null;
  handle?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  label?: string | null;
  detail?: string | null;
  url?: string | null;
};

export type NarrativeArgument = {
  thesis_zh: string;
  bullets_zh?: string[];
  evidence_refs: EvidenceRef[];
  evidence_event_ids?: string[];
  confidence?: number | null;
};

export type TokenMentionSemantic = {
  status: NarrativeStatus;
  trade_stance:
    | "bullish"
    | "bearish"
    | "neutral"
    | "skeptical"
    | "exit-risk"
    | "research-only"
    | "unknown"
    | string;
  attention_valence:
    | "positive"
    | "negative"
    | "mixed"
    | "ironic"
    | "hostile"
    | "panic"
    | "celebratory"
    | "informational"
    | "unknown"
    | string;
  narrative_cluster_key?: string | null;
  narrative_cluster_title?: string | null;
  claim_type?: string | null;
  evidence_type?: string | null;
  semantic_confidence?: number | null;
  co_mentioned_targets?: SearchTargetCandidate[];
  evidence_refs?: EvidenceRef[];
  summary_zh?: string | null;
  data_gaps?: string[];
};

export type NarrativeCluster = {
  cluster_key: string;
  title: string;
  summary_zh: string;
  status?: NarrativeStatus;
  propagation_state?: string | null;
  attention_valence?: string | null;
  trade_stance?: string | null;
  mention_count?: number | null;
  author_count?: number | null;
  lead_accounts?: Array<{
    handle: string;
    role?: string | null;
    posts?: number | null;
    first_seen_ms?: number | null;
  }>;
  evidence_refs: EvidenceRef[];
  data_gaps?: string[];
};

export type TokenDiscussionDigest = {
  schema_version?: string | null;
  status: NarrativeStatus;
  currentness: NarrativeCurrentness;
  analysis_window?: string | null;
  source_window?: string | null;
  surface_window?: string | null;
  reuse_reason?: string | null;
  generated_at_ms?: number | null;
  computed_at_ms?: number | null;
  stale?: boolean | null;
  dominant_narrative?: {
    title: string;
    summary_zh: string;
    propagation_state?: string | null;
    trade_stance?: string | null;
    attention_valence?: string | null;
    evidence_refs: EvidenceRef[];
  } | null;
  coverage?: {
    semantic_coverage?: number | null;
    labeled_mentions?: number | null;
    source_mentions?: number | null;
    independent_authors?: number | null;
  } | null;
  stance_mix?: Partial<Record<TokenMentionSemantic["trade_stance"], number>>;
  attention_valence_mix?: Partial<Record<TokenMentionSemantic["attention_valence"], number>>;
  propagation?: {
    state: string;
    summary_zh: string;
    evidence_refs: EvidenceRef[];
  } | null;
  bull_bear?: {
    stance: "watch" | "research" | "avoid" | "unknown" | string;
    bull: NarrativeArgument;
    bear: NarrativeArgument;
  } | null;
  timeline_pills?: Array<{ label: string; tone?: string | null; evidence_refs?: EvidenceRef[] }>;
  processing?: {
    backlog?: {
      semantic?: number | null;
      retryable?: number | null;
      unavailable?: number | null;
      oldest_due_age_ms?: number | null;
    } | null;
  } | null;
  key_accounts?: Array<{
    handle: string;
    role: string;
    posts: number;
    first_seen_ms?: number | null;
    evidence_refs?: EvidenceRef[];
  }>;
  data_gaps: Array<
    | string
    | {
        code?: string | null;
        message?: string | null;
        reason?: string | null;
        [key: string]: unknown;
      }
  >;
  evidence_refs?: EvidenceRef[];
};

export type PulseOverlay = {
  status: "ready" | "hidden" | "unavailable" | string;
  pulse_status?: SignalPulseStatus | string | null;
  display_status?: string | null;
  evidence_packet_hash?: string | null;
  verdict?: string | null;
  summary_zh?: string | null;
  recommendation?: string | null;
  confidence?: number | null;
  updated_at_ms?: number | null;
  evidence_refs?: EvidenceRef[];
  data_gaps?: string[];
};

export type TokenProfileBlock = {
  status: "ready" | "pending" | "missing" | "unsupported" | "error" | string;
  provider?: string | null;
  observed_at_ms?: number | null;
  identity?: {
    symbol?: string | null;
    name?: string | null;
    logo_url?: string | null;
    banner_url?: string | null;
    description?: string | null;
  } | null;
  links?: {
    website_url?: string | null;
    twitter_url?: string | null;
    twitter_username?: string | null;
    telegram_url?: string | null;
    gmgn_url?: string | null;
    geckoterminal_url?: string | null;
  } | null;
  source?: {
    provider?: string | null;
    source_kind?: string | null;
    source_ref?: string | null;
    quality_flags?: string[] | null;
    raw_available?: boolean | null;
    last_error?: string | null;
  } | null;
};

export type LiveMarketSnapshot = MarketObservationSnapshot & {
  status?: "ready" | "missing" | "unsupported" | "error" | "stale" | string | null;
  error?: string | null;
  message?: string | null;
  stale?: boolean | null;
  readiness?: Partial<MarketReadiness> | null;
  [key: string]: unknown;
};

export type CexLevelBand = {
  kind?: string | null;
  price?: number | null;
  score?: number | null;
  side?: string | null;
  [key: string]: unknown;
};

export type CexDetailSnapshot = {
  snapshot_id?: string | null;
  target_type?: "CexToken" | string | null;
  target_id?: string | null;
  exchange?: string | null;
  native_market_id?: string | null;
  base_symbol?: string | null;
  quote_symbol?: string | null;
  status?: string | null;
  baseline_status?: string | null;
  coinglass_status?: string | null;
  price_usd?: number | null;
  mark_price?: number | null;
  funding_rate?: number | null;
  volume_24h_usd?: number | null;
  open_interest_usd?: number | null;
  oi_change_pct_1h?: number | null;
  oi_change_pct_4h?: number | null;
  oi_change_pct_24h?: number | null;
  cvd_delta_1h?: number | null;
  cvd_delta_4h?: number | null;
  cvd_delta_24h?: number | null;
  long_short_ratio?: number | null;
  top_trader_position_ratio?: number | null;
  level_bands?: CexLevelBand[] | null;
  degraded_reasons?: string[] | null;
  source_refs?: Array<{ ref_id?: string | null; [key: string]: unknown }> | null;
  observed_at_ms?: number | null;
  computed_at_ms?: number | null;
  [key: string]: unknown;
};

export type TokenCasePostsQuery = Omit<TokenPostsQuery, "scope"> & {
  scope: TokenCaseApiScope;
};

export type TokenCasePostsData = Omit<TokenPostsData, "query"> & {
  query: TokenCasePostsQuery;
};

export type TokenCaseSocialTimelineQuery = Omit<TokenSocialTimelineQuery, "scope"> & {
  scope: TokenCaseApiScope;
};

export type TokenCaseSocialTimelineData = Omit<TokenSocialTimelineData, "query"> & {
  query: TokenCaseSocialTimelineQuery;
};

export type TokenCaseDossier = {
  target: SearchTargetCandidate;
  profile?: TokenProfileBlock | null;
  timeline: TokenCaseSocialTimelineData;
  posts: TokenCasePostsData;
  discussion_digest: TokenDiscussionDigest;
  narrative_clusters: NarrativeCluster[];
  pulse_overlay?: PulseOverlay | null;
  market_live: LiveMarketSnapshot;
  cex_detail?: CexDetailSnapshot | null;
};

export type SearchTokenResult = TokenCaseDossier;

export type SearchTopicResult = {
  summary: {
    posts: number;
    authors: number;
  };
  items: SearchItem[];
  agent_brief: SearchAgentBrief;
};

export type SearchAmbiguousResult = {
  candidates: SearchTargetCandidate[];
  summary: {
    posts: number;
    authors: number;
  };
  items: SearchItem[];
  agent_brief: SearchAgentBrief;
};

export type SearchInspectData = {
  query: {
    q: string;
    normalized_q: string;
    window: WindowKey;
    scope: ScopeKey;
    result_kind: SearchInspectResultKind;
  };
  resolver: {
    confidence: number;
    target_candidates: SearchTargetCandidate[];
    selected_target?: SearchTargetCandidate | null;
    reasons: string[];
  };
  token_result?: SearchTokenResult | null;
  topic_result?: SearchTopicResult | null;
  ambiguous_result?: SearchAmbiguousResult | null;
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
  mentions_4h: number;
  mentions_24h: number;
  mentions_window: number;
  unique_authors: number;
  watched_mentions: number;
  latest_seen_ms: number;
  previous_mentions: number;
  mention_delta: number;
  mention_delta_pct: number | null;
  z_score: number | null;
  z_ewma: number | null;
  robust_z: number | null;
  new_burst_score: number | null;
  stream_share: number;
  baseline_version: string;
  baseline_status: string;
  baseline_sample_count: number;
  baseline_nonzero_sample_count: number;
  zero_slot_count: number;
};

export type TokenRadarIntentBlock = {
  intent_id?: string | null;
  display_symbol?: string | null;
  display_name?: string | null;
  evidence?: unknown[];
};

export type TokenRadarDataHealth = {
  identity?: string | null;
  market?: string | null;
  coverage?: string | null;
  [key: string]: unknown;
};

export type MarketObservationSnapshot = {
  target_type?: string | null;
  target_id?: string | null;
  source?: "event_anchor" | "decision_latest" | string | null;
  provider?: string | null;
  pricefeed_id?: string | null;
  price_usd?: number | null;
  price_quote?: number | null;
  quote_symbol?: string | null;
  price_basis?: string | null;
  market_cap_usd?: number | null;
  liquidity_usd?: number | null;
  holders?: number | null;
  volume_24h_usd?: number | null;
  open_interest_usd?: number | null;
  observed_at_ms?: number | null;
  received_at_ms?: number | null;
  raw_payload_hash?: string | null;
};

export type MarketReadiness = {
  anchor_status: "ready" | "missing" | "stale" | string;
  latest_status: "live" | "ready" | "stale" | "missing" | string;
  dex_floor_status: "ready" | "missing_fields" | "not_applicable" | string;
  missing_fields: string[];
  stale_fields: string[];
};

export type MarketContext = {
  event_anchor: MarketObservationSnapshot | null;
  decision_latest: MarketObservationSnapshot | null;
  readiness: MarketReadiness;
  capture_method?: string | null;
  capture_reason?: string | null;
  tick_lag_ms?: number | null;
};

export type TokenRadarRowMeta = {
  lane?: "resolved" | "attention" | string | null;
  rank?: number | null;
  listed_at_ms?: number | null;
  computed_at_ms?: number | null;
  source_max_received_at_ms?: number | null;
};

export type AssetFlowRow = {
  intent?: TokenRadarIntentBlock;
  target?: AssetFlowTargetBlock;
  attention: AssetFlowAttentionBlock;
  source_event_ids?: string[];
  market: MarketContext;
  radar?: TokenRadarRowMeta;
  discussion_digest?: TokenDiscussionDigest | null;
  pulse_overlay?: PulseOverlay | null;
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
  factor_snapshot: TokenFactorSnapshot;
  profile?: TokenProfileBlock | null;
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
    status: "fresh" | "stale" | "pending" | string;
    version: string;
    source: string;
    reason?: string | null;
    row_count?: number | null;
    source_rows?: number | null;
    source_max_received_at_ms?: number | null;
    computed_at_ms?: number | null;
    error?: string | null;
  };
};

export type StockQuoteSnapshot = {
  status: "ready" | "unavailable" | string;
  price?: number | null;
  reference_close_price?: number | null;
  change_pct?: number | null;
  asof?: string | null;
  provider?: string | null;
  provider_symbol?: string | null;
  latency_class?: string | null;
  freshness_class?: string | null;
  error?: string | null;
};

export type StockRadarRow = {
  target: {
    target_type: "MarketInstrument" | string;
    target_id: string;
    symbol: string;
    market?: "us_equity" | string | null;
    exchange?: string | null;
    instrument_type?: string | null;
    name?: string | null;
  };
  attention: {
    mentions: number;
    unique_authors: number;
    watched_mentions: number;
    latest_seen_ms?: number | null;
  };
  latest_event: {
    event_id?: string | null;
    author_handle?: string | null;
    text?: string | null;
    received_at_ms?: number | null;
  };
  quote: StockQuoteSnapshot;
  source_event_ids: string[];
  row_health: string[];
};

export type StocksRadarData = {
  window: WindowKey;
  scope: ScopeKey;
  query: {
    window: WindowKey;
    scope: ScopeKey;
    limit: number;
    window_start_ms: number;
    window_end_ms: number;
  };
  rows: StockRadarRow[];
  health: {
    returned_count: number;
    quote_ready_count: number;
    quote_unavailable_count: number;
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
  event_anchor: MarketObservationSnapshot | null;
  decision_latest: MarketObservationSnapshot | null;
  readiness: MarketReadiness;
  market_status: "fresh" | "partial" | "stale" | "missing" | string;
  price?: number | null;
  price_status?: string | null;
  market_cap?: number | null;
  market_cap_status?: string | null;
  liquidity?: number | null;
  liquidity_status?: string | null;
  pool_status?: "ready" | "missing" | string;
  holder_count?: number | null;
  holder_count_status?: string | null;
  volume_24h?: number | null;
  volume_24h_status?: string | null;
  provider?: string | null;
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
  market_observation_status?:
    | "ready"
    | "pending"
    | "running"
    | "provider_not_configured"
    | "provider_not_found"
    | "provider_error"
    | "rate_limited"
    | "dead"
    | string;
  price_change_status:
    | "ready"
    | "pending_observation"
    | "insufficient_history"
    | "missing_market"
    | "provider_not_configured"
    | "provider_not_found"
    | "provider_error"
    | "rate_limited"
    | "dead"
    | string;
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
  top_authors: Array<{
    handle?: string | null;
    count?: number;
    posts?: number;
    followers?: number | null;
    watched_count?: number;
    role?: string | null;
  }>;
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
  scope: TokenCaseApiScope;
  range: TokenPostRange;
  sort?: TokenPostServerSort;
};

export type TokenSocialTimelineParams = {
  target_type?: string | null;
  target_id?: string | null;
  window: WindowKey;
  scope: TokenCaseApiScope;
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
  profile?: TokenProfileBlock | null;
  discussion_digest?: TokenDiscussionDigest | null;
  pulse_overlay?: PulseOverlay | null;
  factor_data_health?: TokenFactorSnapshot["data_health"];
  factor_gates?: TokenFactorSnapshot["gates"];
  factor_normalization?: TokenFactorSnapshot["normalization"];
  radar?: TokenRadarRowMeta;
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
  symbol?: string | null;
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
  semantic?: TokenMentionSemantic | null;
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
  author_handle?: string | null;
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
  semantic?: TokenMentionSemantic | null;
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

export type TokenTimelineMarketCandles = {
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
  price_series_type?: "anchor_line" | "ohlc" | string | null;
  candle_status?:
    | "ready"
    | "empty"
    | "unsupported"
    | "missing_target"
    | "missing_identity"
    | "missing_market_id"
    | "error"
    | string
    | null;
  candle_source?: string | null;
  candle_bar?: string | null;
  candle_error?: string | null;
  candles?: MarketCandle[];
  [key: string]: unknown;
};

export type MarketCandle = {
  time_ms: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  volume_quote?: number | null;
  volume_usd?: number | null;
  confirmed?: boolean | null;
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
  market_candles?: TokenTimelineMarketCandles | null;
  stages: TokenTimelineStage[];
  buckets: TokenTimelineBucket[];
  authors: TokenTimelineAuthor[];
  posts: TokenTimelinePost[];
  cascade: TokenTimelineCascade;
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
};

export type SignalPulseStatus = "trade_candidate" | "token_watch" | "risk_rejected_high_info";
export type SignalPulseStatusFilter = "all" | SignalPulseStatus;
export type SignalPulseVisibilityFilter = "public" | "hidden";

export type SignalPulseQuery = {
  window: WindowKey;
  scope: ScopeKey;
  status?: SignalPulseStatus | null;
  visibility?: SignalPulseVisibilityFilter | null;
  handle?: string | null;
  q?: string | null;
};

export type SignalPulseHealth = {
  pulse_ready: boolean;
  public_ready?: boolean | null;
  candidate_count: number;
  public_candidate_count?: number | null;
  hidden_candidate_count?: number | null;
  blocked_low_information_count: number;
  dead_job_count: number;
  market_ready_rate: number;
  window?: string | null;
  scope?: string | null;
  since_hours?: number | null;
  publish_status?: "healthy" | "degraded" | "hold_publish" | string | null;
  reasons?: string[];
  latest_packet_created_at_ms?: number | null;
  latest_agent_run_finished_at_ms?: number | null;
  latest_public_candidate_updated_at_ms?: number | null;
  latest_hidden_hold_candidate_updated_at_ms?: number | null;
  due_jobs?: number | null;
  claimed_jobs?: number | null;
  failed_jobs_4h?: number | null;
  agent_runs_4h?: number | null;
  agent_failed_4h?: number | null;
  agent_failure_rate_4h?: number | null;
  unknown_ref_failures_4h?: number | null;
  unknown_ref_failure_rate_4h?: number | null;
  unsupported_claim_failures_4h?: number | null;
  unsupported_claim_failure_rate_4h?: number | null;
  hidden_abstain_4h?: number | null;
  hidden_hold_publish_4h?: number | null;
  hidden_insufficient_evidence_4h?: number | null;
  public_candidates_4h?: number | null;
};

export type SignalPulseSummary = Record<SignalPulseStatus, number> & {
  decision_route_counts?: Record<string, number>;
  decision_recommendation_counts?: Record<string, number>;
  decision_abstain_reason_counts?: Record<string, number>;
  decision_error_count?: number;
};

export type FactorPoint = {
  family: string;
  key: string;
  raw_value?: unknown;
  score?: number | null;
  confidence?: number | null;
  data_health?: string | null;
  freshness_ms?: number | null;
  source_refs?: string[];
  risk_flags?: string[];
};

export type TokenFactorFamilyKey =
  | "social_heat"
  | "social_propagation"
  | "semantic_catalyst"
  | "timing_risk";

export type TokenFactorFamily = {
  raw_score: number;
  score: number;
  weight: number;
  facts: Record<string, unknown>;
  factors: Record<string, FactorPoint>;
  data_health: string;
};

export type TokenFactorSnapshot = {
  schema_version: "token_factor_snapshot_v3_social_attention";
  subject: {
    target_type?: string | null;
    target_id?: string | null;
    symbol?: string | null;
    target_market_type?: string | null;
    chain?: string | null;
    address?: string | null;
    pricefeed_id?: string | null;
  };
  market: MarketContext;
  gates: {
    eligible_for_high_alert: boolean;
    max_decision?: string | null;
    blocked_reasons: string[];
    risk_reasons?: string[];
  };
  data_health: {
    identity: string;
    market: string;
    social: string;
    alpha: string;
    [key: string]: unknown;
  };
  families: Record<TokenFactorFamilyKey, TokenFactorFamily>;
  normalization: {
    status?: string | null;
    cohort?: Record<string, unknown>;
    factor_ranks?: Record<string, unknown>;
    alpha_rank?: number | null;
    cohort_size?: number | null;
    [key: string]: unknown;
  };
  composite: {
    raw_alpha_score?: number | null;
    rank_score?: number | null;
    recommended_decision: string;
    family_scores?: Record<string, number | null | undefined>;
  };
  provenance: {
    source_event_ids: string[];
    computed_at_ms: number;
  };
};

export type BullBearView = {
  strength: "absent" | "weak" | "moderate" | "strong";
  thesis_zh: string;
  supporting_event_ids: string[];
};

export type TradePlaybook = {
  has_playbook: boolean;
  watch_signals: string[];
  exit_triggers: string[];
  monitoring_horizon: "1h" | "4h" | "24h";
};

export type PulseDecision = {
  route: "cex" | "meme" | "research_only" | string;
  recommendation:
    | "high_conviction"
    | "trade_candidate"
    | "watchlist"
    | "ignore"
    | "abstain"
    | string;
  confidence?: number | null;
  abstain_reason?: string | null;
  stage_count?: number | null;
  summary_zh: string;
  invalidation_conditions: string[];
  residual_risks: string[];
  evidence_event_ids?: string[];
  supporting_evidence_refs?: string[];
  risk_evidence_refs?: string[];
  data_gap_refs?: string[];
  // v2 新字段 — 全部可选 + 缺时前端 fallback 显示 "—"
  narrative_archetype?: string;
  narrative_thesis_zh?: string;
  bull_view?: BullBearView | null;
  bear_view?: BullBearView | null;
  playbook?: TradePlaybook | null;
  evidence_event_urls?: Record<string, string>;
};

export type SignalPulseItem = {
  candidate_id: string;
  candidate_type: string;
  subject_key: string;
  target_type?: string | null;
  target_id?: string | null;
  symbol?: string | null;
  window: WindowKey | string;
  scope: ScopeKey | string;
  evidence_status?: string | null;
  decision_status?: string | null;
  display_status?: string | null;
  evidence_packet_hash?: string | null;
  verdict?: string | null;
  social_phase?: string | null;
  candidate_score?: number | null;
  score_band?: string | null;
  evidence_event_ids: string[];
  source_event_ids: string[];
  factor_snapshot: TokenFactorSnapshot;
  decision: PulseDecision;
  gate: Record<string, unknown>;
  claim_verification?: Record<string, unknown> | null;
  evidence_gate?: Record<string, unknown> | null;
  fact_card: Record<string, unknown>;
  pulse_version?: string | null;
  gate_version?: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  created_at_ms: number;
  updated_at_ms: number;
  playbooks: unknown[];
};

export type SignalPulseData = {
  query: SignalPulseQuery;
  health: SignalPulseHealth;
  summary: SignalPulseSummary;
  items: SignalPulseItem[];
  returned_count: number;
  has_more: boolean;
  next_cursor?: string | null;
};

export type SourceEventDetail = {
  event_id: string;
  timestamp_ms: number;
  source_provider: string;
  channel: string;
  action: "tweet" | "quote" | "repost" | "reply" | string;
  author_handle: string | null;
  author_name: string | null;
  author_followers: number | null;
  author_watched: boolean;
  text_clean: string | null;
  canonical_url: string | null;
};

export type SourceEventsByIdsData = {
  events: SourceEventDetail[];
  not_found: string[];
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

export type WorkerStatusData = {
  enabled: boolean;
  running: boolean;
  last_started_at_ms?: number | null;
  last_finished_at_ms?: number | null;
  last_result?: Record<string, unknown> | null;
  last_error?: string | null;
  iteration_duration_p99_ms?: number | null;
  queue_depth?: number | null;
  pool_wait_ms_p99?: number | null;
  details?: Record<string, unknown>;
};

export type StatusData = {
  ok: boolean;
  reasons: string[];
  handles: string[];
  store: string;
  snapshot_gate?: Record<string, unknown>;
  db?: Record<string, unknown> | null;
  provider_states?: Record<string, unknown>;
  workers: Record<string, WorkerStatusData> & {
    collector: WorkerStatusData;
  };
};
