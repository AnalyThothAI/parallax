from __future__ import annotations

from typing import Any

import jsonref
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase


class StrictJsonOutputSchema(AgentOutputSchemaBase):
    """qwen3.6 + llama.cpp compatible structured-output wrapper."""

    def __init__(self, output_type: type[Any]) -> None:
        self._output_type = output_type
        self._schema = AgentOutputSchema(output_type, strict_json_schema=False)
        raw = self._schema.json_schema()
        cleaned = _coerce_dict_additional_properties_to_false(raw)
        replaced = jsonref.replace_refs(cleaned, proxies=False, lazy_load=False)
        flattened = _strip_defs(replaced)
        self._flat = _force_strict_object_shape(flattened)

    @property
    def output_type(self) -> type[Any]:
        """Expose underlying Pydantic class for InstructorSafetyNet fallback."""
        return self._output_type

    def is_plain_text(self) -> bool:
        return self._schema.is_plain_text()

    def name(self) -> str:
        return self._schema.name()

    def json_schema(self) -> dict[str, Any]:
        return self._flat

    def is_strict_json_schema(self) -> bool:
        return True

    def validate_json(self, json_str: str) -> Any:
        text = str(json_str or "")
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else text
        return self._schema.validate_json(candidate)


def _strip_defs(schema: Any) -> Any:
    """Drop the top-level ``$defs`` / ``definitions`` blocks after ref replacement."""

    if not isinstance(schema, dict):
        return schema
    return {key: value for key, value in schema.items() if key not in ("$defs", "definitions")}


def _coerce_dict_additional_properties_to_false(schema: Any) -> Any:
    """Recursively replace ``additionalProperties: <object>`` with ``False``."""

    if isinstance(schema, dict):
        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "additionalProperties" and isinstance(value, dict):
                result[key] = False
            else:
                result[key] = _coerce_dict_additional_properties_to_false(value)
        return result
    if isinstance(schema, list):
        return [_coerce_dict_additional_properties_to_false(item) for item in schema]
    return schema


def _force_strict_object_shape(schema: Any) -> Any:
    """Apply strict-mode object requirements without delegating to the SDK validator."""

    if isinstance(schema, dict):
        new = dict(schema)
        if new.get("type") == "object":
            new.setdefault("additionalProperties", False)
            properties = new.get("properties")
            if isinstance(properties, dict):
                new["required"] = list(properties.keys())
                new["properties"] = {name: _force_strict_object_shape(prop) for name, prop in properties.items()}
        if "items" in new:
            new["items"] = _force_strict_object_shape(new["items"])
        for key in ("$defs", "definitions"):
            if key in new and isinstance(new[key], dict):
                new[key] = {name: _force_strict_object_shape(def_schema) for name, def_schema in new[key].items()}
        for key in ("anyOf", "allOf", "oneOf"):
            if key in new and isinstance(new[key], list):
                new[key] = [_force_strict_object_shape(variant) for variant in new[key]]
        return new
    if isinstance(schema, list):
        return [_force_strict_object_shape(item) for item in schema]
    return schema


__all__ = ["StrictJsonOutputSchema"]
