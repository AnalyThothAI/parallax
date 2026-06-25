import pytest
import yaml
from pydantic import ValidationError

from parallax.platform.agent_execution import AgentRuntimePolicy
from parallax.platform.config.settings import (
    NarrativeAdmissionWorkerSettings,
    PulseCandidateWorkerSettings,
    Settings,
    WorkersSettings,
    default_config_yaml,
    default_workers_yaml,
)


def _manifest_worker_names() -> set[str]:
    from parallax.app.runtime.worker_manifest import all_worker_manifests

    return {manifest.name for manifest in all_worker_manifests()}


def _old_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


def test_default_workers_yaml_contains_canonical_worker_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert set(payload) - {"defaults", "agent_runtime"} == _manifest_worker_names()
    assert _old_anchor_worker_key() not in payload
    assert settings.defaults.enabled is True
    assert settings.defaults.interval_seconds == 5
    assert settings.defaults.soft_timeout_seconds == 120
    assert settings.defaults.hard_timeout_seconds == 180
    assert settings.defaults.backoff.kind == "exponential"
    assert settings.agent_runtime.defaults.model == "deepseek-v4-flash"
    assert settings.agent_runtime.lanes["pulse.decision"].model is None
    assert settings.collector.mode == "continuous"
    assert settings.collector.soft_timeout_seconds == 0
    assert settings.collector.hard_timeout_seconds == 0
    assert settings.collector.snapshot_timeout_seconds == 0.5
    assert settings.market_tick_stream.interval_seconds == 5
    assert settings.market_tick_stream.subscription_limit == 100
    assert settings.market_tick_poll.interval_seconds == 15
    assert settings.market_tick_poll.batch_size == 100
    assert settings.market_tick_poll.concurrency == 4
    assert settings.market_tick_current_projection.interval_seconds == 5
    assert settings.market_tick_current_projection.batch_size == 100
    assert settings.market_tick_current_projection.advisory_lock_key == 2026052401
    assert settings.market_tick_current_projection.wakes_on == ("market_tick_written",)
    assert settings.event_anchor_backfill.interval_seconds == 1
    assert settings.event_anchor_backfill.batch_size == 50
    assert settings.event_anchor_backfill.concurrency == 8
    assert settings.event_anchor_backfill.min_age_ms == 250
    assert settings.token_capture_tier.interval_seconds == 30
    assert settings.token_capture_tier.batch_size == 500
    assert settings.token_capture_tier.ws_limit == 100
    assert settings.token_capture_tier.poll_limit == 500
    assert settings.live_price_gateway.interval_seconds == 2
    assert settings.live_price_gateway.target_limit == 100
    assert settings.live_price_gateway.target_ttl_seconds == 300
    assert not hasattr(settings.live_price_gateway, "subscription_limit")
    assert not hasattr(settings.live_price_gateway, "live_observation_heartbeat_seconds")
    assert settings.resolution_refresh.chain_ids == ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")
    assert settings.resolution_refresh.lease_ms == 300_000
    assert settings.resolution_refresh.hot_not_found_retry_ms == 60_000
    assert settings.asset_profile_refresh.statement_timeout_seconds == 120
    assert settings.asset_profile_refresh.provider_retry_ms == 300_000
    assert settings.asset_profile_refresh.ready_refresh_ms == 21_600_000
    assert settings.asset_profile_refresh.missing_refresh_ms == 900_000
    assert settings.asset_profile_refresh.error_refresh_ms == 900_000
    assert settings.token_image_mirror.interval_seconds == 60
    assert settings.token_image_mirror.source_limit == 5000
    assert settings.token_image_mirror.batch_size == 100
    assert settings.token_image_mirror.max_attempts == 3
    assert settings.token_image_mirror.statement_timeout_seconds == 120
    assert settings.token_image_mirror.advisory_lock_key == 2026052111
    assert settings.token_profile_current.interval_seconds == 60
    assert settings.token_profile_current.batch_size == 500
    assert settings.token_capture_tier.advisory_lock_key == 2026051503
    assert settings.token_radar_projection.advisory_lock_key == 2026051501
    assert settings.token_radar_projection.wakes_on == ("market_tick_current_updated", "resolution_updated")
    assert settings.token_radar_projection.batch_size == 100
    assert settings.token_radar_projection.retry_ms == 30_000
    assert settings.token_radar_projection.private_cache_retention_enabled is True
    assert settings.token_radar_projection.private_cache_retention_ms == 172_800_000
    assert settings.token_radar_projection.statement_timeout_seconds == 120
    assert settings.token_radar_projection.venues == ("all", "sol", "eth", "base", "bsc", "cex")
    assert settings.token_radar_projection.cold_interval_seconds == 60
    assert settings.narrative_admission.interval_seconds == 60
    assert settings.narrative_admission.soft_timeout_seconds == 180
    assert settings.narrative_admission.hard_timeout_seconds == 300
    assert settings.narrative_admission.advisory_lock_key == 2026051901
    assert settings.narrative_admission.wakes_on == ("token_radar_updated", "resolution_updated")
    assert settings.narrative_admission.windows == ("1h",)
    assert settings.narrative_admission.scopes == ("all",)
    assert settings.narrative_admission.admission_limit == 200
    assert settings.narrative_admission.source_limit == 2000
    assert settings.narrative_admission.lease_ms == 60_000
    assert settings.narrative_admission.retry_ms == 60_000
    assert settings.narrative_admission.max_attempts == 3
    assert settings.narrative_admission.statement_timeout_seconds == 30
    assert settings.narrative_admission.hot_rank_limit == 50
    assert settings.narrative_admission.min_rank_score == 30
    assert "mention_semantics" not in payload
    assert "token_discussion_digest" not in payload
    assert not hasattr(settings, "mention_semantics")
    assert not hasattr(settings, "token_discussion_digest")
    assert settings.pulse_candidate.soft_timeout_seconds == 540
    assert settings.pulse_candidate.hard_timeout_seconds == 660
    assert settings.pulse_candidate.max_enqueues_per_cycle == 25
    assert settings.pulse_candidate.max_pending_jobs_global == 100
    assert settings.pulse_candidate.max_pending_jobs_per_window_scope == 25
    assert settings.pulse_candidate.trigger_lease_ms == 60_000
    assert settings.pulse_candidate.trigger_capacity_retry_ms == 30_000
    assert settings.pulse_candidate.trigger_error_retry_ms == 60_000
    assert settings.pulse_candidate.target_edge_budget_per_hour == 3
    assert settings.pulse_candidate.candidate_edge_budget_per_hour == 3
    assert settings.pulse_candidate.failure_circuit_per_hour == 3
    assert settings.pulse_candidate.failure_circuit_reasons == ("schema_validation_failed", "unknown_evidence_id")
    assert settings.pulse_candidate.timeline_debounce_seconds == 600
    assert settings.pulse_candidate.evidence_market_freshness_ms == 3_600_000
    assert settings.pulse_candidate.statement_timeout_seconds == 30
    assert settings.pulse_candidate.windows == ("1h", "4h")
    assert settings.pulse_candidate.stale_job_ttl_by_window_seconds == {"1h": 3600, "4h": 14400}
    assert settings.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert settings.pulse_candidate.gate_thresholds.high_conviction_min == 78
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
    assert settings.macro_view_projection.wakes_on == ("macro_observations_imported",)
    assert settings.macro_daily_brief_projection.wakes_on == ("macro_view_snapshot_updated",)
    assert settings.macro_daily_brief_projection.statement_timeout_seconds == 30
    assert settings.notification_rule.batch_size == 50
    assert settings.notification_rule.statement_timeout_seconds == 30
    assert settings.notification_delivery.batch_size == 1
    assert settings.notification_delivery.max_attempts == 5
    assert settings.notification_delivery.statement_timeout_seconds == 30
    assert settings.news_item_brief.enabled is False
    assert settings.news_item_brief.wakes_on == ()
    assert settings.news_story_brief.enabled is True
    assert settings.news_story_brief.wakes_on == ("news_item_processed",)


