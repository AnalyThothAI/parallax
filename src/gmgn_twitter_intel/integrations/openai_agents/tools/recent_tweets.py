"""``get_target_recent_tweets``: fetch 24h tweets for a Pulse target.

Ranked by ``token_intent_resolutions.resolution_status`` (EXACT > UNIQUE_BY_CONTEXT
> AMBIGUOUS) and ``confidence``; tweets that did not pass attribution carry no
weight and are omitted.

The tweet URL is constructed deterministically from ``events.author_handle`` and
``events.tweet_id`` matching :func:`canonical_tweet_url`.
"""

from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import fetch_target_recent_tweets
from gmgn_twitter_intel.integrations.openai_agents.tools._context import (
    PulseToolContext,
    _check_and_increment_budget,
)

_MAX_RESULT_BYTES = 4 * 1024
_DEFAULT_LIMIT = 15
_MIN_LIMIT = 1
_MAX_LIMIT = 30


def _impl_get_target_recent_tweets(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Pure implementation; exposed for unit tests.

    Mirrors the SDK-decorated tool but takes the unwrapped ``PulseToolContext``
    directly so tests don't need to construct a ``RunContextWrapper``.
    """
    _check_and_increment_budget(ctx_payload)
    pool = ctx_payload.db_pool
    target = str(target_id or "").strip()
    bounded_limit = max(_MIN_LIMIT, min(int(limit), _MAX_LIMIT))
    if not target:
        return {
            "data": {"target_id": "", "tweets": []},
            "contributed_event_ids": [],
        }

    payload = fetch_target_recent_tweets(pool, target_id=target, limit=bounded_limit)
    if "error" in payload:
        return {"data": {"error": payload["error"]}, "contributed_event_ids": []}

    tweets = list(payload.get("tweets") or [])
    event_ids = [str(tweet.get("event_id")) for tweet in tweets if isinstance(tweet, dict) and tweet.get("event_id")]
    data: dict[str, Any] = {**payload, "tweets": tweets}
    truncated = False
    while (
        len(json.dumps(data).encode("utf-8")) > _MAX_RESULT_BYTES and tweets
    ):
        tweets.pop()
        if event_ids:
            event_ids.pop()
        data["tweets"] = tweets
        truncated = True
    if truncated:
        data["truncated"] = True

    for eid in event_ids:
        ctx_payload.contributed_event_ids.add(eid)

    return {"data": data, "contributed_event_ids": event_ids}


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
