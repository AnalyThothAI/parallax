from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from parallax.app.runtime.current_read_model_publisher import FORBIDDEN_SERVING_IDENTITY_COLUMNS


class WorkerKind(StrEnum):
    FACT_INGEST = "fact_ingest"
    FACT_LIFECYCLE = "fact_lifecycle"
    PROJECTION = "projection"
    AGENT_SIDE_EFFECT = "agent_side_effect"
    NOTIFICATION_RULE = "notification_rule"
    NOTIFICATION_DELIVERY = "notification_delivery"
    CACHE_FANOUT = "cache_fanout"
    MAINTENANCE = "maintenance"


class WorkerLane(StrEnum):
    INGEST = "ingest"
    IDENTITY_MARKET_FACT = "identity_market_fact"
    PROJECTION = "projection"
    AGENT = "agent"
    NOTIFICATION = "notification"
    MAINTENANCE_CACHE = "maintenance_cache"


@dataclass(frozen=True, slots=True)
class WorkerManifest:
    name: str
    domain: str
    factory: str
    lane: WorkerLane
    kind: WorkerKind
    worker_class: str
    start_priority: int
    input_contract: tuple[str, ...]
    ordering_keys: tuple[str, ...]
    writes_input_observations: tuple[str, ...] = ()
    writes_facts: tuple[str, ...] = ()
    writes_read_models: tuple[str, ...] = ()
    writes_control_plane: tuple[str, ...] = ()
    current_read_model_identities: tuple[tuple[str, tuple[str, ...]], ...] = ()
    uses_provider_io: bool = False
    idempotency_evidence: tuple[str, ...] = ()
    side_effect_ledgers: tuple[str, ...] = ()
    dirty_target_tables: tuple[str, ...] = ()
    queue_depth_table: str | None = None
    queue_health_tables: tuple[str, ...] = ()
    advisory_lock_key: str | None = None
    wakes_on: tuple[str, ...] = ()
    wakes_out: tuple[str, ...] = ()