def test_worker_settings_schema_matches_manifest_worker_names() -> None:
    worker_fields = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert worker_fields == _manifest_worker_names()


def test_default_config_excludes_deleted_product_settings() -> None:
    config_payload = yaml.safe_load(default_config_yaml())
    workers_payload = yaml.safe_load(default_workers_yaml())
    settings = Settings(ws_token="secret")
    deleted_product_prefix = "_".join(("equity", "event"))

    assert f"{deleted_product_prefix}_intel" not in config_payload
    assert not hasattr(settings, f"{deleted_product_prefix}_intel")
    assert f"{deleted_product_prefix}.brief" not in workers_payload["agent_runtime"]["lanes"]
    assert all(not key.startswith(f"{deleted_product_prefix}_") for key in workers_payload)
    assert all(not field.startswith(f"{deleted_product_prefix}_") for field in WorkersSettings.model_fields)


def test_deleted_product_config_keys_are_rejected() -> None:
    deleted_product_prefix = "_".join(("equity", "event"))

    with pytest.raises(ValidationError):
        Settings(ws_token="secret", **{f"{deleted_product_prefix}_intel": {"enabled": False}})
    with pytest.raises(ValidationError):
        WorkersSettings(**{f"{deleted_product_prefix}_fetch": {"enabled": False}})


