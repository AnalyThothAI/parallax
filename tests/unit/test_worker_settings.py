import pytest
import yaml
from pydantic import ValidationError

from parallax.platform.config.settings import (
    WorkersSettings,
    default_workers_yaml,
)


def _manifest_worker_names() -> set[str]:
    from parallax.app.runtime.worker_manifest import all_worker_manifests

    return {manifest.name for manifest in all_worker_manifests()}


def test_default_workers_yaml_contains_canonical_worker_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert set(payload) == _manifest_worker_names()
    assert settings.collector.mode == "continuous"
    assert settings.collector.snapshot_timeout_seconds == 0.5
    assert settings.collector.backoff.model_dump() == {"base_ms": 1000, "max_ms": 60_000}
    assert settings.market_tick_stream.interval_seconds == 5
    assert settings.market_tick_stream.subscription_limit == 100
    assert settings.market_tick_poll.interval_seconds == 15
    assert settings.market_tick_poll.batch_size == 100
    assert settings.market_tick_poll.concurrency == 4
    assert settings.event_anchor_backfill.interval_seconds == 1
    assert settings.event_anchor_backfill.batch_size == 50
    assert settings.event_anchor_backfill.concurrency == 8
    assert settings.event_anchor_backfill.max_attempts == 3
    assert settings.event_anchor_backfill.lease_ms == 120_000
    assert settings.event_anchor_backfill.statement_timeout_seconds == 30
    assert settings.event_anchor_backfill.min_age_ms == 250
    assert settings.resolution_refresh.chain_ids == ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")
    assert settings.resolution_refresh.max_attempts == 3
    assert settings.resolution_refresh.lease_ms == 300_000
    assert settings.resolution_refresh.hot_not_found_retry_ms == 60_000
    assert settings.asset_profile_refresh.statement_timeout_seconds == 120
    assert settings.asset_profile_refresh.provider_retry_ms == 300_000
    assert settings.asset_profile_refresh.ready_refresh_ms == 21_600_000
    assert settings.asset_profile_refresh.missing_refresh_ms == 900_000
    assert settings.asset_profile_refresh.error_refresh_ms == 900_000
    assert settings.asset_profile_refresh.lease_ms == 120_000
    assert settings.token_image_mirror.interval_seconds == 60
    assert settings.token_image_mirror.source_limit == 5000
    assert settings.token_image_mirror.batch_size == 100
    assert settings.token_image_mirror.lease_ms == 120_000
    assert settings.token_image_mirror.max_attempts == 3
    assert settings.token_image_mirror.statement_timeout_seconds == 120
    assert settings.token_profile_current.interval_seconds == 60
    assert settings.token_profile_current.batch_size == 500
    assert settings.token_profile_current.lease_ms == 120_000
    assert settings.token_profile_current.max_attempts == 3
    assert settings.token_profile_current.statement_timeout_seconds == 30
    assert settings.token_radar_projection.batch_size == 100
    assert settings.token_radar_projection.lease_ms == 120_000
    assert settings.token_radar_projection.max_attempts == 3
    assert settings.token_radar_projection.retry_ms == 30_000
    assert settings.token_radar_projection.private_cache_retention_ms == 172_800_000
    assert settings.token_radar_projection.statement_timeout_seconds == 120
    assert settings.token_radar_projection.venues == ("all", "sol", "eth", "base", "bsc", "cex")
    assert settings.token_radar_projection.cold_interval_seconds == 60
    assert settings.macro_sync.enabled is True
    assert settings.macro_sync.interval_seconds == 900.0
    assert settings.macro_sync.batch_size == 3
    assert settings.macro_sync.bundle_names == (
        "macro-core",
        "macro-calendar-core",
        "treasury-auction-core",
        "fed-text-core",
        "crypto-derivatives-core",
    )
    assert settings.macro_sync.source_name == "macrodata-cli"
    assert settings.macro_sync.bootstrap_lookback_days == 1095
    assert settings.macro_sync.max_window_days == 31
    assert settings.macro_sync.steady_overlap_days == 7
    assert settings.macro_sync.max_bootstrap_windows_per_cycle == 1
    assert settings.macro_sync.lease_ms == 300_000
    assert settings.macro_sync.retry_delay_ms == 900_000
    assert settings.macro_sync.max_attempts == 8
    assert settings.macro_sync.macrodata_timeout_seconds == 240.0
    assert settings.macro_view_projection.lookback_days == 1095
    assert settings.macro_view_projection.limit_per_series == 800
    assert settings.macro_view_projection.lease_ms == 300_000
    assert settings.macro_view_projection.retry_ms == 300_000
    assert settings.daily_macro_judgment.enabled is False
    assert settings.daily_macro_judgment.interval_seconds == 300
    assert settings.daily_macro_judgment.settle_delay_seconds == 1_800
    assert settings.daily_macro_judgment.max_attempts == 3
    assert settings.daily_macro_judgment.analyst_model == "gpt-5.4-mini"
    assert settings.daily_macro_judgment.reviewer_model == "gpt-5.4-mini"
    assert settings.daily_macro_judgment.model_timeout_seconds == 480
    assert settings.notification_rule.batch_size == 50
    assert settings.notification_rule.statement_timeout_seconds == 30
    assert settings.notification_delivery.batch_size == 1
    assert settings.notification_delivery.max_attempts == 5
    assert settings.notification_delivery.statement_timeout_seconds == 30
    assert not hasattr(settings, "news_story_brief")
    assert not hasattr(settings, "agent_runtime")


def test_default_workers_yaml_round_trips_typed_defaults() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    expected = WorkersSettings()

    assert payload == expected.model_dump(mode="json")
    assert WorkersSettings.model_validate(payload) == expected


def test_worker_settings_schema_matches_manifest_worker_names() -> None:
    worker_fields = set(WorkersSettings.model_fields)

    assert worker_fields == _manifest_worker_names()


def test_worker_settings_reject_unknown_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["surprise_worker"] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_unknown_nested_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["collector"]["unexpected_field"] = 1

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_zero_asset_profile_refresh_policies():
    for field_name in ("provider_retry_ms", "ready_refresh_ms", "missing_refresh_ms", "error_refresh_ms"):
        payload = yaml.safe_load(default_workers_yaml())
        payload["asset_profile_refresh"][field_name] = 0

        with pytest.raises(ValidationError):
            WorkersSettings(**payload)


def test_worker_settings_reject_zero_notification_delivery_running_policies():
    payload = yaml.safe_load(default_workers_yaml())
    payload["notification_delivery"]["running_timeout_ms"] = 0

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)

    payload = yaml.safe_load(default_workers_yaml())
    payload["notification_delivery"]["stale_running_terminalization_batch_size"] = 0

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_news_workers_have_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert settings.news_fetch.interval_seconds == 60
    assert settings.news_fetch.batch_size == 5
    assert settings.news_fetch.lease_ms == 60_000
    assert settings.news_fetch.statement_timeout_seconds == 30
    assert settings.news_item_process.batch_size == 10
    assert settings.news_item_process.lease_ms == 120_000
    assert settings.news_item_process.max_attempts == 3
    assert settings.news_item_process.retry_delay_ms == 60_000
    assert settings.news_item_process.statement_timeout_seconds == 30
    assert settings.news_page_projection.batch_size == 100
    assert settings.news_page_projection.lease_ms == 120_000
    assert settings.news_page_projection.max_attempts == 3
    assert settings.news_page_projection.retry_ms == 30_000
    assert settings.news_page_projection.statement_timeout_seconds == 30