_WORKER_MANIFESTS: tuple[WorkerManifest, ...] = (
    WorkerManifest(
        name="collector",
        domain="ingestion",
        factory="ingestion.py",
        lane=WorkerLane.INGEST,
        kind=WorkerKind.FACT_INGEST,
        worker_class="parallax.domains.ingestion.runtime.collector_service.CollectorService",
        start_priority=10,
        input_contract=("gmgn public websocket frames",),
        ordering_keys=("provider_event_id", "received_at_ms"),
        writes_input_observations=("raw_frames",),
        writes_facts=("events", "token_intents"),
        uses_provider_io=True,
        idempotency_evidence=("events provider event identity",),
        wakes_out=("event_written",),
    ),
    WorkerManifest(
        name="market_tick_stream",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.INGEST,
        kind=WorkerKind.FACT_INGEST,
        worker_class=("parallax.domains.asset_market.runtime.market_tick_stream_worker.MarketTickStreamWorker"),
        start_priority=30,
        input_contract=("token_capture_tier stream targets", "stream provider ticks"),
        ordering_keys=("target_type", "target_id", "observed_at_ms"),
        writes_facts=("market_ticks",),
        uses_provider_io=True,
        idempotency_evidence=("market tick provider/time natural key",),
        wakes_out=("market_tick_written",),
    ),
    WorkerManifest(
        name="market_tick_poll",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.INGEST,
        kind=WorkerKind.FACT_INGEST,
        worker_class="parallax.domains.asset_market.runtime.market_tick_poll_worker.MarketTickPollWorker",
        start_priority=40,
        input_contract=("token_capture_tier poll targets", "quote provider ticks"),
        ordering_keys=("target_type", "target_id", "observed_at_ms"),
        writes_facts=("market_ticks",),
        uses_provider_io=True,
        idempotency_evidence=("market tick provider/time natural key",),
        wakes_out=("market_tick_written",),
    ),
    WorkerManifest(
        name="market_tick_current_projection",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=(
            "parallax.domains.asset_market.runtime.market_tick_current_projection_worker."
            "MarketTickCurrentProjectionWorker"
        ),
        start_priority=75,
        input_contract=("market_tick_current_dirty_targets",),
        ordering_keys=("target_type", "target_id"),
        writes_read_models=("market_tick_current",),
        writes_control_plane=("market_tick_current_dirty_targets", "token_radar_dirty_targets"),
        current_read_model_identities=(("market_tick_current", ("target_type", "target_id")),),
        idempotency_evidence=("market_tick_current target primary key", "dirty target claim/retry state"),
        dirty_target_tables=("market_tick_current_dirty_targets",),
        advisory_lock_key="2026052401",
        wakes_on=("market_tick_written",),
        wakes_out=("market_tick_current_updated",),
    ),
    WorkerManifest(
        name="event_anchor_backfill",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        kind=WorkerKind.FACT_LIFECYCLE,
        worker_class=("parallax.domains.asset_market.runtime.event_anchor_backfill_worker.EventAnchorBackfillWorker"),
        start_priority=45,
        input_contract=("event_anchor_backfill_jobs",),
        ordering_keys=("event_id", "intent_id", "target_id"),
        writes_facts=("enriched_events", "market_ticks"),
        writes_control_plane=("event_anchor_backfill_jobs",),
        uses_provider_io=True,
        idempotency_evidence=("event_anchor_backfill_jobs job state", "enriched_events event/intent identity"),
        queue_depth_table="event_anchor_backfill_jobs",
        queue_health_tables=("event_anchor_backfill_jobs",),
    ),
    WorkerManifest(
        name="token_capture_tier",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=("parallax.domains.asset_market.runtime.token_capture_tier_worker.TokenCaptureTierWorker"),
        start_priority=20,
        input_contract=("token_capture_tier_dirty_targets",),
        ordering_keys=("target_type", "target_id"),
        writes_read_models=("token_capture_tier",),
        writes_control_plane=("token_capture_tier_dirty_targets",),
        current_read_model_identities=(("token_capture_tier", ("target_type", "target_id")),),
        idempotency_evidence=("token_capture_tier target primary key", "dirty target payload hash"),
        dirty_target_tables=("token_capture_tier_dirty_targets",),
        advisory_lock_key="2026051503",
    ),
    WorkerManifest(
        name="live_price_gateway",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.MAINTENANCE_CACHE,
        kind=WorkerKind.CACHE_FANOUT,
        worker_class="parallax.domains.asset_market.runtime.live_price_gateway.LivePriceGateway",
        start_priority=50,
        input_contract=("token_capture_tier", "market_ticks"),
        ordering_keys=("target_type", "target_id"),
        idempotency_evidence=("cache target key replacement",),
    ),
    WorkerManifest(
        name="resolution_refresh",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        kind=WorkerKind.FACT_LIFECYCLE,
        worker_class=("parallax.domains.asset_market.runtime.resolution_refresh_worker.ResolutionRefreshWorker"),
        start_priority=60,
        input_contract=("token_intents", "asset_identity_resolution backlog"),
        ordering_keys=("target_type", "lookup_key"),
        writes_facts=("asset_identity_*", "token_intent_resolutions"),
        writes_control_plane=(
            "token_discovery_dirty_lookup_keys",
            "token_radar_dirty_targets",
            "narrative_admission_dirty_targets",
        ),
        idempotency_evidence=("asset identity unique lookup keys", "token_intent_resolutions intent identity"),
        dirty_target_tables=("token_discovery_dirty_lookup_keys",),
        wakes_out=("resolution_updated",),
    ),
    WorkerManifest(
        name="asset_profile_refresh",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        kind=WorkerKind.FACT_LIFECYCLE,
        worker_class=("parallax.domains.asset_market.runtime.asset_profile_refresh_worker.AssetProfileRefreshWorker"),
        start_priority=70,
        input_contract=("asset_profile_refresh_targets",),
        ordering_keys=("target_type", "target_id", "provider"),
        writes_facts=("asset_profiles",),
        writes_control_plane=("asset_profile_refresh_targets", "token_profile_current_dirty_targets"),
        uses_provider_io=True,
        idempotency_evidence=("asset_profiles target/provider identity", "dirty target payload hash"),
        dirty_target_tables=("asset_profile_refresh_targets",),
    ),
    WorkerManifest(
        name="token_image_mirror",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        kind=WorkerKind.FACT_LIFECYCLE,
        worker_class=("parallax.domains.asset_market.runtime.token_image_mirror_worker.TokenImageMirrorWorker"),
        start_priority=82,
        input_contract=("token_image_source_dirty_targets",),
        ordering_keys=("target_type", "target_id", "source_url"),
        writes_facts=("token_image_assets",),
        writes_control_plane=("token_image_source_dirty_targets", "token_profile_current_dirty_targets"),
        uses_provider_io=True,
        idempotency_evidence=("token_image_assets source digest", "dirty target payload hash"),
        dirty_target_tables=("token_image_source_dirty_targets",),
        advisory_lock_key="2026052111",
    ),
    WorkerManifest(
        name="token_profile_current",
        domain="asset_market",
        factory="asset_market.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=("parallax.domains.asset_market.runtime.token_profile_current_worker.TokenProfileCurrentWorker"),
        start_priority=85,
        input_contract=("token_profile_current_dirty_targets",),
        ordering_keys=("target_type", "target_id"),
        writes_read_models=("token_profile_current",),
        writes_control_plane=("token_profile_current_dirty_targets", "token_image_source_dirty_targets"),
        current_read_model_identities=(("token_profile_current", ("target_type", "target_id")),),
        idempotency_evidence=(
            "token_profile_current target primary key",
            "token image source dirty target source_url_hash/target key",
            "dirty target payload hash",
        ),
        dirty_target_tables=("token_profile_current_dirty_targets",),
        advisory_lock_key="2026051702",
    ),
    WorkerManifest(
        name="token_radar_projection",
        domain="token_intel",
        factory="token_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=("parallax.domains.token_intel.runtime.token_radar_projection_worker.TokenRadarProjectionWorker"),
        start_priority=80,
        input_contract=("token_radar_source_dirty_events", "token_radar_dirty_targets"),
        ordering_keys=("window", "scope", "venue", "target_type", "target_id", "source_event_id"),
        writes_read_models=(
            "token_radar_rank_source_events",
            "token_radar_target_features",
            "token_radar_current_rows",
            "token_radar_publication_state",
            "token_radar_target_first_seen",
            "projection_offsets",
            "token_score_evaluations",
        ),
        writes_control_plane=(
            "token_radar_source_dirty_events",
            "token_radar_dirty_targets",
            "projection_runs",
            "pulse_trigger_dirty_targets",
            "narrative_admission_dirty_targets",
        ),
        current_read_model_identities=(
            (
                "token_radar_rank_source_events",
                (
                    "projection_version",
                    "target_type_key",
                    "identity_id",
                    "source_kind",
                    "source_id",
                ),
            ),
            (
                "token_radar_target_features",
                ("projection_version", "window", "scope", "lane", "target_type_key", "identity_id"),
            ),
            (
                "token_radar_current_rows",
                ("projection_version", "window", "scope", "venue", "lane", "target_type_key", "identity_id"),
            ),
            ("token_radar_publication_state", ("projection_version", "window", "scope", "venue")),
            (
                "token_radar_target_first_seen",
                ("projection_version", "window", "scope", "venue", "target_type_key", "identity_id"),
            ),
            ("projection_offsets", ("projection_name",)),
            ("token_score_evaluations", ("horizon", "window", "scope", "score_version", "bucket_label")),
        ),
        idempotency_evidence=("token radar window/scope/target primary key", "projection version"),
        dirty_target_tables=("token_radar_source_dirty_events", "token_radar_dirty_targets"),
        advisory_lock_key="2026051501",
        wakes_on=("market_tick_current_updated", "resolution_updated"),
        wakes_out=("token_radar_updated",),
    ),
    WorkerManifest(
        name="narrative_admission",
        domain="narrative_intel",
        factory="narrative_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=("parallax.domains.narrative_intel.runtime.narrative_admission_worker.NarrativeAdmissionWorker"),
        start_priority=87,
        input_contract=("narrative_admission_dirty_targets",),
        ordering_keys=("window", "scope", "target_type", "target_id"),
        writes_read_models=("narrative_admissions",),
        writes_control_plane=("narrative_admission_dirty_targets",),
        current_read_model_identities=(("narrative_admissions", ("target_type", "target_id", "window", "scope")),),
        idempotency_evidence=("narrative admission target/window identity", "dirty target payload hash"),
        dirty_target_tables=("narrative_admission_dirty_targets",),
        advisory_lock_key="2026051901",
        wakes_on=("token_radar_updated", "resolution_updated"),
    ),
    WorkerManifest(
        name="news_fetch",
        domain="news_intel",
        factory="news_intel.py",
        lane=WorkerLane.INGEST,
        kind=WorkerKind.FACT_INGEST,
        worker_class="parallax.domains.news_intel.runtime.news_fetch_worker.NewsFetchWorker",
        start_priority=90,
        input_contract=("news sources due queue", "news provider documents"),
        ordering_keys=("source_id", "published_at_ms", "external_id"),
        writes_facts=("news_sources", "news_fetch_runs", "news_provider_items", "news_items"),
        writes_control_plane=("news_projection_dirty_targets",),
        uses_provider_io=True,
        idempotency_evidence=("news item source/external identity",),
        advisory_lock_key="2026051905",
    ),
    WorkerManifest(
        name="news_item_process",
        domain="news_intel",
        factory="news_intel.py",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        kind=WorkerKind.FACT_LIFECYCLE,
        worker_class="parallax.domains.news_intel.runtime.news_item_process_worker.NewsItemProcessWorker",
        start_priority=91,
        input_contract=("news items awaiting processing",),
        ordering_keys=("news_item_id",),
        writes_facts=(
            "news_item_entities",
            "news_token_mentions",
            "news_fact_candidates",
            "news_items.content_class",
            "news_items.content_tags_json",
            "news_items.content_classification_json",
        ),
        writes_control_plane=("news_projection_dirty_targets",),
        idempotency_evidence=("news_item_id processing state", "news fact natural keys"),
        advisory_lock_key="2026051902",
        wakes_on=("news_item_written",),
        wakes_out=("news_item_processed",),
    ),
    WorkerManifest(
        name="news_item_brief",
        domain="news_intel",
        factory="news_intel.py",
        lane=WorkerLane.AGENT,
        kind=WorkerKind.AGENT_SIDE_EFFECT,
        worker_class="parallax.domains.news_intel.runtime.news_item_brief_worker.NewsItemBriefWorker",
        start_priority=94,
        input_contract=("semantic news item brief work",),
        ordering_keys=("news_item_id", "artifact_version_hash"),
        writes_read_models=("news_item_agent_briefs",),
        writes_control_plane=("news_projection_dirty_targets", "news_item_agent_runs"),
        current_read_model_identities=(("news_item_agent_briefs", ("news_item_id",)),),
        idempotency_evidence=("news_item_agent_briefs(news_item_id)", "news_item_agent_runs(run_id)"),
        side_effect_ledgers=("news_item_agent_runs", "news_item_agent_briefs"),
        dirty_target_tables=("news_projection_dirty_targets",),
        advisory_lock_key="2026052001",
        wakes_on=("news_item_processed",),
        wakes_out=("news_item_brief_updated",),
    ),
    WorkerManifest(
        name="news_page_projection",
        domain="news_intel",
        factory="news_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class="parallax.domains.news_intel.runtime.news_page_projection_worker.NewsPageProjectionWorker",
        start_priority=95,
        input_contract=("semantic news page reprojection work",),
        ordering_keys=("row_id", "news_item_id"),
        writes_read_models=("news_page_rows",),
        writes_control_plane=("news_projection_dirty_targets",),
        current_read_model_identities=(("news_page_rows", ("row_id",)),),
        idempotency_evidence=("news page projection target identity", "dirty target payload hash"),
        dirty_target_tables=("news_projection_dirty_targets",),
        advisory_lock_key="2026051904",
        wakes_on=(
            "news_item_written",
            "news_item_processed",
            "news_item_brief_updated",
            "news_page_dirty",
        ),
    ),
    WorkerManifest(
        name="news_source_quality_projection",
        domain="news_intel",
        factory="news_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=(
            "parallax.domains.news_intel.runtime.news_source_quality_projection_worker."
            "NewsSourceQualityProjectionWorker"
        ),
        start_priority=95,
        input_contract=("semantic news source-quality refresh/window work",),
        ordering_keys=("source_id", "window"),
        writes_read_models=("news_source_quality_rows",),
        writes_control_plane=("news_projection_dirty_targets",),
        current_read_model_identities=(("news_source_quality_rows", ("source_id", "window")),),
        idempotency_evidence=("news source/window projection identity", "dirty target payload hash"),
        dirty_target_tables=("news_projection_dirty_targets",),
        advisory_lock_key="2026052201",
        wakes_on=("news_item_written",),
    ),
    WorkerManifest(
        name="cex_oi_radar_board",
        domain="cex_market_intel",
        factory="cex_market_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=("parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker.CexOiRadarBoardWorker"),
        start_priority=95,
        input_contract=("cex market universe", "open interest providers"),
        ordering_keys=("provider", "exchange", "quote_symbol", "contract_type", "period", "target_id"),
        writes_read_models=("cex_oi_radar_publication_state", "cex_oi_radar_rows", "cex_detail_snapshots"),
        uses_provider_io=True,
        idempotency_evidence=("cex oi board symbol/period snapshot identity",),
        current_read_model_identities=(
            ("cex_oi_radar_publication_state", ("board_key",)),
            (
                "cex_oi_radar_rows",
                (
                    "board_provider",
                    "board_exchange",
                    "board_quote_symbol",
                    "board_contract_type",
                    "period",
                    "target_id",
                ),
            ),
            ("cex_detail_snapshots", ("exchange", "native_market_id")),
        ),
        advisory_lock_key="2026052108",
    ),
    WorkerManifest(
        name="macro_sync",
        domain="macro_intel",
        factory="macro_intel.py",
        lane=WorkerLane.INGEST,
        kind=WorkerKind.FACT_INGEST,
        worker_class="parallax.domains.macro_intel.runtime.macro_sync_worker.MacroSyncWorker",
        start_priority=80,
        input_contract=("macro_sync_windows", "macrodata macro-core history bundle"),
        ordering_keys=("source_name", "bundle_name", "window_start", "window_end"),
        writes_facts=("macro_observations",),
        writes_control_plane=(
            "macro_import_runs",
            "macro_sync_windows",
            "macro_sync_runs",
            "macro_projection_dirty_targets",
        ),
        uses_provider_io=True,
        idempotency_evidence=("macro observation concept/source/series/date identity", "sync window identity"),
        advisory_lock_key="2026052711",
        wakes_out=("macro_observations_imported",),
    ),
    WorkerManifest(
        name="macro_view_projection",
        domain="macro_intel",
        factory="macro_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class="parallax.domains.macro_intel.runtime.macro_view_projection_worker.MacroViewProjectionWorker",
        start_priority=95,
        input_contract=("macro_projection_dirty_targets", "macro_observation_series_rows current"),
        ordering_keys=("concept_key", "series_key", "observed_at"),
        writes_read_models=(
            "macro_observation_series_rows",
            "macro_observation_series_publication_state",
            "macro_view_snapshots",
        ),
        writes_control_plane=("macro_projection_dirty_targets",),
        current_read_model_identities=(
            ("macro_observation_series_rows", ("projection_version", "concept_key", "observed_at")),
            ("macro_observation_series_publication_state", ("projection_version",)),
            ("macro_view_snapshots", ("projection_version",)),
        ),
        idempotency_evidence=("macro series/observation identity",),
        dirty_target_tables=("macro_projection_dirty_targets",),
        advisory_lock_key="2026052109",
        wakes_on=("macro_observations_imported",),
        wakes_out=("macro_view_snapshot_updated",),
    ),
    WorkerManifest(
        name="macro_daily_brief_projection",
        domain="macro_intel",
        factory="macro_intel.py",
        lane=WorkerLane.PROJECTION,
        kind=WorkerKind.PROJECTION,
        worker_class=(
            "parallax.domains.macro_intel.runtime.macro_daily_brief_projection_worker."
            "MacroDailyBriefProjectionWorker"
        ),
        start_priority=96,
        input_contract=("macro_view_snapshots current", "macro_observation_series_rows current"),
        ordering_keys=("brief_key",),
        writes_read_models=("macro_daily_briefs",),
        current_read_model_identities=(("macro_daily_briefs", ("brief_key",)),),
        idempotency_evidence=("macro_daily_briefs brief_key payload hash",),
        advisory_lock_key="2026060901",
        wakes_on=("macro_view_snapshot_updated",),
    ),
    WorkerManifest(
        name="pulse_candidate",
        domain="pulse_lab",
        factory="pulse.py",
        lane=WorkerLane.AGENT,
        kind=WorkerKind.AGENT_SIDE_EFFECT,
        worker_class="parallax.domains.pulse_lab.runtime.pulse_candidate_worker.PulseCandidateWorker",
        start_priority=96,
        input_contract=("pulse_trigger_dirty_targets", "pulse_agent_jobs"),
        ordering_keys=("window", "scope", "target_type", "target_id", "candidate_id"),
        writes_read_models=(
            "pulse_candidate_edge_state",
            "pulse_candidates",
            "pulse_playbook_snapshots",
        ),
        writes_control_plane=(
            "pulse_trigger_dirty_targets",
            "pulse_agent_jobs",
            "pulse_agent_runs",
            "pulse_candidate_run_budget",
            "pulse_target_run_budget",
            "pulse_agent_run_steps",
            "pulse_agent_runtime_versions",
            "pulse_agent_eval_cases",
            "pulse_agent_eval_results",
        ),
        current_read_model_identities=(
            ("pulse_candidate_edge_state", ("candidate_id",)),
            ("pulse_candidates", ("candidate_id",)),
            ("pulse_playbook_snapshots", ("playbook_id",)),
        ),
        idempotency_evidence=("pulse candidate id", "pulse_agent_jobs candidate identity", "pulse_agent_runs(run_id)"),
        side_effect_ledgers=("pulse_agent_jobs", "pulse_agent_runs", "pulse_agent_run_steps", "pulse_candidates"),
        dirty_target_tables=("pulse_trigger_dirty_targets",),
        queue_depth_table="pulse_agent_jobs",
        advisory_lock_key="2026051502",
        wakes_on=("token_radar_updated",),
    ),
    WorkerManifest(
        name="notification_rule",
        domain="notifications",
        factory="notifications.py",
        lane=WorkerLane.NOTIFICATION,
        kind=WorkerKind.NOTIFICATION_RULE,
        worker_class="parallax.domains.notifications.runtime.notification_worker.NotificationWorker",
        start_priority=120,
        input_contract=("pulse_candidates", "token radar read models", "news_page_rows", "watchlist read models"),
        ordering_keys=("rule_id", "entity_type", "entity_key"),
        writes_facts=("notifications",),
        writes_control_plane=("notification_deliveries",),
        idempotency_evidence=("notifications rule/entity dedupe key", "notification_deliveries(delivery_id)"),
        wakes_out=("notification_delivery_due",),
    ),
    WorkerManifest(
        name="notification_delivery",
        domain="notifications",
        factory="notifications.py",
        lane=WorkerLane.NOTIFICATION,
        kind=WorkerKind.NOTIFICATION_DELIVERY,
        worker_class=("parallax.domains.notifications.runtime.notification_delivery.NotificationDeliveryWorker"),
        start_priority=130,
        input_contract=("notification_deliveries",),
        ordering_keys=("delivery_id", "channel"),
        writes_control_plane=("notification_deliveries",),
        idempotency_evidence=("notification_deliveries(delivery_id) status transition",),
        side_effect_ledgers=("notification_deliveries",),
        queue_depth_table="notification_deliveries",
    ),
)