def test_default_workers_yaml_hard_cuts_old_market_observation_runtime_keys():
    text = default_workers_yaml()
    payload = yaml.safe_load(text)
    legacy_channel = "_".join(("market", "observation", "written"))

    assert _old_anchor_worker_key() not in payload
    assert legacy_channel not in text
    assert "live_observation_" not in text
    assert "hot_target_ttl_seconds" not in text
    assert "cex_poll_interval_seconds" not in text
    assert "investigator_max_tool_calls" not in text
    assert "fallback_agent_brief" not in text
    assert "narrative_fallback" not in text
    worker_payload = {key: value for key, value in payload.items() if key not in {"defaults", "agent_runtime"}}
    assert "timeout_seconds" not in payload["defaults"]
    assert all("timeout_seconds" not in value for value in worker_payload.values())


def test_narrative_realtime_workers_reject_matched_scope():
    with pytest.raises(ValidationError, match=r"must contain only|must be exactly"):
        NarrativeAdmissionWorkerSettings(scopes=("matched",))


def test_default_workers_yaml_hard_cuts_narrative_llm_workers() -> None:
    text = default_workers_yaml()
    payload = yaml.safe_load(text)

    assert "mention_semantics" not in text
    assert "token_discussion_digest" not in text
    assert "narrative.mention_semantics" not in text
    assert "narrative.discussion_digest" not in text
    assert "mention_semantics" not in payload
    assert "token_discussion_digest" not in payload


def test_narrative_runtime_defaults_are_1h_only() -> None:
    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert settings.token_radar_projection.windows == ("5m", "1h", "4h", "24h")
    assert settings.narrative_admission.windows == ("1h",)


