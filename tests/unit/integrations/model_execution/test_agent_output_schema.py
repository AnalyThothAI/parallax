from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


def test_strict_json_output_schema_extracts_json_from_prose_before_validation() -> None:
    payload = StrictJsonOutputSchema(_Payload).validate_json(
        'prefix text {"name": "alpha", "nested": {"label": "beta"}, "tags": [], "metadata": {}} suffix'
    )

    assert isinstance(payload, _Payload)
    assert payload.name == "alpha"
