from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JsonObject = dict[str, Any]


class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ApiEnvelope[T](ApiSchema):
    ok: bool
    data: T | None = None
    error: str | None = None
    field: str | None = None


class BootstrapData(ApiSchema):
    ws_token: str
    handles: list[str] = Field(default_factory=list)
    replay_limit: int


class WorkerLaneStatusData(ApiSchema):
    lane: str
    enabled_workers: int = 0
    running_workers: int = 0
    stopped_workers: int = 0
    disabled_workers: int = 0
    intentionally_not_started_workers: int = 0
    unavailable_workers: int = 0
    degraded_workers: int = 0
    failed_workers: int = 0
    hard_timed_out_workers: int = 0
    oldest_active_run_once_age_ms: int | None = None
    iteration_duration_p99_ms: float | None = None


class StatusData(ApiSchema):
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    store: str | None = None
    snapshot_gate: JsonObject = Field(default_factory=dict)
    db: JsonObject | None = None
    provider_states: JsonObject = Field(default_factory=dict)
    agent_execution: JsonObject | None = None
    workers: dict[str, WorkerStatusData] = Field(default_factory=dict)
    worker_lanes: dict[str, WorkerLaneStatusData] = Field(default_factory=dict)


class ReadinessData(ApiSchema):
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    store: str
    db: JsonObject
    composition: JsonObject


class WorkerStatusData(ApiSchema):
    enabled: bool
    running: bool
    effective_status: str = "disabled"
    unavailable_reason: str | None = None
    last_started_at_ms: int | None = None
    last_finished_at_ms: int | None = None
    last_result: JsonObject | None = None
    last_error: str | None = None
    iteration_duration_p99_ms: float | None = None
    pool_wait_ms_p99: float | None = None
    active_run_once_started_at_ms: int | None = None
    active_run_once_age_ms: int | None = None
    active_run_once_hard_timed_out_at_ms: int | None = None
    active_run_once_count: int = 0
    details: JsonObject = Field(default_factory=dict)


class RecentData(ApiSchema):
    scope: str
    events: list[JsonObject] = Field(default_factory=list)
    items: list[JsonObject] = Field(default_factory=list)


class SearchData(ApiSchema):
    query: JsonObject
    page: JsonObject
    target_candidates: list[JsonObject] = Field(default_factory=list)
    items: list[JsonObject] = Field(default_factory=list)


class SearchInspectData(ApiSchema):
    query: JsonObject
    resolver: JsonObject | None = None
    token_result: JsonObject | None = None
    topic_result: JsonObject | None = None
    ambiguous_result: JsonObject | None = None
    error: str | None = None


class NarrativeCurrentnessData(ApiSchema):
    display_status: Literal["current", "not_ready", "out_of_frontier", "unsupported_window"]
    reason: str


class NarrativeCoverageData(ApiSchema):
    source_mentions: int = 0
    independent_authors: int = 0


class NarrativeAdmissionData(ApiSchema):
    status: Literal["admitted", "suppressed", "missing"]
    reason: str
    is_current: bool = False
    computed_at_ms: int | None = None
    currentness: NarrativeCurrentnessData
    data_gaps: list[Any] = Field(default_factory=list)
    coverage: NarrativeCoverageData = Field(default_factory=NarrativeCoverageData)


class TokenCaseData(ApiSchema):
    target: JsonObject
    profile: JsonObject | None = None
    timeline: JsonObject
    posts: JsonObject
    narrative_admission: NarrativeAdmissionData
    market_live: JsonObject


class TokenRadarRowData(ApiSchema):
    narrative_admission: NarrativeAdmissionData | None = None


class TokenRadarData(ApiSchema):
    window: str
    scope: str
    venue: str
    targets: list[TokenRadarRowData] = Field(default_factory=list)
    attention: list[TokenRadarRowData] = Field(default_factory=list)
    projection: JsonObject = Field(default_factory=dict)


class StocksRadarData(ApiSchema):
    window: str | None = None
    scope: str | None = None
    rows: list[JsonObject] = Field(default_factory=list)
    items: list[JsonObject] = Field(default_factory=list)
    projection: JsonObject | None = None


class NewsStory(ApiSchema):
    story_key: str | None = None
    representative_news_item_id: str | None = None
    member_news_item_ids: list[str] = Field(default_factory=list)
    member_count: int | None = None
    source_domains: list[str] = Field(default_factory=list)


class NewsMarketScope(ApiSchema):
    scope: list[str] = Field(default_factory=list)
    primary: str | None = None
    status: str | None = None
    reason: str | None = None
    basis: JsonObject = Field(default_factory=dict)
    version: str | None = None


class NewsAgentAdmission(ApiSchema):
    eligible: bool | None = None
    status: str | None = None
    reason: str | None = None
    representative_news_item_id: str | None = None
    basis: JsonObject = Field(default_factory=dict)
    version: str | None = None


