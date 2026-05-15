import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.platform.config.settings import WorkersSettings, default_workers_yaml


def test_default_workers_yaml_contains_canonical_worker_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert settings.defaults.enabled is True
    assert settings.defaults.interval_seconds == 5
    assert settings.defaults.backoff.kind == "exponential"
    assert settings.collector.mode == "continuous"
    assert settings.collector.snapshot_timeout_seconds == 0.5
    assert settings.anchor_price.statement_timeout_seconds == 120
    assert settings.live_price_gateway.subscription_limit == 100
    assert settings.resolution_refresh.chain_ids == ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")
    assert settings.asset_profile_refresh.statement_timeout_seconds == 120
    assert settings.token_capture_tier.advisory_lock_key == 2026051503
    assert settings.token_radar_projection.advisory_lock_key == 2026051501
    assert settings.pulse_candidate.timeout_seconds == 0
    assert settings.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert settings.pulse_candidate.gate_thresholds.high_conviction_min == 78
    assert settings.handle_summary.time_threshold_ms == 1_800_000
    assert settings.notification_delivery.max_attempts == 5


def test_worker_settings_reject_unknown_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["surprise_worker"] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_unknown_nested_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["collector"]["legacy_poll_interval_seconds"] = 1

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)
