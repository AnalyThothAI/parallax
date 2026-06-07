from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
) -> int:
    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return 100
    score = _optional_int(provider_signal.get("score"))
    if score is not None:
        return max(0, min(100, 100 - score))
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return 25
    return 100


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "news_item_agent_brief_priority",
]