class NewsAlertEligibility(ApiSchema):
    in_app_eligible: bool | None = None
    external_push_ready: bool | None = None
    external_push_block_reason: str | None = None
    external_push_basis: str | None = None
    agent_status: str | None = None
    decision_class: str | None = None
    market_scope: NewsMarketScope | None = None
    agent_admission_status: str | None = None
    agent_admission_reason: str | None = None


class NewsSignalSummary(ApiSchema):
    source: str | None = None
    provider: str | None = None
    status: str | None = None
    direction: str | None = None
    label_zh: str | None = None
    signal: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    summary_en: str | None = None
    method: str | None = None


class NewsProviderRating(ApiSchema):
    provider: str | None = None
    status: str | None = None
    direction: str | None = None
    signal: str | None = None
    score: int | None = None
    grade: str | None = None
    method: str | None = None


class NewsSignalEnvelope(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    display_signal: NewsSignalSummary = Field(default_factory=NewsSignalSummary)
    agent_signal: JsonObject = Field(default_factory=dict)
    alert_eligibility: NewsAlertEligibility = Field(default_factory=NewsAlertEligibility)


class NewsSourceSummary(ApiSchema):
    source_id: str | None = None
    source_name: str | None = None
    source_domain: str | None = None
    provider_type: str | None = None
    source_role: str | None = None
    trust_tier: str | None = None
    coverage_tags: list[str] = Field(default_factory=list)
    source_quality_status: str | None = None


class NewsTokenLane(ApiSchema):
    lane: str | None = None
    resolution_status: str | None = None
    symbol: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    market_type: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    score: int | None = None
    signal: str | None = None


class NewsFactLane(ApiSchema):
    claim: str | None = None
    event_type: str | None = None
    realis: str | None = None
    status: str | None = None
    affected_targets: list[Any] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class NewsAgentBrief(ApiSchema):
    status: str | None = None
    direction: str | None = None
    decision_class: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    market_read_zh: str | None = None
    market_impacts: list[Any] = Field(default_factory=list)
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


class NewsRow(ApiSchema):
    row_id: str | None = None
    news_item_id: str | None = None
    representative_news_item_id: str | None = None
    story_key: str | None = None
    story: NewsStory | None = None
    latest_at_ms: int | None = None
    lifecycle_status: str | None = None
    headline: str | None = None
    title: str | None = None
    summary: str | None = None
    body_text: str | None = None
    language: str | None = None
    published_at_ms: int | None = None
    fetched_at_ms: int | None = None
    duplicate_count: int | None = None
    duplicate_observation_count: int | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_domains: list[str] = Field(default_factory=list)
    source_domain: str | None = None
    provider_type: str | None = None
    source_role: str | None = None
    trust_tier: str | None = None
    coverage_tags: list[str] = Field(default_factory=list)
    source_quality_status: str | None = None
    source: NewsSourceSummary | None = None
    canonical_url: str | None = None
    content_class: str | None = None
    content_tags: list[str] = Field(default_factory=list)
    content_classification: JsonObject = Field(default_factory=dict)
    signal: NewsSignalEnvelope = Field(default_factory=NewsSignalEnvelope)
    provider_rating: NewsProviderRating | None = None
    token_impacts: list[NewsTokenLane] = Field(default_factory=list)
    token_lanes: list[NewsTokenLane] = Field(default_factory=list)
    fact_lanes: list[NewsFactLane] = Field(default_factory=list)
    agent_brief: NewsAgentBrief | None = None
    agent_brief_status: str | None = None
    agent_status: str | None = None
    agent_brief_computed_at_ms: int | None = None
    market_scope: NewsMarketScope | None = None
    agent_admission_status: str | None = None
    agent_admission_reason: str | None = None
    agent_admission: NewsAgentAdmission | None = None
    agent_representative_news_item_id: str | None = None
    computed_at_ms: int | None = None
    projection_version: str | None = None


class NewsData(ApiSchema):
    items: list[NewsRow] = Field(default_factory=list)
    next_cursor: str | None = None


class NewsObjectData(NewsRow):
    content: str | None = None
    entities: list[Any] = Field(default_factory=list)
    token_mentions: list[Any] = Field(default_factory=list)
    fact_candidates: list[NewsFactLane] = Field(default_factory=list)
    provider_item: JsonObject | None = None
    fetch_run: JsonObject | None = None
    observation_edges: list[JsonObject] = Field(default_factory=list)
    provider_observations: list[JsonObject] = Field(default_factory=list)
    fact_candidate_id: str | None = None


class NewsFactDetailData(ApiSchema):
    fact_candidate_id: str | None = None
    news_item_id: str | None = None
    event_type: str | None = None
    claim: str | None = None
    realis: str | None = None
    evidence_quote: str | None = None
    validation_status: str | None = None
    confidence: float | None = None
    affected_targets_json: list[Any] = Field(default_factory=list)
    rejection_reasons_json: list[str] = Field(default_factory=list)
    headline: str | None = None
    canonical_url: str | None = None
    source_domain: str | None = None
    created_at_ms: int | None = None
    updated_at_ms: int | None = None


class NewsSourceStatusData(ApiSchema):
    provider_capabilities: JsonObject = Field(default_factory=dict)
    source_hygiene: JsonObject = Field(default_factory=dict)
    sources: list[JsonObject] = Field(default_factory=list)


class LiveMarketData(ApiSchema):
    target_type: str
    target_id: str
    status: str | None = None
    market: JsonObject | None = None


class TargetPostsData(ApiSchema):
    query: JsonObject
    score_window: JsonObject | None = None
    total_count: int | None = None
    returned_count: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None
    items: list[JsonObject] = Field(default_factory=list)


class TargetSocialTimelineData(ApiSchema):
    query: JsonObject
    summary: JsonObject | None = None
    market_candles: JsonObject | None = None
    stages: list[JsonObject] = Field(default_factory=list)
    buckets: list[JsonObject] = Field(default_factory=list)
    authors: list[JsonObject] = Field(default_factory=list)
    posts: list[JsonObject] = Field(default_factory=list)
    cascade: JsonObject | None = None
    returned_count: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None


class AccountAlertsData(ApiSchema):
    window: str
    alert_type: str | None = None
    items: list[JsonObject] = Field(default_factory=list)


class NotificationSummary(ApiSchema):
    subscriber_key: str | None = None
    unread_count: int = 0
    high_unread_count: int = 0
    critical_unread_count: int = 0
    highest_unread_severity: str | None = None
    account_unread_counts: JsonObject = Field(default_factory=dict)


class NotificationsData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)
    summary: NotificationSummary | JsonObject | None = None


