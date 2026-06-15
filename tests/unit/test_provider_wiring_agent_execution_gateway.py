from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime import provider_wiring
from parallax.app.runtime.provider_wiring import model_execution
from parallax.app.runtime.provider_wiring.model_execution import build_agent_execution_gateway
from parallax.platform.config.settings import Settings


class FakeLLMGateway:
    trace_export_enabled = False


class FakePulseClient:
    provider = "litellm"
    model = "gpt-pulse"
    artifact_version_hash = "artifact-hash"
    runtime_contract = object()

    def __init__(self) -> None:
        self.pipeline_kwargs: dict[str, Any] | None = None

    def try_reserve_execution(self, lane, *, child_lanes=(), rate_units=1, scope="execution"):
        raise AssertionError("not used")

    def model_for_lane(self, lane):
        return f"model:{lane}"

    def request_audit(self, **kwargs):
        return {"input_hash": "hash-input"}

    async def run_decision_pipeline(self, **kwargs):
        self.pipeline_kwargs = kwargs
        return SimpleNamespace(
            final_decision={"recommendation": "watchlist"},
            agent_run_audit={"output_hash": "hash-1"},
            stage_audits=("pulse_decision",),
        )

    async def aclose(self):
        return None


def test_build_agent_execution_gateway_uses_workers_agent_runtime_settings() -> None:
    settings = Settings(
        llm={
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "qwen3.6"},
                "global_max_concurrency": 2,
                "global_rpm_limit": 30,
                "lanes": {
                    "pulse.decision": {
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
    assert snapshot["lanes"]["pulse.decision"]["timeout_seconds"] == 90


def test_build_agent_execution_gateway_hard_cuts_safety_net() -> None:
    settings = Settings(
        llm={
            "api_key": "sk-test",
        },
        workers={"agent_runtime": {"defaults": {"model": "gpt-news"}}},
    )

    gateway = build_agent_execution_gateway(settings, llm_gateway=FakeLLMGateway())

    assert not hasattr(gateway, "_safety_net")


def test_wire_providers_passes_one_agent_execution_gateway_to_model_execution_factories(monkeypatch) -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-social"},
                "lanes": {
                    "pulse.decision": {"model": "gpt-pulse"},
                    "news.item_brief": {"model": "gpt-news"},
                },
            },
            "pulse_candidate": {"enabled": True},
            "news_item_brief": {"enabled": True},
        },
    )
    agent_gateway = object()
    calls: list[tuple[str, str, object]] = []

    def fake_pulse(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("pulse", settings.agent_runtime_model_for_lane("pulse.decision"), agent_gateway))
        return object()

    def fake_news_item_brief(
        settings: Settings,
        *,
        agent_gateway: object,
        **kwargs: Any,
    ) -> object:
        assert "llm_gateway" not in kwargs
        calls.append(("news_item_brief", settings.agent_runtime_model_for_lane("news.item_brief"), agent_gateway))
        return object()

    db_pool_token = object()
    monkeypatch.setattr(model_execution, "litellm_pulse_decision_provider", fake_pulse)
    monkeypatch.setattr(model_execution, "litellm_news_item_brief_provider", fake_news_item_brief)

    providers = provider_wiring.wire_providers(
        settings,
        start_collector=False,
        agent_execution_gateway=agent_gateway,
        db_pool=db_pool_token,
    )

    assert providers.agent_execution_gateway is agent_gateway
    assert calls == [
        ("news_item_brief", "gpt-news", agent_gateway),
        ("pulse", "gpt-pulse", agent_gateway),
    ]


def test_pulse_provider_uses_agent_runtime_decision_timeout() -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-social"},
                "lanes": {
                    "pulse.decision": {
                        "timeout_seconds": 305,
                    }
                },
            }
        },
    )

    provider = model_execution.litellm_pulse_decision_provider(
        settings,
        agent_gateway=object(),
    )

    assert provider.timeout_seconds == 305


def test_pulse_provider_timeout_requires_agent_runtime_lanes_contract() -> None:
    malformed_settings = SimpleNamespace(workers=SimpleNamespace(agent_runtime=SimpleNamespace()))

    with pytest.raises(AttributeError, match="lanes"):
        model_execution._agent_runtime_lane_timeout_seconds(malformed_settings, "pulse.decision")


def test_pulse_provider_timeout_requires_configured_pulse_decision_lane() -> None:
    malformed_settings = SimpleNamespace(
        workers=SimpleNamespace(
            agent_runtime=SimpleNamespace(lanes={}),
        ),
    )

    with pytest.raises(KeyError, match=r"pulse\.decision"):
        model_execution._agent_runtime_lane_timeout_seconds(malformed_settings, "pulse.decision")


def test_pulse_provider_maps_agent_run_audit_from_litellm_client() -> None:
    client = FakePulseClient()
    provider = model_execution.LiteLLMPulseDecisionProvider(client, pipeline_timeout_seconds=305)

    result = asyncio.run(
        provider.run_decision_pipeline(
            context={},
            run_id="run-1",
            job={},
            route="meme",
            completeness={},
            runtime_manifest={},
        )
    )

    assert client.pipeline_kwargs is not None
    assert "stage_plan" not in client.pipeline_kwargs
    assert result.agent_run_audit == {"output_hash": "hash-1"}
    assert result.final_decision == {"recommendation": "watchlist"}
    assert result.stage_audits == ("pulse_decision",)
