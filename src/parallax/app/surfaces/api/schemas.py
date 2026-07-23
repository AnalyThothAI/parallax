from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    projection_version: Literal["macro_evidence_v1"]
    fact_watermark: date | None
    market_cutoff: date | None
    computed_at_ms: int


class MacroSampleData(ExactApiSchema):
    start: date | None
    end: date | None
    count: int


class MacroObservedInputData(ExactApiSchema):
    observed_at: date
    value: int | float


class MacroConceptInputData(ExactApiSchema):
    concept_key: str
    observed_at: date | None = None
    value: int | float | None


class MacroLiquidityInputData(ExactApiSchema):
    concept_key: str
    source_unit: str
    value_millions_usd: int | float | None


class MacroDerivationData(ExactApiSchema):
    formula: str
    inputs: list[MacroObservedInputData | MacroConceptInputData | MacroLiquidityInputData]
    references: list[str]


class MacroEvidenceFreshnessData(ExactApiSchema):
    status: Literal["fresh", "stale", "missing", "derived"]
    age_days: int | None
    stale_after_days: int | None


class MacroEvidenceData(ExactApiSchema):
    concept_key: str
    role: Literal["primary", "confirmation", "context", "catalyst"]
    status: Literal["available", "stale", "unavailable", "invalid"]
    reason: str | None
    value: int | float | None
    unit: str
    change: int | float | None
    change_window: str | None
    observed_at: date | None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "irregular", "event"]
    source_name: str | None
    series_key: str | None
    data_quality: str
    freshness: MacroEvidenceFreshnessData
    sample: MacroSampleData
    criticality: Literal["critical", "optional"]
    claim_effect: str
    derivation: MacroDerivationData | None


class MacroRuleHitData(ExactApiSchema):
    rule_id: str
    outcome: Literal["trigger", "confirmation", "contradiction", "invalidation"]
    evidence_refs: list[str]


class MacroDecisionItemData(ExactApiSchema):
    code: str
    evidence_refs: list[str]


class MacroUpgradeInvalidationData(ExactApiSchema):
    upgrade: list[MacroDecisionItemData]
    invalidation: list[MacroDecisionItemData]


class MacroPageFreshnessData(ExactApiSchema):
    status: Literal["fresh", "degraded", "insufficient_evidence"]
    critical_missing: list[str]
    critical_stale: list[str]
    optional_unavailable: list[str]


class MacroUnavailableEvidenceData(ExactApiSchema):
    capability: str
    status: Literal["not_assessed"]
    reason: str


class MacroConclusionData(ExactApiSchema):
    status: Literal["supported", "degraded", "insufficient_evidence"]
    judgment: str
    rule_version: str
    rule_hits: list[MacroRuleHitData]


class MacroPageBaseData(ExactApiSchema):
    snapshot: MacroSnapshotData
    conclusion: MacroConclusionData
    horizon: Literal["1_4_weeks"]
    drivers: list[MacroDecisionItemData]
    confirmations: list[MacroDecisionItemData]
    contradictions: list[MacroDecisionItemData]
    upgrade_invalidation: MacroUpgradeInvalidationData
    evidence_refs: list[str]
    freshness: MacroPageFreshnessData
    evidence: list[MacroEvidenceData]
    unavailable_evidence: list[MacroUnavailableEvidenceData]


class MacroDominantShockData(ExactApiSchema):
    candidate: (
        Literal[
            "growth",
            "inflation",
            "policy_real_rates",
            "term_premium_supply",
            "liquidity_funding",
            "credit",
        ]
        | None
    )
    status: Literal["confirmed", "provisional", "divergent", "insufficient_evidence"]
    primary_trigger: MacroDecisionItemData | None
    cross_domain_confirmations: list[MacroDecisionItemData]
    critical_contradictions: list[MacroDecisionItemData]
    affected_exposures: list[str]
    rule_version: str
    hit_evidence: list[str]


class MacroOfficialCatalystData(ExactApiSchema):
    concept_key: str
    event_date: date
    event_time: str
    timezone: str
    source_name: str
    series_key: str
    source_url: str
    release_status: Literal["today", "upcoming"]
    evidence_ref: str


class MacroOverviewData(MacroPageBaseData):
    page_id: Literal["overview"]
    dominant_shock: MacroDominantShockData
    official_catalysts: list[MacroOfficialCatalystData]


class MacroReturnWindowData(ExactApiSchema):
    status: Literal["available", "unavailable"]
    reason: str | None
    window: Literal["20_sessions", "60_sessions"]
    value: int | float | None
    unit: Literal["percent"]
    sample: MacroSampleData
    derivation: MacroDerivationData | None


