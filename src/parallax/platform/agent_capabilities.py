from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentProviderFamily(StrEnum):
    LITELLM = "litellm"
    DEEPSEEK = "deepseek"


def _normalized(value: Any) -> Any:
    if value is None:
        return value
    return str(value).strip().lower()


class AgentRequestOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extra_body: dict[str, Any] = Field(default_factory=dict)
    max_tokens: int | None = Field(default=None, ge=1)

    def option_keys(self) -> list[str]:
        keys: list[str] = []
        if self.extra_body:
            keys.append("extra_body")
        if self.max_tokens is not None:
            keys.append("max_tokens")
        return keys


class AgentCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_family: AgentProviderFamily = AgentProviderFamily.LITELLM
    client_validation_retries: int = Field(default=1, ge=0)
    request_options: AgentRequestOptions = Field(default_factory=AgentRequestOptions)

    @field_validator("provider_family", mode="before")
    @classmethod
    def parse_provider_family(cls, value: Any) -> Any:
        return _normalized(value)


_MODEL_CAPABILITY_DEFAULTS: dict[str, AgentCapabilityProfile] = {
    "qwen3.6": AgentCapabilityProfile(
        provider_family=AgentProviderFamily.LITELLM,
        client_validation_retries=1,
        request_options=AgentRequestOptions(extra_body={"chat_template_kwargs": {"enable_thinking": False}}),
    ),
    "deepseek-v4-flash": AgentCapabilityProfile(
        provider_family=AgentProviderFamily.DEEPSEEK,
        client_validation_retries=1,
        request_options=AgentRequestOptions(extra_body={"thinking": {"type": "disabled"}}),
    ),
}


def resolve_agent_capability_profile(
    *,
    model: str,
    override: AgentCapabilityProfile | None = None,
) -> AgentCapabilityProfile:
    key = str(model or "").strip().lower()
    profile = _MODEL_CAPABILITY_DEFAULTS.get(key) or AgentCapabilityProfile()
    if override is None:
        return profile
    payload = profile.model_dump(mode="python")
    for field_name in override.model_fields_set:
        if field_name == "request_options":
            payload[field_name] = _merge_request_options(
                base=profile.request_options,
                override=override.request_options,
            )
            continue
        payload[field_name] = getattr(override, field_name)
    return AgentCapabilityProfile(**payload)


def _merge_request_options(*, base: AgentRequestOptions, override: AgentRequestOptions) -> AgentRequestOptions:
    payload = base.model_dump(mode="python")
    for field_name in override.model_fields_set:
        payload[field_name] = getattr(override, field_name)
    return AgentRequestOptions(**payload)


__all__ = [
    "AgentCapabilityProfile",
    "AgentProviderFamily",
    "AgentRequestOptions",
    "resolve_agent_capability_profile",
]
