from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
    lane: WorkerLane
    start_priority: int
    wakes_on: tuple[str, ...] = ()
    queue_tables: tuple[str, ...] = ()
    current_read_model_identities: tuple[tuple[str, tuple[str, ...]], ...] = ()


_WORKER_MANIFESTS: tuple[WorkerManifest, ...] = (
    WorkerManifest(
        name="collector",
        lane=WorkerLane.INGEST,
        start_priority=10,
    ),
    WorkerManifest(
        name="token_capture_tier",
        lane=WorkerLane.PROJECTION,
        start_priority=20,
        queue_tables=("token_capture_tier_dirty_targets",),
        current_read_model_identities=(("token_capture_tier", ("target_type", "target_id")),),
    ),
    WorkerManifest(
        name="market_tick_stream",
        lane=WorkerLane.INGEST,
        start_priority=30,
    ),
    WorkerManifest(
        name="market_tick_poll",
        lane=WorkerLane.INGEST,
        start_priority=40,
    ),
    WorkerManifest(
        name="event_anchor_backfill",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        start_priority=45,
        queue_tables=("event_anchor_backfill_jobs",),
    ),
    WorkerManifest(
        name="live_price_gateway",
        lane=WorkerLane.MAINTENANCE_CACHE,
        start_priority=50,
    ),
    WorkerManifest(
        name="resolution_refresh",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        start_priority=60,
        queue_tables=("token_discovery_dirty_lookup_keys",),
    ),
    WorkerManifest(
        name="asset_profile_refresh",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        start_priority=70,
        queue_tables=("asset_profile_refresh_targets",),
    ),
    WorkerManifest(
        name="market_tick_current_projection",
        lane=WorkerLane.PROJECTION,
        start_priority=75,
        wakes_on=("market_tick_written",),
        queue_tables=("market_tick_current_dirty_targets",),
        current_read_model_identities=(("market_tick_current", ("target_type", "target_id")),),
    ),
    WorkerManifest(
        name="token_radar_projection",
        lane=WorkerLane.PROJECTION,
        start_priority=80,
        wakes_on=("market_tick_current_updated", "resolution_updated"),
        queue_tables=("token_radar_dirty_targets",),
        current_read_model_identities=(
            (
                "token_radar_rank_source_events",
                ("projection_version", "target_type_key", "identity_id", "source_kind", "source_id"),
            ),
            (
                "token_radar_target_features",
                ("projection_version", "window", "scope", "lane", "target_type_key", "identity_id"),
            ),
            (
                "token_radar_current_rows",
                ("projection_version", "window", "scope", "venue", "lane", "target_type_key", "identity_id"),
            ),
            (
                "token_radar_publication_state",
                ("projection_version", "window", "scope", "venue"),
            ),
            (
                "token_radar_target_first_seen",
                ("projection_version", "window", "scope", "venue", "target_type_key", "identity_id"),
            ),
        ),
    ),
    WorkerManifest(
        name="macro_sync",
        lane=WorkerLane.INGEST,
        start_priority=80,
    ),
    WorkerManifest(
        name="token_image_mirror",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        start_priority=82,
        queue_tables=("token_image_source_dirty_targets",),
    ),
    WorkerManifest(
        name="token_profile_current",
        lane=WorkerLane.PROJECTION,
        start_priority=85,
        queue_tables=("token_profile_current_dirty_targets",),
        current_read_model_identities=(("token_profile_current", ("target_type", "target_id")),),
    ),
    WorkerManifest(
        name="news_fetch",
        lane=WorkerLane.INGEST,
        start_priority=90,
    ),
    WorkerManifest(
        name="news_item_process",
        lane=WorkerLane.IDENTITY_MARKET_FACT,
        start_priority=91,
        wakes_on=("news_item_written",),
    ),
    WorkerManifest(
        name="news_story_brief",
        lane=WorkerLane.AGENT,
        start_priority=94,
        wakes_on=("news_item_processed",),
        queue_tables=("news_projection_dirty_targets",),
        current_read_model_identities=(("news_story_agent_briefs", ("story_brief_key",)),),
    ),
    WorkerManifest(
        name="news_page_projection",
        lane=WorkerLane.PROJECTION,
        start_priority=95,
        wakes_on=("news_item_written", "news_item_processed", "news_story_brief_updated", "news_page_dirty"),
        queue_tables=("news_projection_dirty_targets",),
        current_read_model_identities=(("news_page_rows", ("row_id",)),),
    ),
    WorkerManifest(
        name="macro_view_projection",
        lane=WorkerLane.PROJECTION,
        start_priority=95,
        wakes_on=("macro_observations_imported",),
        queue_tables=("macro_projection_dirty_targets",),
        current_read_model_identities=(
            ("macro_observation_series_rows", ("projection_version", "concept_key", "observed_at")),
            ("macro_observation_series_publication_state", ("projection_version",)),
            ("macro_view_snapshots", ("projection_version",)),
        ),
    ),
    WorkerManifest(
        name="notification_rule",
        lane=WorkerLane.NOTIFICATION,
        start_priority=120,
        current_read_model_identities=(("notifications", ("dedup_key",)),),
    ),
    WorkerManifest(
        name="notification_delivery",
        lane=WorkerLane.NOTIFICATION,
        start_priority=130,
        queue_tables=("notification_deliveries",),
    ),
)


def all_worker_manifests() -> tuple[WorkerManifest, ...]:
    return _WORKER_MANIFESTS


def manifest_by_name() -> dict[str, WorkerManifest]:
    return {manifest.name: manifest for manifest in _WORKER_MANIFESTS}


def require_worker_manifest(name: str) -> WorkerManifest:
    try:
        return manifest_by_name()[str(name)]
    except KeyError as exc:
        raise ValueError(f"unknown worker manifest: {name}") from exc


def manifests_by_lane() -> dict[WorkerLane, tuple[WorkerManifest, ...]]:
    return {lane: tuple(manifest for manifest in _WORKER_MANIFESTS if manifest.lane is lane) for lane in WorkerLane}


def worker_start_priority() -> dict[str, int]:
    return {manifest.name: manifest.start_priority for manifest in _WORKER_MANIFESTS}


def worker_queue_tables() -> dict[str, tuple[str, ...]]:
    return {manifest.name: manifest.queue_tables for manifest in _WORKER_MANIFESTS if manifest.queue_tables}


def worker_names() -> tuple[str, ...]:
    return tuple(manifest.name for manifest in _WORKER_MANIFESTS)
