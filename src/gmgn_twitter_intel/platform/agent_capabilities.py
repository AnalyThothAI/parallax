from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentOutputStrategy(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class AgentSchemaEnforcement(StrEnum):
    PROVIDER = "provider"
    CLIENT_VALIDATE = "client_validate"


class AgentProviderFamily(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
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

    provider_family: AgentProviderFamily = AgentProviderFamily.OPENAI_COMPATIBLE
    output_strategy: AgentOutputStrategy = AgentOutputStrategy.JSON_SCHEMA
    schema_enforcement: AgentSchemaEnforcement = AgentSchemaEnforcement.PROVIDER
    client_validation_retries: int = Field(default=1, ge=0)
    request_options: AgentRequestOptions = Field(default_factory=AgentRequestOptions)

    @field_validator("provider_family", mode="before")
    @classmethod
    def parse_provider_family(cls, value: Any) -> Any:
        return _normalized(value)

    @field_validator("output_strategy", mode="before")
    @classmethod
    def parse_output_strategy(cls, value: Any) -> Any:
        return _normalized(value)

    @field_validator("schema_enforcement", mode="before")
    @classmethod
    def parse_schema_enforcement(cls, value: Any) -> Any:
        return _normalized(value)

    @model_validator(mode="after")
    def validate_enforcement(self) -> AgentCapabilityProfile:
        if (
            self.output_strategy == AgentOutputStrategy.JSON_SCHEMA
            and self.schema_enforcement != AgentSchemaEnforcement.PROVIDER
        ):
            raise ValueError("json_schema output_strategy requires provider schema_enforcement")
        if (
            self.output_strategy == AgentOutputStrategy.JSON_OBJECT
            and self.schema_enforcement != AgentSchemaEnforcement.CLIENT_VALIDATE
        ):
            raise ValueError("json_object output_strategy requires client_validate schema_enforcement")
        return self


_MODEL_CAPABILITY_DEFAULTS: dict[str, AgentCapabilityProfile] = {
    "deepseek-v4-flash": AgentCapabilityProfile(
        provider_family=AgentProviderFamily.DEEPSEEK,
        output_strategy=AgentOutputStrategy.JSON_OBJECT,
        schema_enforcement=AgentSchemaEnforcement.CLIENT_VALIDATE,
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
        payload[field_name] = getattr(override, field_name)
    return AgentCapabilityProfile(**payload)


__all__ = [
    "AgentCapabilityProfile",
    "AgentOutputStrategy",
    "AgentProviderFamily",
    "AgentRequestOptions",
    "AgentSchemaEnforcement",
    "resolve_agent_capability_profile",
]
