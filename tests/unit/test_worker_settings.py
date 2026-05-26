import pytest
import yaml
from pydantic import ValidationError

from gmgn_twitter_intel.platform.agent_execution import AgentRuntimePolicy
from gmgn_twitter_intel.platform.config.settings import (
    NarrativeAdmissionWorkerSettings,
    PulseCandidateWorkerSettings,
    Settings,
    TokenDiscussionDigestWorkerSettings,
    WorkersSettings,
    default_workers_yaml,
)


def _manifest_worker_names() -> set[str]:
    from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests

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
    assert settings.agent_runtime.defaults.model == "qwen3.6"
    assert settings.agent_runtime.lanes["pulse.signal_analyst"].model == "qwen3.6"
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
    assert not hasattr(settings.live_price_gateway, "subscription_limit")
    assert not hasattr(settings.live_price_gateway, "live_observation_heartbeat_seconds")
    assert settings.resolution_refresh.chain_ids == ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton")
    assert settings.asset_profile_refresh.statement_timeout_seconds == 120
    assert settings.token_image_mirror.interval_seconds == 60
    assert settings.token_image_mirror.source_limit == 5000
    assert settings.token_image_mirror.batch_size == 100
    assert settings.token_image_mirror.statement_timeout_seconds == 120
    assert settings.token_image_mirror.advisory_lock_key == 2026052111
    assert settings.token_profile_current.interval_seconds == 60
    assert settings.token_profile_current.batch_size == 500
    assert settings.token_capture_tier.advisory_lock_key == 2026051503
    assert settings.token_radar_projection.advisory_lock_key == 2026051501
    assert settings.token_radar_projection.wakes_on == ("market_tick_current_updated", "resolution_updated")
    assert settings.narrative_admission.interval_seconds == 60
    assert settings.narrative_admission.soft_timeout_seconds == 180
    assert settings.narrative_admission.hard_timeout_seconds == 300
    assert settings.narrative_admission.advisory_lock_key == 2026051901
    assert settings.narrative_admission.wakes_on == ("token_radar_updated", "resolution_updated")
    assert settings.narrative_admission.windows == ("1h",)
    assert settings.narrative_admission.scopes == ("all",)
    assert settings.narrative_admission.hot_rank_limit == 50
    assert settings.narrative_admission.min_rank_score == 30
    assert settings.mention_semantics.interval_seconds == 60
    assert settings.mention_semantics.soft_timeout_seconds == 240
    assert settings.mention_semantics.hard_timeout_seconds == 300
    assert settings.mention_semantics.batch_size == 50
    assert settings.mention_semantics.provider_batch_size == 10
    assert settings.mention_semantics.max_semantic_rows_enqueued_per_cycle == 120
    assert settings.mention_semantics.max_semantic_rows_enqueued_per_admission == 20
    assert settings.mention_semantics.max_semantics_claimed_per_target_per_cycle == 3
    assert settings.mention_semantics.partial_enqueue_retry_seconds == 5
    assert not hasattr(settings.mention_semantics, "max_pending_source_age_seconds")
    assert settings.mention_semantics.advisory_lock_key == 2026051801
    assert settings.mention_semantics.wakes_on == ("token_radar_updated", "resolution_updated")
    assert settings.token_discussion_digest.interval_seconds == 120
    assert settings.token_discussion_digest.soft_timeout_seconds == 570
    assert settings.token_discussion_digest.hard_timeout_seconds == 660
    assert settings.token_discussion_digest.batch_size == 25
    assert settings.token_discussion_digest.advisory_lock_key == 2026051802
    assert settings.token_discussion_digest.wakes_on == (
        "token_radar_updated",
        "narrative_semantics_updated",
        "market_tick_written",
    )
    assert settings.token_discussion_digest.windows == ("1h",)
    assert settings.token_discussion_digest.scopes == ("all",)
    assert settings.token_discussion_digest.min_semantic_coverage == 0.35
    assert settings.token_discussion_digest.max_mentions_per_digest == 24
    assert settings.token_discussion_digest.max_llm_calls_per_cycle == 3
    assert settings.token_discussion_digest.max_llm_failures_per_cycle == 2
    assert settings.token_discussion_digest.provider_failure_backoff_seconds == 600
    assert settings.token_discussion_digest.digest_ttl_by_window_seconds == {"1h": 900}
    assert settings.token_discussion_digest.max_pending_semantic_rows_for_digest == 5
    assert settings.pulse_candidate.soft_timeout_seconds == 540
    assert settings.pulse_candidate.hard_timeout_seconds == 660
    assert settings.pulse_candidate.max_enqueues_per_cycle == 25
    assert settings.pulse_candidate.max_pending_jobs_global == 100
    assert settings.pulse_candidate.max_pending_jobs_per_window_scope == 25
    assert settings.pulse_candidate.windows == ("1h", "4h")
    assert settings.pulse_candidate.stale_job_ttl_by_window_seconds == {"1h": 3600, "4h": 14400}
    assert settings.pulse_candidate.trigger_thresholds.min_rank_score == 45
    assert settings.pulse_candidate.gate_thresholds.high_conviction_min == 78
    assert settings.handle_summary.time_threshold_ms == 1_800_000
    assert settings.handle_summary.interval_seconds == 30
    assert settings.handle_summary.statement_timeout_seconds == 10
    assert settings.handle_summary.reconcile_limit == 20
    assert settings.handle_summary.window_days == 3
    assert settings.macro_view_projection.lookback_days == 730
    assert settings.macro_view_projection.limit_per_series == 250
    assert settings.notification_delivery.max_attempts == 5


