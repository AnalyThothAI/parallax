from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def needs_news_item_agent_brief(item: Mapping[str, Any]) -> bool:
    provider_signal = _mapping(item.get("provider_signal_json"))
    return not (
        str(item.get("provider_type") or "").strip().lower() == "opennews"
        and str(provider_signal.get("source") or "").strip().lower() == "provider"
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = ["needs_news_item_agent_brief"]
