"""``get_official_token_profile``: pull the canonical asset_profiles row.

Returns the most recent ``status='ready'`` ``asset_profiles`` row keyed by
``asset_id == target_id``. Explicitly surfaces
``description_source_available`` so the model knows whether to expect a usable
``description`` (per OQ-3 decision: GMGN ``description`` empirically is empty
in production today).
"""

from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.domains.pulse_lab.queries.agent_tool_queries import fetch_official_token_profile
from gmgn_twitter_intel.integrations.openai_agents.tools._context import (
    PulseToolContext,
    _check_and_increment_budget,
)

_MAX_RESULT_BYTES = 4 * 1024


def _impl_get_official_token_profile(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
) -> dict[str, Any]:
    """Pure implementation; exposed for unit tests."""
    _check_and_increment_budget(ctx_payload)
    pool = ctx_payload.db_pool
    target = str(target_id or "").strip()
    if not target:
        return {"data": {}, "contributed_event_ids": []}

    data = fetch_official_token_profile(pool, target_id=target)

    if len(json.dumps(data).encode("utf-8")) > _MAX_RESULT_BYTES:
        # Description is the only field that can blow past 4 KiB.
        if isinstance(data.get("description"), str):
            data["description"] = data["description"][:1500]
        data["truncated"] = True

    return {"data": data, "contributed_event_ids": []}


@function_tool
async def get_official_token_profile(
    ctx: RunContextWrapper[PulseToolContext],
    target_id: str,
) -> dict[str, Any]:
    """Return the most recent ``status='ready'`` ``asset_profiles`` row for the target.

    Returns ``{"data": {"target_id": ..., "symbol": ..., "name": ...,
    "website": ..., "twitter_username": ..., "telegram": ...,
    "description": ..., "description_source_available": bool,
    "logo_url": ..., "banner_url": ...}, "contributed_event_ids": []}``.

    Per OQ-3 the GMGN ``description`` field is empty for ~all live profiles
    today, so ``description_source_available`` is the load-bearing signal —
    when ``False`` the model MUST NOT fabricate a description.

    Args:
        target_id: The asset id used as ``asset_profiles.asset_id``.
    """
    return _impl_get_official_token_profile(ctx.context, target_id=target_id)