def test_worker_settings_schema_matches_manifest_worker_names() -> None:
    worker_fields = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert worker_fields == _manifest_worker_names()


def test_equity_event_intel_defaults_are_configured() -> None:
    settings = Settings(ws_token="secret")

    assert settings.equity_event_intel.enabled is False
    assert settings.equity_event_intel.default_universe == "nasdaq_tech"
    assert settings.workers.equity_event_fetch.interval_seconds == 60.0
    assert settings.workers.equity_event_page_projection.wakes_on == (
        "equity_event_document_written",
        "equity_event_processed",
        "equity_event_story_updated",
        "equity_event_brief_updated",
    )


def test_default_workers_yaml_contains_equity_event_workers_and_agent_lane() -> None:
    payload = yaml.safe_load(default_workers_yaml())

    assert "equity_event_fetch" in payload
    assert "equity_event_page_projection" in payload
    assert "equity_event.brief" in payload["agent_runtime"]["lanes"]


def test_equity_event_intel_settings_normalize_config_inputs() -> None:
    settings = Settings(
        ws_token="secret",
        equity_event_intel={
            "enabled": True,
            "default_universe": " nasdaq_tech ",
            "sec_user_agent": " gmgn-test contact@example.com ",
            "agent": {"lane": " equity_event.brief "},
            "companies": [
                {
                    "symbol": " aapl ",
                    "cik": " CIK0000320193 ",
                    "company_name": " Apple Inc. ",
                    "exchange": " nasdaq ",
                    "universe": " mega_cap ",
                }
            ],
            "expected_events": [
                {
                    "expected_event_id": " earnings:AAPL:2026Q2 ",
                    "symbol": " aapl ",
                    "event_type": " earnings_release ",
                    "source_id": " config:earnings ",
                    "expected_at_ms": 0,
                }
            ],
        },
    )

    company = settings.equity_event_intel.companies[0]
    expected_event = settings.equity_event_intel.expected_events[0]
    assert settings.equity_event_intel.default_universe == "nasdaq_tech"
    assert settings.equity_event_intel.sec_user_agent == "gmgn-test contact@example.com"
    assert settings.equity_event_intel.agent.lane == "equity_event.brief"
    assert company.symbol == "AAPL"
    assert company.cik == "0000320193"
    assert company.company_name == "Apple Inc."
    assert company.exchange == "nasdaq"
    assert company.universe == "mega_cap"
    assert expected_event.expected_event_id == "earnings:AAPL:2026Q2"
    assert expected_event.symbol == "AAPL"
    assert expected_event.event_type == "earnings_release"
    assert expected_event.source_id == "config:earnings"


