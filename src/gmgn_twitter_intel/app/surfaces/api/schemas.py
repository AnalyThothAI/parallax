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


class StatusData(ApiSchema):
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    store: str | None = None
    snapshot_gate: JsonObject = Field(default_factory=dict)
    db: JsonObject | None = None
    provider_states: JsonObject = Field(default_factory=dict)
    workers: dict[str, WorkerStatusData] = Field(default_factory=dict)


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


class TokenCaseData(ApiSchema):
    target: JsonObject
    profile: JsonObject | None = None
    timeline: JsonObject
    posts: JsonObject
    agent_brief: JsonObject
    market_live: JsonObject


class TokenRadarData(ApiSchema):
    window: str
    scope: str
    targets: list[JsonObject] = Field(default_factory=list)
    attention: list[JsonObject] = Field(default_factory=list)
    projection: JsonObject = Field(default_factory=dict)


class StocksRadarData(ApiSchema):
    window: str | None = None
    scope: str | None = None
    rows: list[JsonObject] = Field(default_factory=list)
    items: list[JsonObject] = Field(default_factory=list)
    projection: JsonObject | None = None


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
    market_overlay: JsonObject | None = None
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


class SignalPulseData(ApiSchema):
    query: JsonObject | None = None
    summary: JsonObject | None = None
    items: list[JsonObject] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool | None = None
    total_count: int | None = None
    agent_worker_running: bool | None = None


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
    analyst: SignalPulseStagePayload | None = None
    critic: SignalPulseStagePayload | None = None
    judge: SignalPulseStagePayload | None = None
    research_only_gate: SignalPulseStagePayload | None = None


class SignalPulseItem(ApiSchema):
    candidate_id: str | None = None
    status: str | None = None
    target: JsonObject | None = None
    fact_card: JsonObject | None = None
    recommendation: JsonObject | None = None
    stages: SignalPulseStages | None = None


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


class LooseData(ApiSchema):
    pass
