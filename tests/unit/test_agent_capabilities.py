import pytest
from pydantic import ValidationError


def test_qwen_profile_uses_json_object_with_client_validation() -> None:
    from parallax.platform.agent_capabilities import resolve_agent_capability_profile

    profile = resolve_agent_capability_profile(model="qwen3.6")

    assert profile.provider_family == "litellm"
    assert profile.request_options.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_deepseek_profile_uses_json_object_with_client_validation() -> None:
    from parallax.platform.agent_capabilities import resolve_agent_capability_profile

    profile = resolve_agent_capability_profile(model="deepseek-v4-flash")

    assert profile.provider_family == "deepseek"
    assert profile.request_options.extra_body == {"thinking": {"type": "disabled"}}


def test_explicit_profile_override_wins_for_arbitrary_model() -> None:
    from parallax.platform.agent_capabilities import (
        AgentCapabilityProfile,
        resolve_agent_capability_profile,
    )

    override = AgentCapabilityProfile(
        provider_family="litellm",
        client_validation_retries=2,
    )

    profile = resolve_agent_capability_profile(model="local-experiment", override=override)

    assert profile == override


def test_registered_model_profile_preserves_request_options_when_overriding_capability_labels() -> None:
    from parallax.platform.agent_capabilities import (
        AgentCapabilityProfile,
        resolve_agent_capability_profile,
    )

    override = AgentCapabilityProfile(
        provider_family="deepseek",
        client_validation_retries=2,
    )

    profile = resolve_agent_capability_profile(model="deepseek-v4-flash", override=override)

    assert profile.client_validation_retries == 2
    assert profile.request_options.extra_body == {"thinking": {"type": "disabled"}}


def test_registered_model_profile_merges_request_option_overrides() -> None:
    from parallax.platform.agent_capabilities import (
        AgentCapabilityProfile,
        AgentRequestOptions,
        resolve_agent_capability_profile,
    )

    override = AgentCapabilityProfile(request_options=AgentRequestOptions(max_tokens=2200))

    profile = resolve_agent_capability_profile(model="deepseek-v4-flash", override=override)

    assert profile.request_options.extra_body == {"thinking": {"type": "disabled"}}
    assert profile.request_options.max_tokens == 2200


def test_profile_rejects_legacy_output_strategy_fields() -> None:
    from parallax.platform.agent_capabilities import AgentCapabilityProfile

    with pytest.raises(ValidationError, match="output_strategy"):
        AgentCapabilityProfile(
            provider_family="litellm",
            output_strategy="legacy",
        )