def test_narrative_runtime_rejects_non_1h_windows() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    payload["narrative_admission"]["windows"] = ["1h", "4h"]

    with pytest.raises(ValidationError, match=r"narrative_admission.windows"):
        WorkersSettings(**payload)

    payload = yaml.safe_load(default_workers_yaml())
    payload["mention_semantics"] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_narrative_runtime_rejects_deleted_worker_keys() -> None:
    payload = yaml.safe_load(default_workers_yaml())

    payload["token_discussion_digest"] = {"enabled": True}
    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_unknown_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["surprise_worker"] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_old_anchor_worker_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload[_old_anchor_worker_key()] = {"enabled": True}

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_unknown_nested_key():
    payload = yaml.safe_load(default_workers_yaml())
    payload["collector"]["legacy_poll_interval_seconds"] = 1

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_agent_runtime_settings_default_lanes() -> None:
    from parallax.platform.config.settings import WorkersSettings

    settings = WorkersSettings()

    assert settings.agent_runtime.global_max_concurrency == 4
    assert settings.agent_runtime.global_rpm_limit == 60
    assert settings.agent_runtime.defaults.model == "deepseek-v4-flash"
    assert settings.agent_runtime.defaults.disable_thinking is True
    assert settings.agent_runtime.defaults.include_usage is True
    assert settings.agent_runtime.lanes["pulse.decision"].priority == "high"
    assert settings.agent_runtime.lanes["pulse.decision"].timeout_seconds == 240
    assert "narrative.discussion_digest" not in settings.agent_runtime.lanes
    assert "narrative.mention_semantics" not in settings.agent_runtime.lanes
    assert settings.agent_runtime.lanes["news.item_brief"].priority == "low"
    assert settings.agent_runtime.lanes["news.item_brief"].max_concurrency == 1
    assert settings.agent_runtime.lanes["news.item_brief"].timeout_seconds == 180
    assert settings.agent_runtime.lanes["news.story_brief"].priority == "low"
    assert settings.agent_runtime.lanes["news.story_brief"].max_concurrency == 1
    assert settings.agent_runtime.lanes["news.story_brief"].timeout_seconds == 180


def test_agent_runtime_settings_partial_lane_override_preserves_default_lanes() -> None:
    from parallax.platform.config.settings import WorkersSettings

    settings = WorkersSettings(
        agent_runtime={
            "global_max_concurrency": 2,
            "global_rpm_limit": 30,
            "lanes": {
                "pulse.decision": {
                    "priority": "high",
                    "model": "gpt-pulse",
                    "max_concurrency": 1,
                    "timeout_seconds": 90,
                    "circuit_breaker": {
                        "failure_threshold": 3,
                        "window_seconds": 120,
                        "open_seconds": 60,
                    },
                }
            },
        }
    )

    lane = settings.agent_runtime.lanes["pulse.decision"]
    assert settings.agent_runtime.global_max_concurrency == 2
    assert settings.agent_runtime.global_rpm_limit == 30
    assert lane.model == "gpt-pulse"
    assert lane.timeout_seconds == 90
    assert lane.circuit_breaker.failure_threshold == 3
    assert "narrative.mention_semantics" not in settings.agent_runtime.lanes
    assert settings.agent_runtime.lanes["news.item_brief"].timeout_seconds == 180
    assert settings.agent_runtime.lanes["news.story_brief"].timeout_seconds == 180


def test_agent_runtime_settings_accepts_news_item_brief_lane_override() -> None:
    from parallax.platform.config.settings import WorkersSettings

    settings = WorkersSettings(
        agent_runtime={
            "lanes": {
                "news.item_brief": {
                    "priority": "low",
                    "model": "gpt-news",
                    "max_concurrency": 1,
                    "timeout_seconds": 210,
                }
            }
        }
    )

    lane = settings.agent_runtime.lanes["news.item_brief"]
    assert lane.priority == "low"
    assert lane.model == "gpt-news"
    assert lane.max_concurrency == 1
    assert lane.timeout_seconds == 210


def test_agent_runtime_settings_accepts_news_story_brief_lane_override() -> None:
    from parallax.platform.config.settings import WorkersSettings

    settings = WorkersSettings(
        agent_runtime={
            "lanes": {
                "news.story_brief": {
                    "priority": "low",
                    "model": "gpt-story",
                    "max_concurrency": 1,
                    "timeout_seconds": 210,
                }
            }
        }
    )

    lane = settings.agent_runtime.lanes["news.story_brief"]
    assert lane.priority == "low"
    assert lane.model == "gpt-story"
    assert lane.max_concurrency == 1
    assert lane.timeout_seconds == 210