class MacroAssetReturnData(ExactApiSchema):
    concept_key: str
    status: Literal["available", "unavailable"]
    reason: str | None
    observed_at: date | None
    source_name: str | None
    series_key: str | None
    return_20: MacroReturnWindowData
    return_60: MacroReturnWindowData
    evidence: MacroEvidenceData


class MacroCorrelationData(ExactApiSchema):
    left: str
    right: str
    window: Literal["20_sessions", "60_sessions"]
    sample: MacroSampleData
    status: Literal["available", "unavailable"]
    reason: str | None
    correlation: float | None


class MacroCrossAssetData(MacroPageBaseData):
    page_id: Literal["cross_asset"]
    asset_returns: list[MacroAssetReturnData]
    volatility: list[MacroEvidenceData]
    correlations_20: list[MacroCorrelationData]
    correlations_60: list[MacroCorrelationData]
    divergences: list[MacroDecisionItemData]


class MacroMetricData(ExactApiSchema):
    concept_key: str | None = None
    status: Literal["available", "unavailable"]
    reason: str | None
    value: int | float | None
    unit: str | None
    window: str | None
    sample: MacroSampleData
    derivation: MacroDerivationData | None


class MacroInflationReleaseData(ExactApiSchema):
    evidence: MacroEvidenceData
    release_change: MacroMetricData
    year_over_year: MacroMetricData


class MacroFundingCorridorData(ExactApiSchema):
    status: Literal["supported", "insufficient_evidence"]
    state: str
    evidence_refs: list[str]
    spreads: list[MacroEvidenceData]
    evidence: list[MacroEvidenceData]


class MacroCurveShapeData(ExactApiSchema):
    status: Literal["supported", "insufficient_evidence"]
    level_classification: str
    move_classification: str
    two_year_change: int | float | None
    ten_year_change: int | float | None
    change_window: Literal["20_sessions"]
    evidence_refs: list[str]
    rule_version: str


class MacroRatesInflationData(MacroPageBaseData):
    page_id: Literal["rates_inflation"]
    nominal_curve: list[MacroEvidenceData]
    curve_slopes: list[MacroEvidenceData]
    real_yields: list[MacroEvidenceData]
    breakevens: list[MacroEvidenceData]
    term_premium: MacroUnavailableEvidenceData
    policy_funding_corridor: MacroFundingCorridorData
    inflation_releases: list[MacroInflationReleaseData]
    curve_shape: MacroCurveShapeData


class MacroGrowthLaborData(MacroPageBaseData):
    page_id: Literal["growth_labor"]
    growth_leading: list[MacroEvidenceData]
    growth_lagging: list[MacroEvidenceData]
    labor_leading: list[MacroEvidenceData]
    labor_lagging: list[MacroEvidenceData]
    growth_metrics: list[MacroMetricData]


class MacroFundingLayerData(ExactApiSchema):
    evidence: list[MacroEvidenceData]
    spreads: list[MacroEvidenceData]


class MacroLiquidityFundingData(MacroPageBaseData):
    page_id: Literal["liquidity_funding"]
    central_bank_balance_sheet: list[MacroEvidenceData]
    treasury_cash: list[MacroEvidenceData]
    reverse_repo: list[MacroEvidenceData]
    reserves: list[MacroEvidenceData]
    net_liquidity: MacroEvidenceData
    secured_funding: MacroFundingLayerData
    unsecured_funding: MacroFundingLayerData


class MacroTreasurySpreadQuadrantData(ExactApiSchema):
    status: Literal["supported", "insufficient_evidence"]
    quadrant: str
    yield_change: int | float | None
    spread_change: int | float | None
    change_window: Literal["20_sessions"]
    evidence_refs: list[str]
    rule_version: str


class MacroCreditStateData(ExactApiSchema):
    status: Literal["supported", "insufficient_evidence"]
    stage: Literal[
        "contained",
        "tail_stress",
        "broadening",
        "systemic_tightening",
        "repairing",
        "insufficient_evidence",
    ]
    direction: Literal["widening", "narrowing", "stable", "insufficient_evidence"]
    evidence_refs: list[str]
    rule_version: str


class MacroCreditData(MacroPageBaseData):
    page_id: Literal["credit"]
    aggregate_spreads: list[MacroEvidenceData]
    rating_tail: list[MacroEvidenceData]
    effective_yields: list[MacroEvidenceData]
    credit_supply: list[MacroEvidenceData]
    realized_damage: list[MacroEvidenceData]
    financial_conditions_liquidity: list[MacroEvidenceData]
    treasury_spread_quadrant: MacroTreasurySpreadQuadrantData
    credit_state: MacroCreditStateData


