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
    assert settings.token_profile_current.interval_seconds == 60
    assert settings.token_profile_current.batch_size == 500
    assert settings.token_capture_tier.advisory_lock_key == 2026051503
    assert settings.token_radar_projection.advisory_lock_key == 2026051501
    assert settings.token_radar_projection.wakes_on == ("market_tick_written", "resolution_updated")
    assert settings.narrative_admission.interval_seconds == 60
    assert settings.narrative_admission.advisory_lock_key == 2026051901
    assert settings.narrative_admission.wakes_on == ("token_radar_updated", "resolution_updated")
    assert settings.narrative_admission.windows == ("5m", "1h", "4h", "24h")
    assert settings.narrative_admission.scopes == ("all", "matched")
    assert settings.narrative_admission.hot_rank_limit == 50
    assert settings.narrative_admission.min_rank_score == 30
    assert settings.mention_semantics.interval_seconds == 60
    assert settings.mention_semantics.timeout_seconds == 0
    assert settings.mention_semantics.batch_size == 50
    assert settings.mention_semantics.provider_batch_size == 10
    assert settings.mention_semantics.max_semantic_rows_enqueued_per_cycle == 40
    assert settings.mention_semantics.max_pending_semantics_per_target == 80
    assert settings.mention_semantics.max_pending_source_age_seconds == 43_200
    assert settings.mention_semantics.advisory_lock_key == 2026051801
    assert settings.mention_semantics.wakes_on == ("token_radar_updated", "resolution_updated")
    assert settings.token_discussion_digest.interval_seconds == 120
    assert settings.token_discussion_digest.timeout_seconds == 0
    assert settings.token_discussion_digest.batch_size == 25
    assert settings.token_discussion_digest.advisory_lock_key == 2026051802
    assert settings.token_discussion_digest.wakes_on == (
        "token_radar_updated",
        "narrative_semantics_updated",
        "market_tick_written",
    )
    assert settings.token_discussion_digest.windows == ("5m", "1h", "4h", "24h")
    assert settings.token_discussion_digest.scopes == ("all", "matched")
    assert settings.token_discussion_digest.min_semantic_coverage == 0.35
    assert settings.token_discussion_digest.digest_ttl_by_window_seconds["24h"] == 900
    assert settings.pulse_candidate.timeout_seconds == 0
    assert settings.pulse_candidate.max_enqueues_per_cycle == 25
    assert settings.pulse_candidate.max_pending_jobs_global == 100
    assert settings.pulse_candidate.max_pending_jobs_per_window_scope == 25
    assert settings.pulse_candidate.stale_job_ttl_by_window_seconds == {"5m": 300}
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
    assert "investigator_max_tool_calls" not in text
    assert "fallback_agent_brief" not in text
    assert "narrative_fallback" not in text


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


def test_worker_settings_reject_zero_pulse_candidate_budgets():
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["max_enqueues_per_cycle"] = 0

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_legacy_live_gateway_fields():
    payload = yaml.safe_load(default_workers_yaml())
    payload["live_price_gateway"]["subscription_limit"] = 100

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_news_workers_have_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert settings.news_fetch.interval_seconds == 60
    assert settings.news_fetch.timeout_seconds == 120
    assert settings.news_fetch.batch_size == 5
    assert settings.news_fetch.advisory_lock_key == 2026051905
    assert settings.news_item_process.advisory_lock_key == 2026051902
    assert settings.news_item_process.wakes_on == ("news_item_written",)
    assert settings.news_story_projection.advisory_lock_key == 2026051903
    assert settings.news_story_projection.wakes_on == ("news_item_processed",)
    assert settings.news_page_projection.advisory_lock_key == 2026051904
    assert settings.news_page_projection.wakes_on == (
        "news_item_written",
        "news_item_processed",
        "news_story_updated",
    )


def test_default_worker_advisory_lock_keys_are_unique():
    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))
    keys = {
        worker_name: getattr(worker_settings, "advisory_lock_key", None)
        for worker_name, worker_settings in settings
        if getattr(worker_settings, "advisory_lock_key", None) is not None
    }

    assert len(keys.values()) == len(set(keys.values()))
