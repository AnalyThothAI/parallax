"""OpenAI SDK wrapper for the Pulse price-action tool."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.integrations.openai_agents.tools._context import PulseToolContext

_DEFAULT_HOURS = 24


def _impl_get_target_price_action(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
    hours: int = _DEFAULT_HOURS,
) -> dict[str, Any]:
    """Pure SDK-adapter implementation; exposed for unit tests."""
    return ctx_payload.tool_runtime.get_target_price_action(target_id=target_id, hours=hours)


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
