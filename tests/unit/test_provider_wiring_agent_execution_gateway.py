from __future__ import annotations

from parallax.app.runtime import provider_wiring
from parallax.app.runtime.provider_wiring import model_execution
from parallax.app.runtime.provider_wiring.model_execution import build_agent_execution_gateway
from parallax.platform.config.settings import Settings


def test_build_agent_execution_gateway_uses_workers_agent_runtime_settings() -> None:
    settings = Settings(
        llm={"api_key": "sk-test", "base_url": "https://example.com/v1"},
        workers={
            "agent_runtime": {
                "model": "qwen3.6",
                "max_concurrency": 2,
                "rpm_limit": 30,
                "timeout_seconds": 90,
            }
        },
    )

    gateway = build_agent_execution_gateway(settings)

    snapshot = gateway.status_snapshot()
    assert snapshot["lane"] == "news.story_brief"
    assert snapshot["model"] == "qwen3.6"
    assert snapshot["max_concurrency"] == 2
    assert snapshot["rpm_limit"] == 30
    assert snapshot["timeout_seconds"] == 90


def test_build_agent_execution_gateway_hard_cuts_safety_net() -> None:
    settings = Settings(
        llm={"api_key": "sk-test"},
        workers={"agent_runtime": {"model": "gpt-news"}},
    )

    gateway = build_agent_execution_gateway(settings)

    assert not hasattr(gateway, "_safety_net")


def test_wire_providers_passes_agent_execution_gateway_to_news_provider(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={"api_key": "sk-test"},
        workers={
            "agent_runtime": {"model": "gpt-story"},
            "news_story_brief": {"enabled": True},
        },
    )
    agent_gateway = object()
    calls: list[object] = []

    def fake_news_story_brief(*, agent_gateway: object) -> object:
        calls.append(agent_gateway)
        return object()

    monkeypatch.setattr(model_execution, "litellm_news_story_brief_provider", fake_news_story_brief)

    providers = provider_wiring.wire_providers(
        settings,
        start_collector=False,
        agent_execution_gateway=agent_gateway,
    )

    assert not hasattr(providers, "agent_execution_gateway")
    assert providers.news_intel.story_brief_provider is not None
    assert calls == [agent_gateway]
