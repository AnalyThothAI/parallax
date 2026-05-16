import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES
from gmgn_twitter_intel.platform.config.settings import WorkersSettings, default_workers_yaml


def _legacy_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


def test_default_workers_yaml_contains_canonical_worker_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert set(payload) - {"defaults"} == set(CANONICAL_WORKER_NAMES)
    assert _legacy_anchor_worker_key() not in payload
    assert settings.defaults.enabled is True
    assert settings.defaults.interval_seconds == 5
    assert settings.defaults.backoff.kind == "exponential"
    assert settings.collector.mode == "continuous"
    assert settings.collector.snapshot_timeout_seconds == 0.5
    assert settings.market_tick_stream.interval_seconds == 5
    assert settings.market_tick_stream.subscription_limit == 100
    assert settings.market_tick_poll.interval_seconds == 15
    assert settings.market_tick_poll.batch_size == 100
    assert settings.market_tick_poll.concurrency == 4
    assert settings.event_anchor_backfill.interval_seconds == 1
    assert settings.event_anchor_backfill.batch_size == 50
    assert settings.event_anchor_backfill.concurrency == 8
    assert settings.event_anchor_backfill.min_age_ms == 250
    assert settings.token_capture_tier.interval_seconds == 30
    assert settings.token_capture_tier.batch_size == 500
    assert settings.token_capture_tier.ws_limit == 100
    assert settings.token_capture_tier.poll_limit == 500
    assert settings.live_price_gateway.interval_seconds == 2
    assert not hasattr(settings.live_price_gateway, "subscription_limit")
    assert not hasattr(settings.live_price_gateway, "live_observation_heartbeat_seconds")
    assert settings.resolution_refresh.chain_ids == ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")
    assert settings.asset_profile_refresh.statement_timeout_seconds == 120
    assert settings.token_capture_tier.advisory_lock_key == 2026051503
    assert settings.token_radar_projection.advisory_lock_key == 2026051501
    assert settings.token_radar_projection.wakes_on == ("market_tick_written", "resolution_updated")
    assert settings.pulse_candidate.timeout_seconds == 0
    assert settings.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert settings.pulse_candidate.gate_thresholds.high_conviction_min == 78
    assert settings.handle_summary.time_threshold_ms == 1_800_000
    assert settings.notification_delivery.max_attempts == 5


def test_default_workers_yaml_hard_cuts_old_market_observation_runtime_keys():
    text = default_workers_yaml()
    payload = yaml.safe_load(text)
    legacy_channel = "_".join(("market", "observation", "written"))

    assert _legacy_anchor_worker_key() not in payload
    assert legacy_channel not in text
    assert "live_observation_" not in text
    assert "hot_target_ttl_seconds" not in text
    assert "cex_poll_interval_seconds" not in text


def test_worker_settings_reject_unknown_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["surprise_worker"] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_legacy_anchor_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload[_legacy_anchor_worker_key()] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_unknown_nested_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["collector"]["legacy_poll_interval_seconds"] = 1

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_legacy_live_gateway_fields():
    payload = yaml.safe_load(default_workers_yaml())
    payload["live_price_gateway"]["subscription_limit"] = 100

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)
