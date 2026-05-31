from __future__ import annotations

import dataclasses
from typing import Any, cast


def _json_safe(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 6:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(child, depth + 1) for key, child in value.items() if child is not None}
    if isinstance(value, list | tuple):
        return [_json_safe(item, depth + 1) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump(mode="json")
        if isinstance(data, dict):
            return _json_safe(data, depth + 1)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_safe(dataclasses.asdict(value), depth + 1)
    return str(value)


def extract_model_usage(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    candidates: list[Any] = [
        getattr(result, "usage", None),
        getattr(getattr(result, "context_wrapper", None), "usage", None),
    ]
    for attr in ("raw_response", "response", "final_response"):
        response = getattr(result, attr, None)
        if response is not None:
            candidates.append(getattr(response, "usage", None))
    responses = getattr(result, "raw_responses", None) or getattr(result, "responses", None)
    if isinstance(responses, list | tuple):
        candidates.extend(getattr(response, "usage", None) for response in responses)
    for candidate in candidates:
        if candidate is None:
            continue
        data = _json_safe(candidate)
        if isinstance(data, dict) and data:
            return cast(dict[str, Any], data)
    return {}


__all__ = ["extract_model_usage"]
