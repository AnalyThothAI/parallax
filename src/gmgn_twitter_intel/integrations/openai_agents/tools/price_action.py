"""``get_target_price_action``: summarise market_ticks for a Pulse target.

Aggregates the configured time window (default 24h) of ``market_ticks`` for
``target_id`` and returns first/last price, volume and liquidity peaks, holders,
market cap and a small candle count. Does not load every tick — heavy series
data is left to the dedicated read model.
"""

from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import fetch_target_price_action
from gmgn_twitter_intel.integrations.openai_agents.tools._context import (
    PulseToolContext,
    _check_and_increment_budget,
)

_MAX_RESULT_BYTES = 4 * 1024
_DEFAULT_HOURS = 24
_MIN_HOURS = 1
_MAX_HOURS = 168  # 7d


def _impl_get_target_price_action(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
    hours: int = _DEFAULT_HOURS,
) -> dict[str, Any]:
    """Pure implementation; exposed for unit tests."""
    _check_and_increment_budget(ctx_payload)
    pool = ctx_payload.db_pool
    target = str(target_id or "").strip()
    bounded_hours = max(_MIN_HOURS, min(int(hours), _MAX_HOURS))
    if not target:
        return {
            "data": {"target_id": "", "hours": bounded_hours, "candles_count": 0},
            "contributed_event_ids": [],
        }

    payload = fetch_target_price_action(pool, target_id=target, hours=bounded_hours)
    if len(json.dumps(payload).encode("utf-8")) > _MAX_RESULT_BYTES:
        # Aggregate payload is small by construction; if somehow oversized,
        # drop the peak / min fields first.
        for key in (
            "holders_peak",
            "volume_24h_peak_usd",
            "liquidity_peak_usd",
            "price_min_usd",
            "price_max_usd",
        ):
            payload.pop(key, None)
            if len(json.dumps(payload).encode("utf-8")) <= _MAX_RESULT_BYTES:
                break
        payload["truncated"] = True

    return {"data": payload, "contributed_event_ids": []}


@function_tool
async def get_target_price_action(
    ctx: RunContextWrapper[PulseToolContext],
    target_id: str,
    hours: int = _DEFAULT_HOURS,
) -> dict[str, Any]:
    """Return a summary of market_ticks for ``target_id`` over the last ``hours``.

    Returns ``{"data": {"target_id": ..., "current_price_usd": ...,
    "price_change_window_pct": ..., "volume_24h_usd": ..., "liquidity_usd": ...,
    "market_cap_usd": ..., "holders": ..., "candles_count": N,
    "first_seen_ms": ..., "latest_seen_ms": ...}, "contributed_event_ids": []}``.

    ``contributed_event_ids`` is always empty: market_ticks are not Twitter
    events and do not back the Investigator's ``supporting_event_ids`` guard.

    Args:
        target_id: The Pulse target id used in ``market_ticks.target_id``.
        hours: Aggregation window in hours (clamped to 1..168, default 24).
    """
    return _impl_get_target_price_action(
        ctx.context, target_id=target_id, hours=hours
    )
