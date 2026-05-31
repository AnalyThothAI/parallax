from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from parallax.domains.pulse_lab.types.agent_decision import (
    BearCaseMemo,
    FinalDecision,
    SignalAnalystMemo,
)
from parallax.integrations.model_execution.output_schema import (
    StrictJsonOutputSchema,
)


class _NestedPayload(BaseModel):
    label: str


class _Payload(BaseModel):
    name: str
    nested: _NestedPayload
    tags: list[_NestedPayload] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def _walk_schema(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_schema(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_schema(child)


def test_strict_json_output_schema_flattens_refs_and_forces_strict_objects() -> None:
    schema = StrictJsonOutputSchema(_Payload).json_schema()

    assert "$defs" not in schema
    assert "definitions" not in schema
    assert "$ref" not in str(schema)
    assert schema["required"] == ["name", "nested", "tags", "metadata"]

    object_nodes = [node for node in _walk_schema(schema) if node.get("type") == "object"]
    assert object_nodes
    assert all(node.get("additionalProperties") is False for node in object_nodes)


def test_pulse_agent_output_schemas_match_litellm_json_object_subset() -> None:
    forbidden_keywords = {
        "$defs",
        "$ref",
        "allOf",
        "default",
        "definitions",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "not",
        "oneOf",
        "patternProperties",
        "then",
    }

    for output_type in (SignalAnalystMemo, BearCaseMemo, FinalDecision):
        schema = StrictJsonOutputSchema(output_type).json_schema()

        assert schema["type"] == "object"
        assert "anyOf" not in schema
        for node in _walk_schema(schema):
            assert forbidden_keywords.isdisjoint(node.keys())
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert node.get("required") == list(node.get("properties", {}).keys())


def test_final_decision_schema_keeps_worker_enriched_urls_as_empty_object_contract() -> None:
    schema = StrictJsonOutputSchema(FinalDecision).json_schema()

    evidence_urls = schema["properties"]["evidence_event_urls"]
    assert evidence_urls["type"] == "object"
    assert evidence_urls["additionalProperties"] is False
    assert evidence_urls.get("properties", {}) == {}
    assert "evidence_event_urls" in schema["required"]


def test_strict_json_output_schema_extracts_json_from_prose_before_validation() -> None:
    payload = StrictJsonOutputSchema(_Payload).validate_json(
        'prefix text {"name": "alpha", "nested": {"label": "beta"}, "tags": [], "metadata": {}} suffix'
    )

    assert isinstance(payload, _Payload)
    assert payload.name == "alpha"
