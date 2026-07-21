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
    soft_timed_out_workers: int = 0
    hard_timed_out_workers: int = 0
    oldest_active_run_once_age_ms: int | None = None
    iteration_duration_p99_ms: float | None = None
    queue_depth: int | None = None
    queue_health: JsonObject = Field(default_factory=dict)


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
    queue_depth: int | None = None
    queue_health: JsonObject = Field(default_factory=dict)
    pool_wait_ms_p99: float | None = None
    active_run_once_started_at_ms: int | None = None
    active_run_once_age_ms: int | None = None
    active_run_once_soft_timed_out_at_ms: int | None = None
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
    pulse_overlay: JsonObject | None = None
    market_live: JsonObject
    cex_detail: JsonObject | None = None


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


class AccountQualityData(ApiSchema):
    query: JsonObject | None = None
    accounts: list[JsonObject] = Field(default_factory=list)


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


class SignalPulseBullBearView(ApiSchema):
    strength: str
    thesis_zh: str
    supporting_event_ids: list[str]


class SignalPulsePlaybook(ApiSchema):
    has_playbook: bool
    watch_signals: list[str]
    exit_triggers: list[str]
    monitoring_horizon: str


class SignalPulseDecision(ApiSchema):
    route: str | None
    recommendation: str | None
    confidence: float | None
    summary_zh: str | None
    abstain_reason: str | None
    narrative_archetype: str | None
    narrative_thesis_zh: str | None
    bull_view: SignalPulseBullBearView | None
    bear_view: SignalPulseBullBearView | None
    playbook: SignalPulsePlaybook | None
    evidence_event_ids: list[str]
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    risk_evidence_refs: list[str] = Field(default_factory=list)
    data_gap_refs: list[str] = Field(default_factory=list)
    evidence_event_urls: dict[str, str]
    invalidation_conditions: list[str]
    residual_risks: list[str]


class SignalPulseHealth(ApiSchema):
    pulse_ready: bool | None = None
    public_ready: bool | None = None
    candidate_count: int | None = None
    public_candidate_count: int | None = None
    hidden_candidate_count: int | None = None
    blocked_low_information_count: int | None = None
    dead_job_count: int | None = None
    market_ready_rate: float | None = None
    window: str | None = None
    scope: str | None = None
    since_hours: int | None = None
    publish_status: str | None = None
    reasons: list[str] = Field(default_factory=list)
    latest_packet_created_at_ms: int | None = None
    latest_agent_run_finished_at_ms: int | None = None
    latest_public_candidate_updated_at_ms: int | None = None
    latest_hidden_hold_candidate_updated_at_ms: int | None = None
    due_jobs: int | None = None
    claimed_jobs: int | None = None
    failed_jobs_4h: int | None = None
    agent_runs_4h: int | None = None
    agent_failed_4h: int | None = None
    agent_failure_rate_4h: float | None = None
    unknown_ref_failures_4h: int | None = None
    unknown_ref_failure_rate_4h: float | None = None
    unsupported_claim_failures_4h: int | None = None
    unsupported_claim_failure_rate_4h: float | None = None
    hidden_abstain_4h: int | None = None
    hidden_hold_publish_4h: int | None = None
    hidden_insufficient_evidence_4h: int | None = None
    public_candidates_4h: int | None = None


class SignalPulseItem(ApiSchema):
    candidate_id: str | None = None
    candidate_type: str | None = None
    subject_key: str | None = None
    subject: JsonObject | None = None
    target_type: str | None = None
    target_id: str | None = None
    symbol: str | None = None
    window: str | None = None
    scope: str | None = None
    evidence_status: str | None = None
    decision_status: str | None = None
    display_status: str | None = None
    evidence_packet_hash: str | None = None
    verdict: str | None = None
    social_phase: str | None = None
    candidate_score: float | None = None
    score_band: str | None = None
    gate_reasons: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    factor_snapshot: JsonObject | None = None
    decision: SignalPulseDecision | None = None
    gate: JsonObject | None = None
    fact_card: JsonObject | None = None
    pulse_version: str | None = None
    gate_version: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    created_at_ms: int | None = None
    updated_at_ms: int | None = None
    playbooks: list[JsonObject] = Field(default_factory=list)


class SignalPulseData(ApiSchema):
    query: JsonObject | None = None
    health: SignalPulseHealth | None = None
    summary: JsonObject | None = None
    items: list[SignalPulseItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool | None = None
    total_count: int | None = None
    returned_count: int | None = None


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
    recent_signal_event_count: int = 0
    total_signal_event_count: int = 0


class WatchlistHandlesOverviewData(ApiSchema):
    window: str
    items: list[WatchlistHandleRowOverview] = Field(default_factory=list)


class WatchlistOverviewQuery(ApiSchema):
    handle: str
    scope: Literal["signal", "all"]
    window: str


class WatchlistOverviewMetrics(ApiSchema):
    source_event_count: int = 0
    signal_event_count: int = 0
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