class NotificationDeliveriesData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)


class NotificationReadData(ApiSchema):
    notification_id: str
    updated: bool


class NotificationReadAllData(ApiSchema):
    updated_count: int


class SourceEventDetail(ApiSchema):
    event_id: str
    timestamp_ms: int
    source_provider: str
    channel: str
    action: str
    author_handle: str | None = None
    author_name: str | None = None
    author_followers: int | None = None
    author_watched: bool = False
    text_clean: str | None = None
    canonical_url: str | None = None


class SourceEventsByIdsData(ApiSchema):
    events: list[SourceEventDetail] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)


class WatchlistHandleRowOverview(ApiSchema):
    handle: str
    last_source_event_at_ms: int | None = None
    recent_source_event_count: int = 0


class WatchlistHandlesOverviewData(ApiSchema):
    window: str
    items: list[WatchlistHandleRowOverview] = Field(default_factory=list)


class WatchlistOverviewQuery(ApiSchema):
    handle: str
    window: str


class WatchlistOverviewMetrics(ApiSchema):
    source_event_count: int = 0
    resolved_token_count: int = 0
    candidate_mention_count: int = 0
    narrative_count: int = 0
    last_source_event_at_ms: int | None = None


class WatchlistOverviewCluster(ApiSchema):
    label: str
    count: int = 0
    query: str
    kind: Literal["resolved_token", "candidate_mention", "narrative"]
    target_type: str | None = None
    target_id: str | None = None
    symbol: str | None = None
    source: str


class WatchlistHandleOverviewData(ApiSchema):
    query: WatchlistOverviewQuery
    metrics: WatchlistOverviewMetrics
    resolved_token_clusters: list[WatchlistOverviewCluster] = Field(default_factory=list)
    candidate_mention_clusters: list[WatchlistOverviewCluster] = Field(default_factory=list)
    narrative_clusters: list[WatchlistOverviewCluster] = Field(default_factory=list)
    clusters_truncated: bool = False
    risk_notes: list[str] = Field(default_factory=list)


class WatchlistHandleTimelineData(ApiSchema):
    query: JsonObject
    items: list[JsonObject] = Field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None


class ItemsData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)


class EnrichmentJobsData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)
    counts: JsonObject = Field(default_factory=dict)


class OpsDiagnosticsData(ApiSchema):
    schema_version: str
    generated_at_ms: int | None = None
    overall: JsonObject = Field(default_factory=dict)
    config: JsonObject = Field(default_factory=dict)
    database: JsonObject = Field(default_factory=dict)
    collector: JsonObject = Field(default_factory=dict)
    providers: list[JsonObject] = Field(default_factory=list)
    workers: list[JsonObject] = Field(default_factory=list)
    worker_lanes: JsonObject = Field(default_factory=dict)
    queues: list[JsonObject] = Field(default_factory=list)
    agent_execution: JsonObject = Field(default_factory=dict)
    domains: JsonObject = Field(default_factory=dict)
    suggested_checks: list[JsonObject] = Field(default_factory=list)


class OpsQueueData(ApiSchema):
    schema_version: str
    queue_name: str
    status_filter: str | None = None
    counts_by_status: JsonObject = Field(default_factory=dict)
    summary: JsonObject = Field(default_factory=dict)
    items: list[JsonObject] = Field(default_factory=list)


class LooseData(ApiSchema):
    pass