class MacroSeriesPointData(ExactApiSchema):
    observed_at: date
    value: int | float | None
    source_name: str | None
    series_key: str | None
    unit: str | None
    frequency: str | None
    data_quality: str
    event_metadata: MacroSeriesEventMetadataData


class MacroSeriesEventMetadataData(ExactApiSchema):
    text_value: str | None = None
    source_url: str | None = None
    event_code: str | None = None
    document_type: str | None = None
    speaker: str | None = None
    event_time: str | None = None
    event_time_et: str | None = None
    reference_period: str | None = None
    cusip: str | None = None
    announcement_date: date | None = None
    settlement_date: date | None = None
    reopening: bool | None = None


class MacroSeriesGapData(ExactApiSchema):
    code: str
    label: str
    severity: Literal["warning", "error"]
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
    target_candidates: list[JsonObject]
    selected_target: JsonObject | None
    reasons: list[str]


class SearchInspectTopicSummaryData(ExactApiSchema):
    posts: int
    authors: int


class SearchInspectTopicData(ExactApiSchema):
    summary: SearchInspectTopicSummaryData
    items: list[JsonObject]


class SearchInspectAmbiguousData(ExactApiSchema):
    candidates: list[JsonObject]
    summary: SearchInspectTopicSummaryData
    items: list[JsonObject]


class SearchInspectData(ExactApiSchema):
    query: SearchInspectQueryData
    resolver: SearchInspectResolverData
    token_result: TokenCaseData | None
    topic_result: SearchInspectTopicData | None
    ambiguous_result: SearchInspectAmbiguousData | None


class TokenCaseData(ExactApiSchema):
    target: JsonObject
    profile: JsonObject | None
    timeline: JsonObject
    posts: JsonObject
    market_live: JsonObject
    current_radar: TokenRadarFactRowData | None


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
    timing_risk: int | float


class TokenFactorRankValuesData(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    social_heat: int | float | None
    social_propagation: int | float | None
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

    schema_version: Literal["token_factor_snapshot_v4_transparent_factors"]
    subject: TokenFactorSubjectData
    market: TokenFactorMarketData
    gates: TokenFactorGatesData
    data_health: JsonObject
    families: TokenFactorFamiliesData
    normalization: TokenFactorNormalizationData
    composite: TokenFactorCompositeData
    provenance: TokenFactorProvenanceData


class TokenRadarFactRowData(ExactApiSchema):
    model_config = ConfigDict(extra="forbid")

    intent: TokenRadarIntentData
    radar: TokenRadarMetaData
    resolution: TokenRadarResolutionData
    quality: TokenRadarQualityData
    factor_snapshot: TokenFactorSnapshotData


class TokenRadarRowData(TokenRadarFactRowData):
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
    source_ids: list[str] = Field(default_factory=list)
    provider_article_keys: list[str] = Field(default_factory=list)


class NewsMarketScope(ExactApiSchema):
    scope: list[str]
    primary: str
    status: str
    reason: str
    basis: JsonObject
    version: str


class NewsProviderRating(ExactApiSchema):
    provider: str | None = None
    status: str | None = None
    direction: str | None = None
    signal: str | None = None
    score: int | None = None
    grade: str | None = None
    method: str | None = None


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
    canonical_item_key: str
    duplicate_count: int
    source_ids: list[str]
    source_domains: list[str]
    provider_article_keys: list[str]
    token_lanes: list[NewsTokenLane]
    fact_lanes: list[NewsFactLane]
    provider_rating: NewsProviderRating
    content_class: str
    content_tags: list[str]
    content_classification: JsonObject
    source: NewsSourceSummary
    market_scope: NewsMarketScope
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
    content_tags: list[str]
    content_classification: JsonObject
    provider_rating: NewsProviderRating
    market_scope: NewsMarketScope
    token_lanes: list[NewsTokenLane]
    fact_lanes: list[NewsFactLane]
    source: NewsSourceDetailData
    provider_item: JsonObject
    fetch_run: JsonObject | None
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
    hashtag_count: int
    last_source_event_at_ms: int | None


class WatchlistOverviewCluster(ExactApiSchema):
    label: str
    count: int
    query: str
    kind: Literal["resolved_token", "candidate_mention", "hashtag"]
    target_type: str | None
    target_id: str | None
    symbol: str | None
    source: str


class WatchlistHandleOverviewData(ExactApiSchema):
    query: WatchlistOverviewQuery
    metrics: WatchlistOverviewMetrics
    resolved_token_clusters: list[WatchlistOverviewCluster]
    candidate_mention_clusters: list[WatchlistOverviewCluster]
    hashtag_clusters: list[WatchlistOverviewCluster]
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
