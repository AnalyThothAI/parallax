"""OpenAI SDK wrapper for the Pulse official-profile tool."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from gmgn_twitter_intel.integrations.openai_agents.tools._context import PulseToolContext


def _impl_get_official_token_profile(
    ctx_payload: PulseToolContext,
    *,
    target_id: str,
) -> dict[str, Any]:
    """Pure SDK-adapter implementation; exposed for unit tests."""
    return ctx_payload.tool_runtime.get_official_token_profile(target_id=target_id)


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
