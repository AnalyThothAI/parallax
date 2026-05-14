from __future__ import annotations

from typing import Any

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
    collector: JsonObject | None = None
    enrichment: JsonObject | None = None
    token_radar_projection: JsonObject | None = None
    anchor_price: JsonObject | None = None
    live_price_gateway: JsonObject | None = None
    notifications: JsonObject | None = None
    watchlist_handle_summary: JsonObject | None = None


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
    error: str | None = None


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
