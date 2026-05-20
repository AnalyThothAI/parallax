from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime import provider_wiring
from gmgn_twitter_intel.app.runtime.provider_wiring import openai
from gmgn_twitter_intel.app.runtime.provider_wiring.openai import build_agent_execution_gateway
from gmgn_twitter_intel.platform.config.settings import Settings


class FakeLLMGateway:
    trace_export_enabled = False


def test_build_agent_execution_gateway_uses_workers_agent_runtime_settings() -> None:
    settings = Settings(
        llm={
            "api_key": "sk-test",
            "model": "qwen3.6",
            "base_url": "https://example.com/v1",
            "instructor_safety_net_enabled": False,
        },
        workers={
            "agent_runtime": {
                "global_max_concurrency": 2,
                "global_rpm_limit": 30,
                "lanes": {
                    "pulse.decision_maker": {
                        "priority": "high",
                        "max_concurrency": 1,
                        "timeout_seconds": 90,
                    }
                },
            }
        },
    )

    gateway = build_agent_execution_gateway(settings, llm_gateway=FakeLLMGateway())

    snapshot = gateway.status_snapshot()
    assert snapshot["global_max_concurrency"] == 2
    assert snapshot["lanes"]["pulse.decision_maker"]["timeout_seconds"] == 90


def test_build_agent_execution_gateway_uses_news_item_brief_model_for_news_only_safety_net() -> None:
    settings = Settings(
        llm={
            "api_key": "sk-test",
            "news_item_brief_model": "gpt-news",
            "instructor_safety_net_enabled": True,
        },
    )

    gateway = build_agent_execution_gateway(settings, llm_gateway=FakeLLMGateway())

    assert gateway._safety_net is not None
    assert gateway._safety_net._model == "gpt-news"


def test_wire_providers_passes_one_agent_execution_gateway_to_openai_factories(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
            "model": "gpt-social",
            "pulse_agent_model": "gpt-pulse",
            "narrative_intel_model": "gpt-narrative",
            "watchlist_handle_summary_model": "gpt-watchlist",
            "news_item_brief_model": "gpt-news",
        },
        workers={
            "pulse_candidate": {"enabled": True},
            "mention_semantics": {"enabled": True},
            "token_discussion_digest": {"enabled": True},
            "handle_summary": {"enabled": True},
            "news_item_brief": {"enabled": True},
        },
    )
    agent_gateway = object()
    calls: list[tuple[str, str, object]] = []

    def fake_social(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("social", settings.llm_model or "", agent_gateway))
        return object()

    def fake_narrative(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("narrative", settings.narrative_intel_model or "", agent_gateway))
        return object()

    def fake_pulse(
        settings: Settings,
        *,
        agent_gateway: object,
        db_pool: object | None,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        assert db_pool is db_pool_token
        calls.append(("pulse", settings.pulse_agent_model or "", agent_gateway))
        return object()

    def fake_watchlist(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("watchlist", settings.watchlist_handle_summary_model or "", agent_gateway))
        return object()

    def fake_news_item_brief(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("news_item_brief", settings.news_item_brief_model or "", agent_gateway))
        return object()

    db_pool_token = object()
    monkeypatch.setattr(openai, "openai_social_event_provider", fake_social)
    monkeypatch.setattr(openai, "openai_narrative_intel_provider", fake_narrative)
    monkeypatch.setattr(openai, "openai_pulse_decision_provider", fake_pulse)
    monkeypatch.setattr(openai, "openai_watchlist_summary_provider", fake_watchlist)
    monkeypatch.setattr(openai, "openai_news_item_brief_provider", fake_news_item_brief)

    providers = provider_wiring.wire_providers(
        settings,
        start_collector=False,
        agent_execution_gateway=agent_gateway,
        db_pool=db_pool_token,
    )

    assert providers.agent_execution_gateway is agent_gateway
    assert calls == [
        ("social", "gpt-social", agent_gateway),
        ("narrative", "gpt-narrative", agent_gateway),
        ("news_item_brief", "gpt-news", agent_gateway),
        ("pulse", "gpt-pulse", agent_gateway),
        ("watchlist", "gpt-watchlist", agent_gateway),
    ]


def test_pulse_provider_uses_agent_runtime_pipeline_timeout() -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
            "model": "gpt-social",
            "pulse_agent_model": "gpt-pulse",
        },
        workers={
            "agent_runtime": {
                "lanes": {
                    "pulse.pipeline": {
                        "timeout_seconds": 305,
                    }
                },
            }
        },
    )

    provider = openai.openai_pulse_decision_provider(
        settings,
        agent_gateway=object(),
        db_pool=object(),
    )

    assert provider.timeout_seconds == 305