def all_worker_manifests() -> tuple[WorkerManifest, ...]:
    return _WORKER_MANIFESTS


def manifest_by_name() -> dict[str, WorkerManifest]:
    return {manifest.name: manifest for manifest in _WORKER_MANIFESTS}


def require_worker_manifest(name: str) -> WorkerManifest:
    try:
        return manifest_by_name()[name]
    except KeyError as exc:
        raise ValueError(f"unknown worker manifest: {name}") from exc


def manifests_by_lane() -> dict[WorkerLane, tuple[WorkerManifest, ...]]:
    return {lane: tuple(manifest for manifest in _WORKER_MANIFESTS if manifest.lane is lane) for lane in WorkerLane}


def manifest_names_for_factory(factory: str) -> frozenset[str]:
    return frozenset(manifest.name for manifest in _WORKER_MANIFESTS if manifest.factory == factory)


def worker_class_by_name() -> dict[str, str]:
    return {manifest.name: manifest.worker_class for manifest in _WORKER_MANIFESTS}


def worker_start_priority() -> dict[str, int]:
    return {manifest.name: manifest.start_priority for manifest in _WORKER_MANIFESTS}


def worker_queue_depth_tables() -> dict[str, str]:
    return {
        manifest.name: manifest.queue_depth_table
        for manifest in _WORKER_MANIFESTS
        if manifest.queue_depth_table is not None
    }