@pytest.mark.parametrize(
    "payload",
    [
        {"companies": [{"symbol": "   "}]},
        {"companies": [{"symbol": "AAPL", "cik": "CIK-not-a-number"}]},
        {"companies": [{"symbol": "AAPL", "universe": "   "}]},
        {"expected_events": [{"expected_event_id": "", "symbol": "AAPL", "expected_at_ms": 1}]},
        {"expected_events": [{"expected_event_id": "e1", "symbol": " ", "expected_at_ms": 1}]},
        {"expected_events": [{"expected_event_id": "e1", "symbol": "AAPL", "expected_at_ms": -1}]},
        {"expected_events": [{"expected_event_id": "e1", "symbol": "AAPL", "event_type": "", "expected_at_ms": 1}]},
        {"expected_events": [{"expected_event_id": "e1", "symbol": "AAPL", "source_id": "", "expected_at_ms": 1}]},
        {"agent": {"lane": " "}},
    ],
)
def test_equity_event_intel_settings_reject_invalid_config_inputs(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(ws_token="secret", equity_event_intel=payload)


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

    with pytest.raises(ValidationError, match=r"must contain only|must be exactly"):
        TokenDiscussionDigestWorkerSettings(scopes=("all", "matched"))


def test_mention_semantics_hard_cuts_source_age_prune_setting() -> None:
    text = default_workers_yaml()
    settings = WorkersSettings(**yaml.safe_load(text))

    assert "max_pending_source_age_seconds" not in text
    assert not hasattr(settings.mention_semantics, "max_pending_source_age_seconds")
    assert settings.mention_semantics.max_semantic_rows_enqueued_per_cycle == 120
    assert settings.mention_semantics.max_semantic_rows_enqueued_per_admission == 20
    assert settings.mention_semantics.max_semantics_claimed_per_target_per_cycle == 3
    assert settings.mention_semantics.partial_enqueue_retry_seconds == 5


def test_token_discussion_digest_has_llm_cycle_caps() -> None:
    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert settings.token_discussion_digest.max_llm_calls_per_cycle == 3
    assert settings.token_discussion_digest.max_llm_failures_per_cycle == 2
    assert settings.token_discussion_digest.provider_failure_backoff_seconds == 600


def test_token_discussion_digest_hard_cuts_old_epoch_chasing_settings() -> None:
    text = default_workers_yaml()
    payload = yaml.safe_load(text)
    digest_payload = payload["token_discussion_digest"]

    assert "min_new_labeled_mentions" not in digest_payload
    assert "min_new_authors" not in digest_payload
    assert "5m" not in digest_payload["digest_ttl_by_window_seconds"]
    assert digest_payload["digest_ttl_by_window_seconds"] == {"1h": 900}

    invalid_payload = yaml.safe_load(text)
    invalid_payload["token_discussion_digest"]["min_new_labeled_mentions"] = 3
    invalid_payload["token_discussion_digest"]["min_new_authors"] = 2

    with pytest.raises(ValidationError):
        WorkersSettings(**invalid_payload)


def test_token_discussion_digest_rejects_obsolete_digest_ttl_window() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    payload["token_discussion_digest"]["digest_ttl_by_window_seconds"]["5m"] = 120

    with pytest.raises(ValidationError):
        WorkersSettings(**payload)


def test_narrative_runtime_defaults_are_1h_only() -> None:
    settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

    assert settings.token_radar_projection.windows == ("5m", "1h", "4h", "24h")
    assert settings.narrative_admission.windows == ("1h",)
    assert settings.token_discussion_digest.windows == ("1h",)
    assert settings.token_discussion_digest.digest_ttl_by_window_seconds == {"1h": 900}
    assert settings.token_discussion_digest.max_pending_semantic_rows_for_digest == 5


def test_narrative_runtime_rejects_non_1h_windows() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    payload["narrative_admission"]["windows"] = ["1h", "4h"]

    with pytest.raises(ValidationError, match=r"narrative_admission.windows"):
        WorkersSettings(**payload)

    payload = yaml.safe_load(default_workers_yaml())
    payload["token_discussion_digest"]["windows"] = ["24h"]

    with pytest.raises(ValidationError, match=r"token_discussion_digest.windows"):
        WorkersSettings(**payload)


def test_token_discussion_digest_rejects_non_1h_ttl_keys() -> None:
    payload = yaml.safe_load(default_workers_yaml())
    payload["token_discussion_digest"]["digest_ttl_by_window_seconds"] = {"1h": 900, "4h": 1800}

    with pytest.raises(ValidationError, match="digest_ttl_by_window_seconds"):
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
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    settings = WorkersSettings()

    assert settings.agent_runtime.global_max_concurrency == 4
    assert settings.agent_runtime.global_rpm_limit == 60
    assert settings.agent_runtime.defaults.model == "qwen3.6"
    assert settings.agent_runtime.defaults.disable_thinking is True
    assert settings.agent_runtime.defaults.include_usage is True
    assert settings.agent_runtime.lanes["pulse.signal_analyst"].priority == "high"
    assert settings.agent_runtime.lanes["pulse.bear_case"].timeout_seconds == 180
    assert settings.agent_runtime.lanes["pulse.risk_portfolio_judge"].timeout_seconds == 180
    assert settings.agent_runtime.lanes["narrative.discussion_digest"].timeout_seconds == 180
    assert settings.agent_runtime.lanes["narrative.mention_semantics"].priority == "bulk"
    assert settings.agent_runtime.lanes["watchlist.handle_summary"].priority == "low"
    assert settings.agent_runtime.lanes["news.item_brief"].priority == "low"
    assert settings.agent_runtime.lanes["news.item_brief"].max_concurrency == 1
    assert settings.agent_runtime.lanes["news.item_brief"].timeout_seconds == 180


def test_agent_runtime_settings_partial_lane_override_preserves_default_lanes() -> None:
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    settings = WorkersSettings(
        agent_runtime={
            "global_max_concurrency": 2,
            "global_rpm_limit": 30,
            "lanes": {
                "pulse.risk_portfolio_judge": {
                    "priority": "high",
                    "model": "gpt-judge",
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

    lane = settings.agent_runtime.lanes["pulse.risk_portfolio_judge"]
    assert settings.agent_runtime.global_max_concurrency == 2
    assert settings.agent_runtime.global_rpm_limit == 30
    assert lane.model == "gpt-judge"
    assert lane.timeout_seconds == 90
    assert lane.circuit_breaker.failure_threshold == 3
    assert settings.agent_runtime.lanes["pulse.pipeline"].timeout_seconds == 240
    assert settings.agent_runtime.lanes["pulse.pipeline"].model == "qwen3.6"
    assert settings.agent_runtime.lanes["narrative.mention_semantics"].priority == "bulk"
    assert settings.agent_runtime.lanes["watchlist.handle_summary"].priority == "low"
    assert settings.agent_runtime.lanes["news.item_brief"].timeout_seconds == 180


def test_agent_runtime_settings_accepts_news_item_brief_lane_override() -> None:
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

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
    assert settings.news_fetch.advisory_lock_key == 2026051905
    assert settings.news_item_process.advisory_lock_key == 2026051902
    assert settings.news_item_process.wakes_on == ("news_item_written",)
    assert settings.news_story_projection.advisory_lock_key == 2026051903
    assert settings.news_story_projection.wakes_on == ("news_item_processed",)
    assert settings.news_item_brief.interval_seconds == 10
    assert settings.news_item_brief.soft_timeout_seconds == 180
    assert settings.news_item_brief.hard_timeout_seconds == 240
    assert settings.news_item_brief.batch_size == 5
    assert settings.news_item_brief.advisory_lock_key == 2026052001
    assert settings.news_item_brief.backpressure_cooldown_ms == 60_000
    assert settings.news_item_brief.wakes_on == ("news_item_processed", "news_story_updated")
    assert settings.news_page_projection.advisory_lock_key == 2026051904
    assert settings.news_page_projection.wakes_on == (
        "news_item_written",
        "news_item_processed",
        "news_story_updated",
        "news_item_brief_updated",
        "news_page_dirty",
    )
    assert settings.news_source_quality_projection.interval_seconds == 60
    assert settings.news_source_quality_projection.batch_size == 100
    assert settings.news_source_quality_projection.advisory_lock_key == 2026052201
    assert settings.news_source_quality_projection.wakes_on == (
        "news_item_written",
        "news_item_processed",
        "news_story_updated",
        "news_item_brief_updated",
    )
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


def test_agent_runtime_default_model_uses_registered_capability_profile() -> None:
    settings = WorkersSettings(agent_runtime={"defaults": {"model": "deepseek-v4-flash"}})
    policy = AgentRuntimePolicy.model_validate(settings.agent_runtime.model_dump(mode="json"))

    profile = policy.capability_for_lane("pulse.signal_analyst")

    assert profile.provider_family == "openai_compatible"
    assert profile.request_options.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_agent_runtime_lane_accepts_capability_overrides() -> None:
    settings = WorkersSettings(
        agent_runtime={
            "lanes": {
                "news.item_brief": {
                    "provider_family": "deepseek",
                    "client_validation_retries": 2,
                }
            }
        }
    )

    lane = settings.agent_runtime.lanes["news.item_brief"]
    assert lane.provider_family == "deepseek"
    assert lane.client_validation_retries == 2


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
