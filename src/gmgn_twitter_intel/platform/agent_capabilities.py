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


class AgentCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_family: AgentProviderFamily = AgentProviderFamily.OPENAI_COMPATIBLE
    output_strategy: AgentOutputStrategy = AgentOutputStrategy.JSON_SCHEMA
    schema_enforcement: AgentSchemaEnforcement = AgentSchemaEnforcement.PROVIDER
    client_validation_retries: int = Field(default=1, ge=0)

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
    ),
}


def resolve_agent_capability_profile(
    *,
    model: str,
    override: AgentCapabilityProfile | None = None,
) -> AgentCapabilityProfile:
    if override is not None:
        return override
    key = str(model or "").strip().lower()
    profile = _MODEL_CAPABILITY_DEFAULTS.get(key)
    if profile is not None:
        return profile
    return AgentCapabilityProfile()


__all__ = [
    "AgentCapabilityProfile",
    "AgentOutputStrategy",
    "AgentProviderFamily",
    "AgentSchemaEnforcement",
    "resolve_agent_capability_profile",
]