def worker_queue_health_tables() -> dict[str, tuple[str, ...]]:
    return {
        manifest.name: _dedupe(
            (
                *((manifest.queue_depth_table,) if manifest.queue_depth_table else ()),
                *manifest.dirty_target_tables,
                *manifest.queue_health_tables,
            )
        )
        for manifest in _WORKER_MANIFESTS
        if manifest.queue_depth_table or manifest.dirty_target_tables or manifest.queue_health_tables
    }


def worker_dirty_target_tables() -> dict[str, tuple[str, ...]]:
    return {
        manifest.name: manifest.dirty_target_tables for manifest in _WORKER_MANIFESTS if manifest.dirty_target_tables
    }


def worker_names() -> tuple[str, ...]:
    return tuple(manifest.name for manifest in _WORKER_MANIFESTS)


def _validate_worker_manifests() -> None:
    names = [manifest.name for manifest in _WORKER_MANIFESTS]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(f"duplicate worker manifest names: {duplicate_names}")

    missing_idempotency = [manifest.name for manifest in _WORKER_MANIFESTS if not manifest.idempotency_evidence]
    if missing_idempotency:
        raise ValueError(f"worker manifests missing idempotency evidence: {missing_idempotency}")

    missing_side_effect_ledgers = [
        manifest.name
        for manifest in _WORKER_MANIFESTS
        if manifest.kind in {WorkerKind.AGENT_SIDE_EFFECT, WorkerKind.NOTIFICATION_DELIVERY}
        and not manifest.side_effect_ledgers
    ]
    if missing_side_effect_ledgers:
        raise ValueError(f"side-effect worker manifests missing ledgers: {missing_side_effect_ledgers}")

    missing_dirty_control_owner = {
        manifest.name: sorted(set(manifest.dirty_target_tables) - set(manifest.writes_control_plane))
        for manifest in _WORKER_MANIFESTS
        if set(manifest.dirty_target_tables) - set(manifest.writes_control_plane)
    }
    if missing_dirty_control_owner:
        raise ValueError(f"dirty target tables missing from writes_control_plane: {missing_dirty_control_owner}")

    missing_queue_health_owner = {
        manifest.name: sorted(
            set(manifest.queue_health_tables)
            - set(
                (
                    *manifest.writes_facts,
                    *manifest.writes_input_observations,
                    *manifest.writes_read_models,
                    *manifest.writes_control_plane,
                    *manifest.side_effect_ledgers,
                )
            )
        )
        for manifest in _WORKER_MANIFESTS
        if set(manifest.queue_health_tables)
        - set(
            (
                *manifest.writes_facts,
                *manifest.writes_input_observations,
                *manifest.writes_read_models,
                *manifest.writes_control_plane,
                *manifest.side_effect_ledgers,
            )
        )
    }
    if missing_queue_health_owner:
        raise ValueError(f"queue health tables missing from worker ownership: {missing_queue_health_owner}")

    missing_current_identities = {
        manifest.name: sorted(
            set(manifest.writes_read_models)
            - {table_name for table_name, _identity_columns in manifest.current_read_model_identities}
        )
        for manifest in _WORKER_MANIFESTS
        if set(manifest.writes_read_models)
        - {table_name for table_name, _identity_columns in manifest.current_read_model_identities}
    }
    if missing_current_identities:
        raise ValueError(f"current read model tables missing stable identities: {missing_current_identities}")

    forbidden_current_identities = {
        manifest.name: {
            table_name: sorted(set(identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS)
            for table_name, identity_columns in manifest.current_read_model_identities
            if set(identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS
        }
        for manifest in _WORKER_MANIFESTS
        if any(
            set(identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS
            for _table_name, identity_columns in manifest.current_read_model_identities
        )
    }
    if forbidden_current_identities:
        raise ValueError(
            f"current read model identities include serving lifecycle columns: {forbidden_current_identities}"
        )


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


_validate_worker_manifests()


__all__ = [
    "WorkerKind",
    "WorkerLane",
    "WorkerManifest",
    "all_worker_manifests",
    "manifest_by_name",
    "manifest_names_for_factory",
    "manifests_by_lane",
    "require_worker_manifest",
    "worker_class_by_name",
    "worker_dirty_target_tables",
    "worker_names",
    "worker_queue_depth_tables",
    "worker_queue_health_tables",
    "worker_start_priority",
]
