from __future__ import annotations

from typing import Any


def postgres_safe_json(value: Any) -> Any:
    if isinstance(value, str):
        return postgres_safe_text(value)
    if isinstance(value, list):
        return [postgres_safe_json(item) for item in value]
    if isinstance(value, tuple):
        return [postgres_safe_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key).replace("\x00", ""): postgres_safe_json(item) for key, item in value.items()}
    return value


def postgres_safe_text(value: Any) -> str:
    return str(value or "").replace("\x00", "")
