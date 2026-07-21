from __future__ import annotations

from parallax.app.runtime import provider_wiring
from parallax.app.runtime.provider_wiring import model_execution
from parallax.app.runtime.provider_wiring.model_execution import build_agent_execution_gateway
from parallax.platform.config.settings import Settings


class FakeLLMGateway:
    api_key = "sk-test"
    base_url = "https://example.com/v1"
    trace_export_enabled = False


def test_build_agent_execution_gateway_uses_workers_agent_runtime_settings() -> None:
    settings = Settings(
        llm={"api_key": "sk-test", "base_url": "https://example.com/v1"},
        workers={
            "agent_runtime": {
                "defaults": {"model": "qwen3.6"},
                "global_max_concurrency": 2,
                "global_rpm_limit": 30,
                "lanes": {
                    "news.item_brief": {
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
    assert snapshot["lanes"]["news.item_brief"]["timeout_seconds"] == 90


def test_build_agent_execution_gateway_hard_cuts_safety_net() -> None:
    settings = Settings(
        llm={"api_key": "sk-test"},
        workers={"agent_runtime": {"defaults": {"model": "gpt-news"}}},
    )

    gateway = build_agent_execution_gateway(settings, llm_gateway=FakeLLMGateway())

    assert not hasattr(gateway, "_safety_net")


def test_wire_providers_passes_agent_execution_gateway_to_news_provider(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={"api_key": "sk-test"},
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-social"},
                "lanes": {
                    "news.item_brief": {"model": "gpt-news"},
                    "news.story_brief": {"model": "gpt-story"},
                },
            },
            "news_item_brief": {"enabled": True},
        },
    )
    agent_gateway = object()
    calls: list[object] = []

    def fake_news_item_brief(*, agent_gateway: object) -> object:
        calls.append(agent_gateway)
        return object()

    monkeypatch.setattr(model_execution, "litellm_news_item_brief_provider", fake_news_item_brief)

    providers = provider_wiring.wire_providers(
        settings,
        start_collector=False,
        agent_execution_gateway=agent_gateway,
    )

    assert providers.agent_execution_gateway is agent_gateway
    assert providers.news_intel.brief_provider is not None
    assert calls == [agent_gateway]
