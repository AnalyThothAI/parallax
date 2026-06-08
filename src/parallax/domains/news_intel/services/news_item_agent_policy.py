from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
) -> int:
    return 100


__all__ = [
    "news_item_agent_brief_priority",
]
