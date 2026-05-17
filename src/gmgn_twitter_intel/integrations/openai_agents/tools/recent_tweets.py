"""OpenAI SDK wrapper for the Pulse recent-tweets tool."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.integrations.openai_agents.tools._context import PulseToolContext

_DEFAULT_LIMIT = 15


def _impl_get_target_recent_tweets(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Pure SDK-adapter implementation; exposed for unit tests."""
    return ctx_payload.tool_runtime.get_target_recent_tweets(target_id=target_id, limit=limit)


@function_tool
async def get_target_recent_tweets(
    ctx: RunContextWrapper[PulseToolContext],
    target_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return up to ``limit`` recent tweets (24h window) for a Pulse target.

    Each tweet entry exposes ``event_id``, ``author_handle``, ``author_followers``,
    ``received_at_ms``, ``text_clean``, ``tweet_url`` (https://x.com/<handle>/status/<id>),
    ``resolution_status`` (EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS), and a derived
    ``attribution_weight``. Sorted by resolution strength then recency.

    Returns ``{"data": {"target_id": ..., "tweets": [...], "truncated"?: bool},
    "contributed_event_ids": [...]}``. Result is truncated to keep the
    serialized payload under 4 KiB. On DB error, returns
    ``{"data": {"error": "..."}, "contributed_event_ids": []}``.

    Args:
        target_id: The Pulse target id (``token_intent_resolutions.target_id``).
        limit: Max tweets to return (clamped to 1..30, default 15).
    """
    return _impl_get_target_recent_tweets(
        ctx.context, target_id=target_id, limit=limit
    )
