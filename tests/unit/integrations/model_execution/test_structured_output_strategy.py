from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from gmgn_twitter_intel.integrations.model_execution.structured_json_strategy import (
    ChatJsonObjectStrategy,
    StructuredOutputContext,
)
from gmgn_twitter_intel.platform.agent_capabilities import (
    AgentCapabilityProfile,
    AgentProviderFamily,
    resolve_agent_capability_profile,
)
from gmgn_twitter_intel.platform.agent_execution import AgentStageSpec


class Payload(BaseModel):
    value: str


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]
        self.usage = {"prompt_tokens": 8, "completion_tokens": 4}


class FakeCompletions:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses or ['{"value":"ok"}'])

    async def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        content = self._responses.pop(0) if self._responses else '{"value":"ok"}'
        return FakeResponse(content)


@pytest.fixture
def fake_litellm(monkeypatch: pytest.MonkeyPatch):
    completions = FakeCompletions()
    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.model_execution.structured_json_strategy.litellm.acompletion",
        completions.create,
    )
    return completions


def test_json_object_strategy_uses_official_response_format_and_client_validation(
    fake_litellm: FakeCompletions,
) -> None:
    async def scenario() -> None:
        strategy = ChatJsonObjectStrategy(api_key="sk-test", base_url="https://example.com/v1")

        outcome = await strategy.run(_context())

        call = fake_litellm.calls[0]
        assert call["model"] == "openai/deepseek-v4-flash"
        assert call["response_format"] == {"type": "json_object"}
        assert call["api_key"] == "sk-test"
        assert call["base_url"] == "https://example.com/v1"
        assert call["timeout"] == 30.0
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}
        assert "tools" not in call
        assert "tool_choice" not in call
        assert "json object" in call["messages"][0]["content"].lower()
        assert '"value"' in call["messages"][0]["content"]
        assert outcome.final_output == Payload(value="ok")
        assert outcome.audit_extra["parse_mode"] == "json_object_client_validate"
        assert outcome.audit_extra["schema_enforcement"] == "client_validate"
        assert outcome.audit_extra["safety_net_used"] is False

    asyncio.run(scenario())


def test_json_object_strategy_reasks_within_same_strategy_after_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        completions = FakeCompletions(responses=["{}", '{"value":"fixed"}'])
        monkeypatch.setattr(
            "gmgn_twitter_intel.integrations.model_execution.structured_json_strategy.litellm.acompletion",
            completions.create,
        )
        strategy = ChatJsonObjectStrategy(api_key="sk-test", base_url="https://example.com/v1")

        outcome = await strategy.run(
            _context(
                capability_profile=AgentCapabilityProfile(
                    provider_family=AgentProviderFamily.DEEPSEEK,
                    client_validation_retries=1,
                )
            )
        )

        assert outcome.final_output == Payload(value="fixed")
        assert len(completions.calls) == 2
        assert outcome.audit_extra["safety_net_used"] is True
        assert outcome.audit_extra["safety_net_retries"] == 1
        assert "failed application validation" in completions.calls[1]["messages"][-1]["content"]

    asyncio.run(scenario())


def _context(
    *,
    capability_profile: AgentCapabilityProfile | None = None,
    model_name: str = "deepseek-v4-flash",
) -> StructuredOutputContext:
    profile = capability_profile or resolve_agent_capability_profile(model="deepseek-v4-flash")
    return StructuredOutputContext(
        stage=AgentStageSpec(
            lane="pulse.signal_analyst",
            stage="signal_analyst",
            instructions="Return JSON for the signal.",
            input_payload={"token": "ABC"},
            output_type=Payload,
            prompt_version="p1",
            schema_version="s1",
            workflow_name="workflow",
            agent_name="agent",
        ),
        model_name=model_name,
        timeout_seconds=30.0,
        capability_profile=profile,
    )


def test_json_object_strategy_uses_registered_model_request_options_by_default(fake_litellm: FakeCompletions) -> None:
    async def scenario() -> None:
        strategy = ChatJsonObjectStrategy(api_key="sk-test", base_url="https://example.com/v1")

        await strategy.run(_context(capability_profile=resolve_agent_capability_profile(model="deepseek-v4-flash")))

        call = fake_litellm.calls[0]
        assert call["response_format"] == {"type": "json_object"}
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}

    asyncio.run(scenario())


def test_json_object_strategy_keeps_explicit_litellm_provider_prefix(fake_litellm: FakeCompletions) -> None:
    async def scenario() -> None:
        strategy = ChatJsonObjectStrategy(api_key="sk-test", base_url="https://example.com/v1")

        await strategy.run(_context(model_name="deepseek/deepseek-chat"))

        assert fake_litellm.calls[0]["model"] == "deepseek/deepseek-chat"

    asyncio.run(scenario())
