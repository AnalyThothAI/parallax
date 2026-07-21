from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JsonObject = dict[str, Any]


class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExactApiSchema(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApiEnvelope[T](ExactApiSchema):
    ok: bool
    data: T | None = None
    error: str | None = None
    field: str | None = None


class AgentExecutionStatusData(ExactApiSchema):
    lane: Literal["news.story_brief"]
    model: str
    provider_family: str
    output_strategy: Literal["json_object"]
    schema_enforcement: Literal["client_validate"]
    max_concurrency: int
    rpm_limit: int
    timeout_seconds: float
    in_flight: int
    provider_running: int
    circuit_state: Literal["open", "closed"]
    circuit_open_until_ms: int | None
    capacity_denied_total: int
    circuit_open_total: int
    timeout_total: int
    last_denied_at_ms: int | None
    last_timeout_at_ms: int | None
    oldest_in_flight_age_ms: float | None


class AgentExecutionUnavailableData(ExactApiSchema):
    status: Literal["unavailable"]
    error: str


class BootstrapData(ExactApiSchema):
    ws_token: str
    handles: list[str]
    replay_limit: int


class StatusData(ExactApiSchema):
    ok: bool
    reasons: list[str]
    handles: list[str]
    store: Literal["postgresql"]
    snapshot_gate: JsonObject
    db: JsonObject
    provider_states: dict[str, JsonObject]
    agent_execution: AgentExecutionStatusData | AgentExecutionUnavailableData | None
    news_provider_contract: JsonObject
    workers: dict[str, WorkerStatusData]


class ReadinessData(ExactApiSchema):
    ok: bool
    reasons: list[str]
    handles: list[str]
    store: Literal["postgresql"]
    db: JsonObject
    composition: JsonObject


class WorkerStatusData(ExactApiSchema):
    enabled: bool
    running: bool
    effective_status: Literal[
        "disabled",
        "intentionally_not_started",
        "unavailable",
        "degraded",
        "running",
        "stopped",
        "failed",
    ]
    unavailable_reason: str | None
    last_started_at_ms: int | None
    last_finished_at_ms: int | None
    last_result: JsonObject | None
    last_error: str | None
    iteration_duration_p99_ms: float | None


class MacroSnapshotData(ExactApiSchema):
    projection_version: str
    asof_date: date
    status: str
    regime: str
    overall_score: int | float | None
    computed_at_ms: int


class MacroCurrentnessData(ExactApiSchema):
    publication_status: str | None
    publication_row_count: int | None
    publication_finished_at_ms: int | None
    facts_max_observed_at: date | None
    projection_lag_days: int | None
    projection_behind_facts: bool


class MacroData(ExactApiSchema):
    snapshot: MacroSnapshotData | None
    currentness: MacroCurrentnessData
    panels: JsonObject
    indicators: JsonObject
    triggers: list[JsonObject]
    data_gaps: list[JsonObject]
    source_coverage: JsonObject
    features: JsonObject
    chain: JsonObject
    scenario: JsonObject
    scorecard: JsonObject


class MacroAssetCorrelationAssetData(ExactApiSchema):
    concept_key: str
    title: str
    observations_count: int
    return_count: int
    start_date: date | None
    end_date: date | None
    latest_observed_at: date | None
    sources: list[str]


class MacroAssetCorrelationMatrixRowData(ExactApiSchema):
    concept_key: str
    correlations: dict[str, float | None]


class MacroAssetCorrelationPairData(ExactApiSchema):
    left: str
    right: str
    correlation: float | None
    sample_size: int
    start_date: date | None
    end_date: date | None
    available: bool
    reason: str | None


class MacroAssetCorrelationGapData(ExactApiSchema):
    code: Literal["insufficient_history", "insufficient_overlap", "zero_variance"]
    sample_size: int
    concept_key: str | None = None
    left: str | None = None
    right: str | None = None


class MacroAssetCorrelationData(ExactApiSchema):
    window: Literal["20d", "60d", "120d"]
    assets: list[MacroAssetCorrelationAssetData]
    matrix: list[MacroAssetCorrelationMatrixRowData]
    pairs: list[MacroAssetCorrelationPairData]
    data_gaps: list[MacroAssetCorrelationGapData]
    asof_date: date | None


class MacroSeriesPointData(ExactApiSchema):
    observed_at: date
    value: int | float | None
    source_name: str | None
    data_quality: str


class MacroSeriesGapData(ExactApiSchema):
    code: str
    label: str
    severity: str
    score_participation: bool
    concept_key: str


class MacroSeriesItemData(ExactApiSchema):
    concept_key: str
    status: Literal["ok", "missing", "insufficient_history"]
    unit: str | None
    sources: list[str]
    latest_observed_at: date | None
    data_quality: str
    points: list[MacroSeriesPointData]
    data_gaps: list[MacroSeriesGapData]


class MacroSeriesData(ExactApiSchema):
    window: Literal["20d", "60d", "120d", "1y", "3y"]
    series: dict[str, MacroSeriesItemData]
    data_gaps: list[MacroSeriesGapData]


class MacroModuleSnapshotData(ExactApiSchema):
    module_id: str
    route_path: str
    title: str
    subtitle: str
    question: str
    section: str
    projection_version: str
    status: str
    status_label: str
    asof_date: date
    asof_label: str
    computed_at_ms: int
    computed_at_label: str
    source_projection_version: str


class MacroModuleChartPointData(ExactApiSchema):
    observed_at: date
    value: int | float


class MacroModuleChartSeriesData(ExactApiSchema):
    concept_key: str
    label: str
    unit_label: str
    points: list[MacroModuleChartPointData]


class MacroModuleChartData(ExactApiSchema):
    id: str
    kind: Literal["time_series"]
    title: str
    subtitle: str
    status: str
    status_label: str
    min_points: int
    missing_concept_keys: list[str]
    series: list[MacroModuleChartSeriesData]


class MacroModuleTableColumnData(ExactApiSchema):
    key: str
    label: str


class MacroModuleTableData(ExactApiSchema):
    id: str
    title: str
    status: str
    missing_concept_keys: list[str]
    columns: list[MacroModuleTableColumnData]
    rows: list[JsonObject]


class MacroModuleAvailabilityTableData(ExactApiSchema):
    id: Literal["availability_proxy_notes"]
    title: str
    status: str
    rows: list[JsonObject]


class MacroModuleEvidenceData(ExactApiSchema):
    confirmations: list[JsonObject]
    contradictions: list[JsonObject]
    watch_triggers: list[JsonObject]
    invalidations: list[JsonObject]


class MacroModuleDataHealthData(ExactApiSchema):
    summary_status: str
    summary_label: str
    module_gaps: list[JsonObject]
    chart_gaps: list[JsonObject]
    global_gaps: list[JsonObject]


class MacroModuleProvenanceCurrentnessData(ExactApiSchema):
    facts_max_observed_at: date | None
    projection_lag_days: int | None
    projection_behind_facts: bool


class MacroModuleProvenanceData(ExactApiSchema):
    projection_version: str
    currentness: MacroModuleProvenanceCurrentnessData
    rows: list[JsonObject]


class MacroModuleData(ExactApiSchema):
    snapshot: MacroModuleSnapshotData
    tiles: list[JsonObject]
    primary_chart: MacroModuleChartData
    tables: list[MacroModuleTableData | MacroModuleAvailabilityTableData]
    module_read: JsonObject
    module_evidence: MacroModuleEvidenceData
    transmission: list[JsonObject]
    data_health: MacroModuleDataHealthData
    provenance: MacroModuleProvenanceData
    related_routes: list[JsonObject]
    daily_brief: JsonObject | None = None


class RecentData(ExactApiSchema):
    scope: str
    events: list[JsonObject]
    items: list[JsonObject]


class SearchPageData(ExactApiSchema):
    returned_count: int
    has_more: bool
    next_cursor: str | None


class SearchData(ExactApiSchema):
    query: JsonObject
    page: SearchPageData
    target_candidates: list[JsonObject]
    items: list[JsonObject]


class SearchInspectQueryData(ExactApiSchema):
    q: str
    normalized_q: str
    window: str
    scope: str
    result_kind: Literal["token_result", "topic_result", "ambiguous_result", "empty_result"]


class SearchInspectResolverData(ExactApiSchema):
    confidence: int | float
    target_candidates: list[JsonObject]
    selected_target: JsonObject | None
    reasons: list[str]


class SearchInspectData(ExactApiSchema):
    query: SearchInspectQueryData
    resolver: SearchInspectResolverData
    token_result: JsonObject | None
    topic_result: JsonObject | None
    ambiguous_result: JsonObject | None


class NarrativeCurrentnessData(ExactApiSchema):
    display_status: Literal["current", "not_ready", "out_of_frontier", "unsupported_window"]
    reason: str


class NarrativeCoverageData(ExactApiSchema):
    source_mentions: int
    independent_authors: int


class NarrativeAdmissionData(ExactApiSchema):
    status: Literal["admitted", "suppressed", "missing"]
    reason: str
    is_current: bool
    computed_at_ms: int | None
    currentness: NarrativeCurrentnessData
    data_gaps: list[JsonObject]
    coverage: NarrativeCoverageData


class TokenCaseData(ExactApiSchema):
    target: JsonObject
    profile: JsonObject | None
    timeline: JsonObject
    posts: JsonObject
    narrative_admission: NarrativeAdmissionData
    market_live: JsonObject


class TokenRadarIntentData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    event_id: str
    display_symbol: str | None = None
    display_name: str | None = None
    evidence: list[Any]


class TokenRadarMetaData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    lane: str | None = None
    rank: int | None = None
    listed_at_ms: int | None = None
    computed_at_ms: int | None = None
    source_max_received_at_ms: int | None = None


class TokenRadarResolutionData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    status: str
    target_type: str | None
    target_id: str | None
    pricefeed_id: str | None
    reason_codes: list[str]
    candidate_ids: list[str]
    lookup_keys: list[str]
    discovery: list[JsonObject]


class TokenRadarQualityData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    status: str
    degraded_reasons: list[str]


class TokenFactorSubjectData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    target_type: str | None
    target_id: str | None
    symbol: str | None
    target_market_type: str | None
    chain: str | None
    address: str | None
    pricefeed_id: str | None


class TokenFactorMarketReadinessData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    anchor_status: str
    latest_status: str
    dex_floor_status: str
    missing_fields: list[str]
    stale_fields: list[str]


class TokenFactorMarketData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    event_anchor: JsonObject | None
    decision_latest: JsonObject | None
    readiness: TokenFactorMarketReadinessData
    capture_method: str | None = None
    capture_reason: str | None = None
    tick_lag_ms: int | float | None = None


class TokenFactorFamilyData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    raw_score: int | float
    score: int | float
    weight: int | float
    data_health: str
    facts: JsonObject
    factors: JsonObject


class TokenFactorFamiliesData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    social_heat: TokenFactorFamilyData
    social_propagation: TokenFactorFamilyData
    semantic_catalyst: TokenFactorFamilyData
    timing_risk: TokenFactorFamilyData


class TokenFactorGatesData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    eligible_for_high_alert: bool
    max_decision: Literal["discard", "watch", "high_alert"]
    blocked_reasons: list[str]
    risk_reasons: list[str]


class TokenFactorFamilyValuesData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    social_heat: int | float
    social_propagation: int | float
    semantic_catalyst: int | float
    timing_risk: int | float


class TokenFactorRankValuesData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    social_heat: int | float | None
    social_propagation: int | float | None
    semantic_catalyst: int | float | None
    timing_risk: int | float | None


class TokenFactorNormalizationData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    status: str
    cohort_status: str
    cohort: JsonObject
    factor_ranks: TokenFactorRankValuesData
    alpha_rank: int | float | None


class TokenFactorCompositeData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    raw_alpha_score: int | float
    rank_score: int | float
    family_scores: TokenFactorFamilyValuesData
    recommended_decision: Literal["discard", "watch", "high_alert"]


class TokenFactorProvenanceData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    source_event_ids: list[str]
    computed_at_ms: int


class TokenFactorSnapshotData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["token_factor_snapshot_v3_social_attention"]
    subject: TokenFactorSubjectData
    market: TokenFactorMarketData
    gates: TokenFactorGatesData
    data_health: JsonObject
    families: TokenFactorFamiliesData
    normalization: TokenFactorNormalizationData
    composite: TokenFactorCompositeData
    provenance: TokenFactorProvenanceData


class TokenRadarRowData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    intent: TokenRadarIntentData
    radar: TokenRadarMetaData
    resolution: TokenRadarResolutionData
    quality: TokenRadarQualityData
    narrative_admission: NarrativeAdmissionData | None = None
    factor_snapshot: TokenFactorSnapshotData
    profile: JsonObject | None = None


class TokenRadarAnchorCoverageData(ExactApiSchema):
    status: str
    ready: int
    missing: int
    total: int


class TokenRadarUnresolvedData(ExactApiSchema):
    identity_missing_count: int
    nil_count: int
    ambiguous_count: int
    sample_symbols: list[str]


class TokenRadarProjectionData(ExactApiSchema):
    status: Literal["fresh", "stale", "pending", "failed"]
    version: str
    source: Literal["token_radar_current_rows"]
    venue: str
    reason: str | None
    latest_attempt_status: str
    row_count: int
    source_rows: int
    source_max_received_at_ms: int
    source_frontier_ms: int | None
    computed_at_ms: int | None
    error: str | None
    anchor_coverage: TokenRadarAnchorCoverageData
    quality_status: Literal["ready", "degraded", "insufficient", "failed"]
    degraded_reasons: list[str]
    unresolved: TokenRadarUnresolvedData


class TokenRadarData(ExactApiSchema):
    window: str
    scope: str
    venue: str
    targets: list[TokenRadarRowData]
    attention: list[TokenRadarRowData]
    projection: TokenRadarProjectionData


class StocksRadarQueryData(ExactApiSchema):
    window: str
    scope: str
    limit: int
    window_start_ms: int
    window_end_ms: int


class StocksRadarTargetData(ExactApiSchema):
    target_type: Literal["MarketInstrument"]
    target_id: str | None
    symbol: str | None
    market: Literal["us_equity"]
    exchange: str | None
    instrument_type: str | None
    name: str | None


class StocksRadarAttentionData(ExactApiSchema):
    mentions: int
    unique_authors: int
    watched_mentions: int
    latest_seen_ms: int | None


class StocksRadarLatestEventData(ExactApiSchema):
    event_id: str | None
    author_handle: str | None
    text: str | None
    received_at_ms: int | None


class StocksRadarQuoteData(ExactApiSchema):
    status: Literal["ready", "unavailable"]
    price: int | float | None
    reference_close_price: int | float | None
    change_pct: int | float | None
    asof: str | None
    provider: str | None
    provider_symbol: str | None
    latency_class: str | None
    freshness_class: str | None
    error: str | None


class StocksRadarRowData(ExactApiSchema):
    target: StocksRadarTargetData
    attention: StocksRadarAttentionData
    latest_event: StocksRadarLatestEventData
    quote: StocksRadarQuoteData
    source_event_ids: list[str]
    row_health: list[str]


class StocksRadarHealthData(ExactApiSchema):
    returned_count: int
    quote_ready_count: int
    quote_unavailable_count: int


class StocksRadarData(ExactApiSchema):
    window: str
    scope: str
    query: StocksRadarQueryData
    rows: list[StocksRadarRowData]
    health: StocksRadarHealthData


class NewsStory(ExactApiSchema):
    story_key: str
    representative_news_item_id: str
    member_news_item_ids: list[str]
    member_count: int
    source_domains: list[str]


class NewsMarketScope(ExactApiSchema):
    scope: list[str]
    primary: str
    status: str
    reason: str
    basis: JsonObject
    version: str


class NewsAgentAdmission(ExactApiSchema):
    eligible: bool
    status: str
    reason: str
    representative_news_item_id: str
    basis: JsonObject
    version: str


class NewsAlertEligibility(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    in_app_eligible: bool
    external_push_ready: bool
    external_push_block_reason: str | None = None
    external_push_basis: str | None = None
    agent_status: str
    decision_class: str | None = None
    market_scope: NewsMarketScope


class NewsSignalSummary(ExactApiSchema):
    source: str
    provider: str | None = None
    status: str
    direction: str
    label_zh: str | None = None
    signal: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    summary_en: str | None = None
    method: str | None = None


class NewsProviderRating(ExactApiSchema):
    provider: str | None = None
    status: str | None = None
    direction: str | None = None
    signal: str | None = None
    score: int | None = None
    grade: str | None = None
    method: str | None = None


class NewsAgentSignal(ExactApiSchema):
    status: str
    direction: str | None = None
    decision_class: str | None = None


class NewsSignalEnvelope(ExactApiSchema):
    display_signal: NewsSignalSummary
    agent_signal: NewsAgentSignal
    alert_eligibility: NewsAlertEligibility


class NewsSourceSummary(ExactApiSchema):
    source_id: str | None
    source_name: str | None
    source_domain: str
    provider_type: str
    source_role: str
    trust_tier: str
    coverage_tags: list[str]
    source_quality_status: str


class NewsTokenLane(ExactApiSchema):
    lane: str
    resolution_status: str | None = None
    symbol: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    display_name: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    candidate_targets: list[JsonObject] = Field(default_factory=list)


class NewsFactLane(ExactApiSchema):
    fact_candidate_id: str | None = None
    claim: str | None = None
    event_type: str | None = None
    realis: str | None = None
    status: str
    affected_targets: list[Any] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class NewsAgentBrief(ExactApiSchema):
    event_type: str | None = None
    market_domains: list[str] = Field(default_factory=list)
    status: str
    direction: str | None = None
    decision_class: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    market_read_zh: str | None = None
    market_impacts: list[Any] = Field(default_factory=list)
    transmission_paths: list[Any] = Field(default_factory=list)
    bull_strength: str | None = None
    bear_strength: str | None = None
    data_gap_count: int | None = None
    computed_at_ms: int | None = None
    bull_view: JsonObject | None = None
    bear_view: JsonObject | None = None
    affected_entities: list[Any] = Field(default_factory=list)
    data_gaps: list[Any] = Field(default_factory=list)
    watch_triggers: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    evidence_refs: list[Any] = Field(default_factory=list)


class NewsRow(ExactApiSchema):
    row_id: str
    news_item_id: str
    representative_news_item_id: str
    story_key: str
    story: NewsStory
    latest_at_ms: int
    lifecycle_status: str
    headline: str
    summary: str
    source_domain: str
    canonical_url: str
    duplicate_count: int
    source_ids: list[str]
    source_domains: list[str]
    token_lanes: list[NewsTokenLane]
    fact_lanes: list[NewsFactLane]
    signal: NewsSignalEnvelope
    provider_rating: NewsProviderRating
    token_impacts: list[NewsTokenLane]
    content_class: str
    content_tags: list[str]
    content_classification: JsonObject
    source: NewsSourceSummary
    agent_brief: NewsAgentBrief
    agent_status: str
    agent_brief_computed_at_ms: int | None
    macro_event_flow: JsonObject | None = None
    agent_admission_status: str
    agent_admission_reason: str
    agent_admission: NewsAgentAdmission
    agent_representative_news_item_id: str
    computed_at_ms: int
    projection_version: str


class NewsData(ExactApiSchema):
    items: list[NewsRow]
    next_cursor: str | None


class NewsSourceDetailData(ExactApiSchema):
    source_id: str | None
    provider_type: str
    source_domain: str
    source_name: str | None
    source_role: str
    trust_tier: str
    coverage_tags: list[str]
    asset_universe: list[str]
    authority_scope: JsonObject
    source_quality_status: str
    enabled: bool
    managed_by_config: bool
    refresh_interval_seconds: int
    created_at_ms: int
    updated_at_ms: int


class NewsObjectData(ExactApiSchema):
    news_item_id: str
    source_id: str
    source_domain: str
    canonical_url: str
    title: str
    summary: str
    body_text: str
    language: str
    published_at_ms: int
    fetched_at_ms: int
    lifecycle_status: str
    content_class: str
    processed_at_ms: int | None
    processing_error: str | None
    created_at_ms: int
    updated_at_ms: int
    duplicate_observation_count: int
    representative_news_item_id: str
    story_key: str
    story: NewsStory
    agent_admission_status: str
    agent_admission_reason: str
    agent_admission: NewsAgentAdmission
    agent_representative_news_item_id: str
    agent_admission_computed_at_ms: int | None
    content_tags: list[str]
    content_classification: JsonObject
    signal: NewsSignalEnvelope
    provider_rating: NewsProviderRating
    token_impacts: list[NewsTokenLane]
    token_lanes: list[NewsTokenLane]
    fact_lanes: list[NewsFactLane]
    source: NewsSourceDetailData
    provider_item: JsonObject
    fetch_run: JsonObject | None
    agent_brief: NewsAgentBrief
    observation_edges: list[JsonObject]
    provider_observations: list[JsonObject]
    entities: list[Any]
    token_mentions: list[Any]
    fact_candidates: list[JsonObject]


class NewsFactDetailData(ExactApiSchema):
    fact_candidate_id: str
    news_item_id: str
    event_type: str
    claim: str
    realis: str
    evidence_quote: str
    evidence_span_start: int
    evidence_span_end: int
    source_role: str
    required_slots_json: JsonObject
    affected_targets_json: list[Any]
    validation_status: str
    rejection_reasons_json: list[str]
    extraction_method: str
    policy_version: str
    created_at_ms: int
    updated_at_ms: int
    headline: str
    canonical_url: str
    source_domain: str


class NewsProviderCapabilitiesData(ExactApiSchema):
    supported_provider_types: list[str]
    configured_provider_types: list[str]
    unsupported_configured_provider_types: list[str]


class NewsSourceProviderData(ExactApiSchema):
    source_id: str
    provider_type: str


class NewsSourceHealthData(ExactApiSchema):
    source_id: str
    status: str


class NewsSourceWarningData(ExactApiSchema):
    source_id: str
    reason: str


class NewsSourceHygieneData(ExactApiSchema):
    sources_missing_coverage_tags: list[str]
    unsupported_sources: list[NewsSourceProviderData]
    degraded_sources: list[NewsSourceHealthData]
    warnings: list[NewsSourceWarningData]


class NewsSourceStatusData(ExactApiSchema):
    provider_capabilities: NewsProviderCapabilitiesData
    source_hygiene: NewsSourceHygieneData
    sources: list[JsonObject]


class LiveMarketData(ExactApiSchema):
    target_type: str
    target_id: str
    status: Literal["live", "stale", "missing"]
    price_usd: float | None
    price_quote: float | None
    quote_symbol: str | None
    price_basis: Literal["usd", "quote_as_usd", "unavailable"]
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    volume_24h_usd: float | None
    open_interest_usd: float | None
    observed_at_ms: int | None
    received_at_ms: int | None
    age_ms: int | None
    provider: str | None


class TargetPostsQueryData(ExactApiSchema):
    target_type: str
    target_id: str
    window: str
    scope: str
    post_range: str = Field(alias="range")
    sort: str


class TargetPostsScoreWindowData(ExactApiSchema):
    window: str


class TargetPostsData(ExactApiSchema):
    query: TargetPostsQueryData
    score_window: TargetPostsScoreWindowData
    total_count: int
    returned_count: int
    has_more: bool
    next_cursor: str | None
    items: list[JsonObject]


class TargetSocialTimelineQueryData(ExactApiSchema):
    target_type: str
    target_id: str
    window: str
    scope: str
    bucket: str


class TargetSocialTimelineData(ExactApiSchema):
    query: TargetSocialTimelineQueryData
    summary: JsonObject
    market_candles: JsonObject | None
    stages: list[JsonObject]
    buckets: list[JsonObject]
    authors: list[JsonObject]
    posts: list[JsonObject]
    cascade: JsonObject
    returned_count: int
    has_more: bool
    next_cursor: str | None


class AccountAlertsData(ExactApiSchema):
    window: str
    alert_type: str | None
    items: list[JsonObject]


class NotificationSummary(ExactApiSchema):
    subscriber_key: str
    unread_count: int
    high_unread_count: int
    critical_unread_count: int
    highest_unread_severity: str | None
    account_unread_counts: dict[str, int]


class NotificationItemData(ExactApiSchema):
    notification_id: str
    dedup_key: str
    rule_id: str
    severity: str
    title: str
    body: str
    entity_type: str | None
    entity_key: str | None
    author_handle: str | None
    symbol: str | None
    chain: str | None
    address: str | None
    event_id: str | None
    source_table: str
    source_id: str
    occurrence_count: int
    first_seen_at_ms: int
    last_seen_at_ms: int
    created_at_ms: int
    updated_at_ms: int
    read_at_ms: int | None
    payload: JsonObject
    channels: list[str]


class NotificationsData(ExactApiSchema):
    items: list[NotificationItemData]
    summary: NotificationSummary


class NotificationDeliveriesData(ExactApiSchema):
    items: list[JsonObject]


class NotificationReadData(ExactApiSchema):
    notification_id: str
    updated: bool


class NotificationReadAllData(ExactApiSchema):
    updated_count: int


class SourceEventDetail(ExactApiSchema):
    event_id: str
    timestamp_ms: int
    source_provider: str
    channel: str
    action: str
    author_handle: str | None
    author_name: str | None
    author_followers: int | None
    author_watched: bool
    text_clean: str | None
    canonical_url: str | None


class SourceEventsByIdsData(ExactApiSchema):
    events: list[SourceEventDetail]
    not_found: list[str]


class WatchlistHandleRowOverview(ExactApiSchema):
    handle: str
    last_source_event_at_ms: int | None
    recent_source_event_count: int


class WatchlistHandlesOverviewData(ExactApiSchema):
    window: str
    items: list[WatchlistHandleRowOverview]


class WatchlistOverviewQuery(ExactApiSchema):
    handle: str
    window: str


class WatchlistOverviewMetrics(ExactApiSchema):
    source_event_count: int
    resolved_token_count: int
    candidate_mention_count: int
    narrative_count: int
    last_source_event_at_ms: int | None


class WatchlistOverviewCluster(ExactApiSchema):
    label: str
    count: int
    query: str
    kind: Literal["resolved_token", "candidate_mention", "narrative"]
    target_type: str | None
    target_id: str | None
    symbol: str | None
    source: str


class WatchlistHandleOverviewData(ExactApiSchema):
    query: WatchlistOverviewQuery
    metrics: WatchlistOverviewMetrics
    resolved_token_clusters: list[WatchlistOverviewCluster]
    candidate_mention_clusters: list[WatchlistOverviewCluster]
    narrative_clusters: list[WatchlistOverviewCluster]
    clusters_truncated: bool
    risk_notes: list[str]


class WatchlistTimelineQuery(ExactApiSchema):
    handle: str
    limit: int


class WatchlistTimelineItem(ExactApiSchema):
    event_id: str
    received_at_ms: int
    author_handle: str | None
    action: str
    text_clean: str | None
    canonical_url: str | None
    cashtags: list[str]
    hashtags: list[str]
    mentions: list[str]
    event: JsonObject
    token_resolutions: list[JsonObject]


class WatchlistHandleTimelineData(ExactApiSchema):
    query: WatchlistTimelineQuery
    items: list[WatchlistTimelineItem]
    has_more: bool
    next_cursor: str | None


class OpsOverallData(ExactApiSchema):
    status: str
    severity: str
    reasons: list[str]
    section_status_counts: dict[str, int]


class OpsConfigData(ExactApiSchema):
    app_home: str | None
    config_path: str | None
    workers_config_path: str | None
    handles_count: int
    upstream_channels: list[str]
    gmgn_configured: bool
    okx_dex_configured: bool
    llm_configured: bool
    news_enabled: bool
    notifications_enabled: bool


class OpsSectionFailureData(ExactApiSchema):
    status: Literal["unknown"]
    section: str
    error_type: str
    reason: str


class OpsDatabaseData(ExactApiSchema):
    ok: bool
    probe: Literal["postgres_liveness"]
    status: str
    schema_payload: JsonObject = Field(alias="schema")
    detail: str | None = None
    error: str | None = None
    original_error: str | None = None
    original_detail: str | None = None


class OpsCollectorData(ExactApiSchema):
    status: str
    connection: JsonObject
    details: JsonObject


class OpsProviderData(ExactApiSchema):
    provider: str
    domain: str
    configured: bool
    capabilities: list[str]
    state: str
    last_state_change_at_ms: int | None
    last_error_type: str | None
    status: str
    reason: str


class OpsWorkerData(ExactApiSchema):
    name: str
    group: str
    enabled: bool
    running: bool
    effective_status: str
    unavailable_reason: str | None
    last_started_at_ms: int | None
    last_finished_at_ms: int | None
    last_result: JsonObject | None
    last_error_type: str | None
    iteration_duration_p99_ms: float | None
    status: str
    reason: str


class OpsQueueSummaryData(ExactApiSchema):
    queue_name: str
    table: str
    worker_name: str
    counts_by_status: dict[str, int]
    due_count: int
    running_count: int
    dead_count: int
    failed_count: int
    oldest_due_age_ms: int | None
    oldest_running_age_ms: int | None
    status: str
    reason: str


class OpsAgentExecutionPolicyData(ExactApiSchema):
    lane: Literal["news.story_brief"]
    model: str
    provider_family: str
    output_strategy: Literal["json_object"]
    schema_enforcement: Literal["client_validate"]
    max_concurrency: int
    rpm_limit: int
    timeout_seconds: float


class OpsAgentExecutionCountersData(ExactApiSchema):
    in_flight: int
    provider_running: int
    circuit_state: Literal["open", "closed"]
    circuit_open_until_ms: int | None
    capacity_denied_total: int
    circuit_open_total: int
    timeout_total: int
    last_denied_at_ms: int | None
    last_timeout_at_ms: int | None
    oldest_in_flight_age_ms: float | None


class OpsAgentExecutionData(ExactApiSchema):
    status: Literal["ok", "degraded", "disabled", "unavailable", "unknown"]
    policy: OpsAgentExecutionPolicyData | None
    counters: OpsAgentExecutionCountersData | None
    status_reason: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_policy_state(self) -> OpsAgentExecutionData:
        inactive = self.status in {"disabled", "unavailable", "unknown"}
        if inactive and (self.policy is not None or self.counters is not None):
            raise ValueError("inactive agent execution must not expose policy or counters")
        if not inactive and (self.policy is None or self.counters is None):
            raise ValueError("active agent execution requires policy and counters")
        return self


class OpsTokenRadarDomainData(ExactApiSchema):
    status: str
    publication: JsonObject


class OpsAssetMarketDomainData(ExactApiSchema):
    status: str
    configured_provider_count: int
    provider_count: int


class OpsNewsDomainData(ExactApiSchema):
    status: str
    sources: list[JsonObject]
    source_count: int


class OpsWatchlistDomainData(ExactApiSchema):
    status: str
    configured_handle_count: int


class OpsNotificationsDomainData(ExactApiSchema):
    status: str
    summary: NotificationSummary


class OpsDomainsData(ExactApiSchema):
    token_radar: OpsTokenRadarDomainData | OpsSectionFailureData
    asset_market: OpsAssetMarketDomainData | OpsSectionFailureData
    news: OpsNewsDomainData | OpsSectionFailureData
    watchlist: OpsWatchlistDomainData | OpsSectionFailureData
    notifications: OpsNotificationsDomainData | OpsSectionFailureData


class OpsSuggestedCheckData(ExactApiSchema):
    id: str
    label: str
    reason: str
    cli_equivalent: str
    safe_to_run: bool
    requires_confirmation: bool


class OpsDiagnosticsData(ExactApiSchema):
    schema_version: Literal["ops.diagnostics.v1"]
    generated_at_ms: int
    overall: OpsOverallData
    config: OpsConfigData
    database: OpsDatabaseData | OpsSectionFailureData
    collector: OpsCollectorData | OpsSectionFailureData
    providers: list[OpsProviderData]
    workers: list[OpsWorkerData]
    queues: list[OpsQueueSummaryData]
    agent_execution: OpsAgentExecutionData
    domains: OpsDomainsData
    suggested_checks: list[OpsSuggestedCheckData]


class OpsQueueItemData(ExactApiSchema):
    id: Any
    status: str | None
    attempt_count: int | None
    max_attempts: int | None
    created_at_ms: int | None
    updated_at_ms: int | None
    next_run_at_ms: int | None
    last_attempt_at_ms: int | None
    delivered_at_ms: int | None
    last_error_type: str | None
    last_error_preview: str | None
    source: JsonObject


class OpsQueueData(ExactApiSchema):
    schema_version: Literal["ops.queue.v1"]
    queue_name: str
    status_filter: str | None
    counts_by_status: dict[str, int]
    summary: OpsQueueSummaryData
    items: list[OpsQueueItemData]
