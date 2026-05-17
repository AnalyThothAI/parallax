from __future__ import annotations

from typing import Any, Protocol

from gmgn_twitter_intel.domains.pulse_lab.providers import ToolBudgetExceeded
from gmgn_twitter_intel.integrations.openai_agents.tools._context import PulseToolContext
from gmgn_twitter_intel.integrations.openai_agents.tools.official_profile import (
    get_official_token_profile,
)
from gmgn_twitter_intel.integrations.openai_agents.tools.price_action import (
    get_target_price_action,
)
from gmgn_twitter_intel.integrations.openai_agents.tools.recent_tweets import (
    get_target_recent_tweets,
)


class ToolResult(Protocol):
    """Every Investigator tool must return a value satisfying this shape.

    ``contributed_event_ids`` is used by the worker-side hallucination guard:
    the Investigator-returned ``supporting_event_ids`` must be a subset of the
    union of all tool calls' ``contributed_event_ids`` together with the
    pulse context's ``evidence_event_ids`` and ``source_event_ids``.

    Concrete tool implementations (Task 4) will be plain dataclasses or
    Pydantic models that satisfy this Protocol structurally; no runtime
    isinstance check is performed.
    """

    data: dict[str, Any]
    contributed_event_ids: list[str]


__all__ = [
    "PulseToolContext",
    "ToolBudgetExceeded",
    "ToolResult",
    "get_official_token_profile",
    "get_target_price_action",
    "get_target_recent_tweets",
]
