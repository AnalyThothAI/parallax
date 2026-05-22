from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.types import NormalizedEquityDocument


def normalize_ir_feed_documents(
    *,
    source: Mapping[str, Any],
    payload: Mapping[str, Any],
    fetched_at_ms: int,
) -> list[NormalizedEquityDocument]:
    del source, payload, fetched_at_ms
    return []