def test_agent_runtime_settings_reject_unknown_lane_key() -> None:
    with pytest.raises(ValidationError):
        WorkersSettings(
            agent_runtime={
                "lanes": {
                    "pulse.signal-analyst": {
                        "priority": "high",
                        "max_concurrency": 1,
                        "timeout_seconds": 90,
                    }
                }
            }
        )


def test_worker_settings_reject_zero_pulse_candidate_budgets():
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["max_enqueues_per_cycle"] = 0

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_zero_pulse_candidate_trigger_policies():
    for field_name in (
        "trigger_lease_ms",
        "trigger_capacity_retry_ms",
        "trigger_error_retry_ms",
        "target_edge_budget_per_hour",
        "candidate_edge_budget_per_hour",
        "failure_circuit_per_hour",
        "evidence_market_freshness_ms",
    ):
        payload = yaml.safe_load(default_workers_yaml())
        payload["pulse_candidate"][field_name] = 0

        with pytest.raises(ValidationError):
            WorkersSettings(**payload)


def test_worker_settings_reject_zero_asset_profile_refresh_policies():
    for field_name in ("provider_retry_ms", "ready_refresh_ms", "missing_refresh_ms", "error_refresh_ms"):
        payload = yaml.safe_load(default_workers_yaml())
        payload["asset_profile_refresh"][field_name] = 0

        with pytest.raises(ValidationError):
            WorkersSettings(**payload)


def test_worker_settings_reject_empty_pulse_failure_circuit_reasons():
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["failure_circuit_reasons"] = []

    with pytest.raises(ValidationError, match="failure_circuit_reasons"):
        WorkersSettings(**payload)


def test_worker_settings_reject_zero_pulse_job_running_timeout_ms():
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["job_running_timeout_ms"] = 0

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_worker_settings_reject_zero_pulse_stale_running_terminalization_batch_size():
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["stale_running_terminalization_batch_size"] = 0

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


def test_worker_settings_reject_zero_hard_timeout_for_non_continuous_workers() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    payload["pulse_candidate"]["hard_timeout_seconds"] = 0

    with pytest.raises(ValidationError, match="hard_timeout_seconds"):
        WorkersSettings(**payload)


def test_pulse_candidate_settings_reject_removed_windows() -> None:
    with pytest.raises(ValidationError, match=r"pulse_candidate\.windows"):
        PulseCandidateWorkerSettings(windows=("5m",))

    with pytest.raises(ValidationError, match=r"pulse_candidate\.windows"):
        PulseCandidateWorkerSettings(windows=("24h",))


