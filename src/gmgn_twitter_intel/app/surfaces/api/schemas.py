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
    failed_workers: int = 0
    soft_timed_out_workers: int = 0
    hard_timed_out_workers: int = 0
    oldest_active_run_once_age_ms: int | None = None
    iteration_duration_p99_ms: float | None = None
    queue_depth: int | None = None


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
    last_started_at_ms: int | None = None
    last_finished_at_ms: int | None = None
    last_result: JsonObject | None = None
    last_error: str | None = None
    iteration_duration_p99_ms: float | None = None
    queue_depth: int | None = None
    pool_wait_ms_p99: float | None = None
    active_run_once_started_at_ms: int | None = None
    active_run_once_age_ms: int | None = None
    active_run_once_soft_timed_out_at_ms: int | None = None
    active_run_once_hard_timed_out_at_ms: int | None = None
    active_run_once_count: int = 0
    details: JsonObject = Field(default_factory=dict)


class NarrativeSemanticBacklog(ApiSchema):
    total_pending: int = 0
    estimated_semantic_drain_seconds: int = 0
    current_source_rows: int = 0
    semantic_rows_for_current_sources: int = 0
    missing_semantic_rows: int = 0
    admissions_with_missing_semantics: int = 0
    pending_existing_rows: int = 0
    queued: int = 0
    retryable: int = 0
    stale: int = 0
    unavailable: int = 0
    suppressed_current_digest_count: int = 0
    stale_fingerprint_current_digest_count: int = 0
    oldest_due_age_ms: int | None = None


class NarrativeRunHealth(ApiSchema):
    success: int = 0
    failure: int = 0
    timeout: int = 0


class NarrativeAdmissionHealth(ApiSchema):
    current_admissions: int = 0
    suppressed_admissions: int = 0
    current_source_events: int = 0
    current_independent_authors: int = 0


class NarrativeEpochHealth(ApiSchema):
    epoch_policy_version: str | None = None
    unsupported_window_admissions: int = 0
    last_ready_digest_count: int = 0
    updating_snapshot_count: int = 0
    material_delta_due_count: int = 0
    no_material_delta_deferred_count: int = 0
    last_ready_p50_age_ms: int | None = None
    last_ready_p95_age_ms: int | None = None
    delta_source_rows: int = 0
    delta_independent_authors: int = 0
    digest_refresh_due_by_window: dict[str, int] = Field(default_factory=dict)
    digest_refresh_deferred_by_epoch_policy: dict[str, int] = Field(default_factory=dict)


class NarrativeBacklogHealthData(ApiSchema):
    schema_version: str | None = None
    now_ms: int | None = None
    since_hours: int = 4
    realtime_windows: list[str] = Field(default_factory=list)
    realtime_scopes: list[str] = Field(default_factory=list)
    admissions: NarrativeAdmissionHealth = Field(default_factory=NarrativeAdmissionHealth)
    semantic_backlog: NarrativeSemanticBacklog = Field(default_factory=NarrativeSemanticBacklog)
    epoch: NarrativeEpochHealth = Field(default_factory=NarrativeEpochHealth)
    recent_runs: dict[str, NarrativeRunHealth] = Field(default_factory=dict)
    digest_status_counts: dict[str, int] = Field(default_factory=dict)
    digest_reason_counts: dict[str, int] = Field(default_factory=dict)
    pending_digest_count: int = 0
    estimated_digest_drain_seconds: int = 0


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
    display_status: Literal["current", "updating", "stale", "not_ready", "out_of_frontier", "unsupported_window"]
    epoch_id: str | None = None
    epoch_policy_version: str | None = None
    ready_source_fingerprint: str | None = None
    current_source_fingerprint: str | None = None
    ready_source_event_count: int = 0
    current_source_event_count: int = 0
    delta_source_event_count: int = 0
    delta_independent_author_count: int = 0
    delta_since_ms: int | None = None
    last_ready_computed_at_ms: int | None = None
    next_refresh_due_at_ms: int | None = None
    reason: str


class TokenDiscussionDigestData(ApiSchema):
    status: Literal["ready", "pending", "insufficient", "semantic_unavailable", "stale"]
    currentness: NarrativeCurrentnessData
    analysis_window: str | None = None
    source_window: str | None = None
    surface_window: str | None = None
    reuse_reason: str | None = None
    data_gaps: list[Any] = Field(default_factory=list)
    coverage: JsonObject = Field(default_factory=dict)


class NarrativeDeltaData(ApiSchema):
    display_status: str
    delta_source_event_count: int = 0
    delta_independent_author_count: int = 0
    label: str | None = None


