import pytest
import yaml
from pydantic import ValidationError

from parallax.platform.agent_execution import AgentRuntimePolicy
from parallax.platform.config.settings import (
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

    assert set(payload) - {"agent_runtime"} == _manifest_worker_names()
    assert _old_anchor_worker_key() not in payload
    assert settings.agent_runtime.model == "deepseek-v4-flash"
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
    assert settings.token_profile_current.interval_seconds == 60
    assert settings.token_profile_current.batch_size == 500
    assert settings.token_radar_projection.batch_size == 100
    assert settings.token_radar_projection.retry_ms == 30_000
    assert settings.token_radar_projection.private_cache_retention_ms == 172_800_000
    assert settings.token_radar_projection.statement_timeout_seconds == 120
    assert settings.token_radar_projection.venues == ("all", "sol", "eth", "base", "bsc", "cex")
    assert settings.token_radar_projection.cold_interval_seconds == 60
    assert "narrative_admission" not in payload
    assert not hasattr(settings, "narrative_admission")
    assert "mention_semantics" not in payload
    assert "token_discussion_digest" not in payload
    assert not hasattr(settings, "mention_semantics")
    assert not hasattr(settings, "token_discussion_digest")
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
    assert settings.notification_rule.batch_size == 50
    assert settings.notification_rule.statement_timeout_seconds == 30
    assert settings.notification_delivery.batch_size == 1
    assert settings.notification_delivery.max_attempts == 5
    assert settings.notification_delivery.statement_timeout_seconds == 30
    assert settings.news_story_brief.enabled is True


def test_default_workers_yaml_round_trips_typed_defaults() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    expected = WorkersSettings()

    assert payload == expected.model_dump(mode="json")
    assert WorkersSettings.model_validate(payload) == expected


def test_worker_settings_schema_matches_manifest_worker_names() -> None:
    worker_fields = set(WorkersSettings.model_fields) - {"agent_runtime"}

    assert worker_fields == _manifest_worker_names()


@pytest.mark.parametrize("field", ["wakes_on", "hard_timeout_seconds", "advisory_lock_key"])
def test_deleted_worker_lifecycle_control_keys_are_rejected(field: str) -> None:
    payload = yaml.safe_load(default_workers_yaml())

    assert all(field not in worker_config for worker_config in payload.values() if isinstance(worker_config, dict))
    payload["news_item_process"][field] = "legacy"

    with pytest.raises(ValidationError, match=field):
        WorkersSettings(**payload)


def test_default_config_excludes_deleted_product_settings() -> None:
    config_payload = yaml.safe_load(default_config_yaml())
    workers_payload = yaml.safe_load(default_workers_yaml())
    settings = Settings(ws_token="secret")
    deleted_product_prefix = "_".join(("equity", "event"))

    assert f"{deleted_product_prefix}_intel" not in config_payload
    assert not hasattr(settings, f"{deleted_product_prefix}_intel")
    assert deleted_product_prefix not in str(workers_payload["agent_runtime"])
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
    worker_payload = {key: value for key, value in payload.items() if key != "agent_runtime"}
    assert all("timeout_seconds" not in value for value in worker_payload.values())


def test_default_workers_yaml_hard_cuts_narrative_workers() -> None:
    text = default_workers_yaml()
    payload = yaml.safe_load(text)

    assert "mention_semantics" not in text
    assert "token_discussion_digest" not in text
    assert "narrative_admission" not in text
    assert "narrative.mention_semantics" not in text
    assert "narrative.discussion_digest" not in text
    assert "mention_semantics" not in payload
    assert "token_discussion_digest" not in payload
    assert "narrative_admission" not in payload


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


def test_agent_runtime_settings_have_one_flat_policy() -> None:
    settings = WorkersSettings()

    assert settings.agent_runtime.model == "deepseek-v4-flash"
    assert settings.agent_runtime.provider_family is None
    assert settings.agent_runtime.max_tokens == 2200
    assert settings.agent_runtime.max_concurrency == 1
    assert settings.agent_runtime.rpm_limit == 60
    assert settings.agent_runtime.timeout_seconds == 180
    assert settings.agent_runtime.circuit_breaker.failure_threshold == 5
    assert settings.agent_runtime.circuit_breaker.window_seconds == 300
    assert settings.agent_runtime.circuit_breaker.open_seconds == 120


def test_agent_runtime_settings_accept_flat_override() -> None:
    settings = WorkersSettings(
        agent_runtime={
            "model": "gpt-news",
            "provider_family": "litellm",
            "max_tokens": 1800,
            "max_concurrency": 2,
            "rpm_limit": 30,
            "timeout_seconds": 90,
            "circuit_breaker": {
                "failure_threshold": 3,
                "window_seconds": 120,
                "open_seconds": 60,
            },
        }
    )

    assert settings.agent_runtime.model == "gpt-news"
    assert settings.agent_runtime.provider_family.value == "litellm"
    assert settings.agent_runtime.max_tokens == 1800
    assert settings.agent_runtime.max_concurrency == 2
    assert settings.agent_runtime.rpm_limit == 30
    assert settings.agent_runtime.timeout_seconds == 90
    assert settings.agent_runtime.circuit_breaker.failure_threshold == 3


@pytest.mark.parametrize(
    "legacy_field, legacy_value",
    [
        ("defaults", {"model": "gpt-base"}),
        ("lanes", {"news.story_brief": {"model": "gpt-story"}}),
        ("global_max_concurrency", 2),
        ("global_rpm_limit", 30),
        ("client_validation_retries", 2),
        ("priority", "high"),
        ("disable_thinking", True),
        ("include_usage", True),
    ],
)
def test_agent_runtime_settings_reject_removed_policy_layers(
    legacy_field: str,
    legacy_value: object,
) -> None:
    with pytest.raises(ValidationError, match=legacy_field):
        WorkersSettings(agent_runtime={legacy_field: legacy_value})


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


@pytest.mark.parametrize(
    "worker_name",
    ["market_tick_current_projection", "token_capture_tier", "live_price_gateway"],
)
def test_worker_settings_reject_retired_market_control_workers(worker_name: str) -> None:
    with pytest.raises(ValidationError, match=worker_name):
        WorkersSettings(**{worker_name: {"enabled": True}})


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
    assert not hasattr(settings, "news_story_projection")
    assert settings.news_story_brief.interval_seconds == 10
    assert settings.news_story_brief.batch_size == 5
    assert settings.news_story_brief.lease_ms == 120_000
    assert settings.news_story_brief.retry_ms == 60_000
    assert settings.news_story_brief.statement_timeout_seconds == 30
    assert settings.news_story_brief.backpressure_cooldown_ms == 60_000
    assert settings.news_page_projection.batch_size == 100
    assert settings.news_page_projection.lease_ms == 120_000
    assert settings.news_page_projection.retry_ms == 30_000
    assert settings.news_page_projection.statement_timeout_seconds == 30


def test_agent_runtime_capability_fields_default_to_model_registry() -> None:
    settings = WorkersSettings()

    assert settings.agent_runtime.provider_family is None
    assert settings.agent_runtime.max_tokens == 2200


def test_agent_runtime_default_model_uses_registered_capability_profile() -> None:
    settings = WorkersSettings(agent_runtime={"model": "deepseek-v4-flash"})
    profile = settings.agent_runtime.capability_profile()

    assert profile.provider_family.value == "deepseek"
    assert profile.request_options.extra_body == {"thinking": {"type": "disabled"}}


def test_platform_agent_runtime_policy_default_matches_workers_settings_default() -> None:
    assert AgentRuntimePolicy() == WorkersSettings().agent_runtime


def test_agent_runtime_accepts_capability_overrides() -> None:
    settings = WorkersSettings(
        agent_runtime={
            "provider_family": "deepseek",
            "max_tokens": 1800,
        }
    )

    assert settings.agent_runtime.provider_family.value == "deepseek"
    assert settings.agent_runtime.max_tokens == 1800


def test_agent_runtime_rejects_legacy_output_strategy_field() -> None:
    with pytest.raises(ValidationError, match="output_strategy"):
        WorkersSettings(
            agent_runtime={
                "output_strategy": "freeform_yaml",
            }
        )