def test_worker_settings_reject_legacy_live_gateway_fields():
    payload = yaml.safe_load(default_workers_yaml())
    payload["live_price_gateway"]["subscription_limit"] = 100

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_news_workers_have_defaults():
    payload = yaml.safe_load(default_workers_yaml())
    settings = WorkersSettings(**payload)

    assert settings.news_fetch.interval_seconds == 60
    assert settings.news_fetch.soft_timeout_seconds == 120
    assert settings.news_fetch.hard_timeout_seconds == 180
    assert settings.news_fetch.batch_size == 5
    assert settings.news_fetch.lease_ms == 60_000
    assert settings.news_fetch.statement_timeout_seconds == 30
    assert settings.news_fetch.advisory_lock_key == 2026051905
    assert settings.news_item_process.advisory_lock_key == 2026051902
    assert settings.news_item_process.batch_size == 10
    assert settings.news_item_process.lease_ms == 120_000
    assert settings.news_item_process.max_attempts == 3
    assert settings.news_item_process.retry_delay_ms == 60_000
    assert settings.news_item_process.statement_timeout_seconds == 30
    assert settings.news_item_process.wakes_on == ("news_item_written",)
    assert not hasattr(settings, "news_story_projection")
    assert settings.news_item_brief.interval_seconds == 10
    assert settings.news_item_brief.soft_timeout_seconds == 180
    assert settings.news_item_brief.hard_timeout_seconds == 240
    assert settings.news_item_brief.batch_size == 5
    assert settings.news_item_brief.lease_ms == 120_000
    assert settings.news_item_brief.retry_ms == 60_000
    assert settings.news_item_brief.statement_timeout_seconds == 30
    assert settings.news_item_brief.advisory_lock_key == 2026052001
    assert settings.news_item_brief.backpressure_cooldown_ms == 60_000
    assert settings.news_item_brief.wakes_on == ()
    assert settings.news_page_projection.batch_size == 100
    assert settings.news_page_projection.lease_ms == 120_000
    assert settings.news_page_projection.retry_ms == 30_000
    assert settings.news_page_projection.statement_timeout_seconds == 30
    assert settings.news_page_projection.advisory_lock_key == 2026051904
    assert settings.news_page_projection.wakes_on == (
        "news_item_written",
        "news_item_processed",
        "news_story_brief_updated",
        "news_page_dirty",
    )
    assert settings.news_source_quality_projection.interval_seconds == 60
    assert settings.news_source_quality_projection.batch_size == 100
    assert settings.news_source_quality_projection.lease_ms == 120_000
    assert settings.news_source_quality_projection.retry_ms == 30_000
    assert settings.news_source_quality_projection.statement_timeout_seconds == 30
    assert settings.news_source_quality_projection.advisory_lock_key == 2026052201
    assert settings.news_source_quality_projection.wakes_on == ("news_item_written",)
    assert settings.news_source_quality_projection.windows == ("24h", "7d")


def test_default_worker_advisory_lock_keys_are_unique():
    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))
    keys = {
        worker_name: getattr(worker_settings, "advisory_lock_key", None)
        for worker_name, worker_settings in settings
        if getattr(worker_settings, "advisory_lock_key", None) is not None
    }

    assert len(keys.values()) == len(set(keys.values()))


def test_agent_runtime_capability_fields_default_to_model_registry() -> None:
    settings = WorkersSettings()

    assert settings.agent_runtime.defaults.provider_family is None
    assert settings.agent_runtime.defaults.client_validation_retries is None
    assert settings.agent_runtime.defaults.max_tokens is None
    assert settings.agent_runtime.lanes["pulse.decision"].max_tokens is None
    assert settings.agent_runtime.lanes["news.item_brief"].max_tokens == 2200
    assert settings.agent_runtime.lanes["news.story_brief"].max_tokens == 2200


def test_agent_runtime_default_model_uses_registered_capability_profile() -> None:
    settings = WorkersSettings(agent_runtime={"defaults": {"model": "deepseek-v4-flash"}})
    policy = AgentRuntimePolicy.model_validate(settings.agent_runtime.model_dump(mode="json"))

    profile = policy.capability_for_lane("pulse.decision")

    assert profile.provider_family.value == "deepseek"
    assert profile.request_options.extra_body == {"thinking": {"type": "disabled"}}


def test_platform_agent_runtime_policy_default_matches_workers_settings_default() -> None:
    assert AgentRuntimePolicy().defaults.model == WorkersSettings().agent_runtime.defaults.model


def test_agent_runtime_lane_accepts_capability_overrides() -> None:
    settings = WorkersSettings(
        agent_runtime={
            "lanes": {
                "news.item_brief": {
                    "provider_family": "deepseek",
                    "client_validation_retries": 2,
                    "max_tokens": 1800,
                }
            }
        }
    )

    lane = settings.agent_runtime.lanes["news.item_brief"]
    assert lane.provider_family == "deepseek"
    assert lane.client_validation_retries == 2
    assert lane.max_tokens == 1800


def test_agent_runtime_rejects_legacy_output_strategy_field() -> None:
    with pytest.raises(ValidationError, match="output_strategy"):
        WorkersSettings(
            agent_runtime={
                "lanes": {
                    "news.item_brief": {
                        "output_strategy": "freeform_yaml",
                    }
                }
            }
        )