class TokenCaseData(ApiSchema):
    target: JsonObject
    profile: JsonObject | None = None
    timeline: JsonObject
    posts: JsonObject
    discussion_digest: TokenDiscussionDigestData
    narrative_delta: NarrativeDeltaData = Field(default_factory=lambda: NarrativeDeltaData(display_status="not_ready"))
    narrative_clusters: list[JsonObject] = Field(default_factory=list)
    pulse_overlay: JsonObject | None = None
    market_live: JsonObject
    cex_detail: JsonObject | None = None


class TokenRadarRowData(ApiSchema):
    discussion_digest: TokenDiscussionDigestData | None = None


class TokenRadarData(ApiSchema):
    window: str
    scope: str
    targets: list[TokenRadarRowData] = Field(default_factory=list)
    attention: list[TokenRadarRowData] = Field(default_factory=list)
    projection: JsonObject = Field(default_factory=dict)


class StocksRadarData(ApiSchema):
    window: str | None = None
    scope: str | None = None
    rows: list[JsonObject] = Field(default_factory=list)
    items: list[JsonObject] = Field(default_factory=list)
    projection: JsonObject | None = None


class NewsData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)
    next_cursor: str | None = None


class NewsObjectData(ApiSchema):
    pass


class NewsSourceStatusData(ApiSchema):
    provider_capabilities: JsonObject = Field(default_factory=dict)
    source_hygiene: JsonObject = Field(default_factory=dict)
    sources: list[JsonObject] = Field(default_factory=list)


class EquityEventsData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)
    next_cursor: str | None = None


class EquityEventObjectData(ApiSchema):
    pass


class EquityEventCalendarData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)


class EquityEventTimelineData(ApiSchema):
    items: list[JsonObject] = Field(default_factory=list)
    next_cursor: str | None = None


class EquityEventSourceStatusData(ApiSchema):
    sources: list[JsonObject] = Field(default_factory=list)


class EquityEventSummaryData(ApiSchema):
    p0_open_count: int = 0
    today_count: int = 0
    brief_pending_count: int = 0
    latest_event_at_ms: int | None = None


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


class SignalPulseStagePayload(ApiSchema):
    stage: str | None = None
    route: str | None = None
    status: str | None = None
    model: str | None = None
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    latency_ms: int | None = None
    attempt_index: int | None = None
    response: JsonObject | None = None
    error: str | None = None


class SignalPulseStages(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    evidence_pack: SignalPulseStagePayload | None = None
    evidence_completeness_gate: SignalPulseStagePayload | None = None
    signal_analyst: SignalPulseStagePayload | None = None
    bear_case: SignalPulseStagePayload | None = None
    claim_verifier: SignalPulseStagePayload | None = None
    risk_portfolio_judge: SignalPulseStagePayload | None = None
    recommendation_clipper: SignalPulseStagePayload | None = None
    deterministic_eval: SignalPulseStagePayload | None = None
    write_gate: SignalPulseStagePayload | None = None


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
    agent_worker_running: bool | None = None
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
    claim_verification: JsonObject | None = None
    evidence_gate: JsonObject | None = None
    fact_card: JsonObject | None = None
    agent_run_id: str | None = None
    pulse_version: str | None = None
    gate_version: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    created_at_ms: int | None = None
    updated_at_ms: int | None = None
    playbooks: list[JsonObject] = Field(default_factory=list)
    stages: SignalPulseStages | None = None


class SignalPulseData(ApiSchema):
    query: JsonObject | None = None
    health: SignalPulseHealth | None = None
    summary: JsonObject | None = None
    items: list[SignalPulseItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool | None = None
    total_count: int | None = None
    returned_count: int | None = None
    agent_worker_running: bool | None = None


class SocialEventDetail(ApiSchema):
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


class SocialEventsByIdsData(ApiSchema):
    events: list[SocialEventDetail] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)


class WatchlistHandleSummaryData(ApiSchema):
    handle: str
    status: str
    generated_at_ms: int | None = None
    staleness_ms: int | None = None
    is_stale: bool = False
    pending_recompute: bool = False
    signal_count: int = 0
    input_event_count: int = 0
    signal_count_at_generation: int = 0
    model: str | None = None
    summary_zh: str = ""
    topics: list[JsonObject] = Field(default_factory=list)


class WatchlistHandleRowOverview(ApiSchema):
    handle: str
    last_source_event_at_ms: int | None = None
    recent_source_event_count: int = 0
    recent_signal_event_count: int = 0
    total_signal_event_count: int = 0
    summary_status: Literal["ready", "not_ready"]
    summary_is_stale: bool = False


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
