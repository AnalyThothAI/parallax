"""Internal shared types for Investigator tools.

Lives in a private module so individual tool files can import
``PulseToolContext`` / ``_check_and_increment_budget`` without triggering the
circular import that would arise if these were defined in
``tools/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolBudgetExceeded(RuntimeError):
    """Investigator tool call exceeded ``investigator_max_tool_calls`` for the route.

    Each tool function calls :func:`_check_and_increment_budget` on entry; when
    the counter exceeds the configured budget this is raised, terminating the
    current ``Runner.run`` invocation and surfacing the budget breach to the
    caller (worker) for telemetry / fallback handling.
    """


@dataclass
class PulseToolContext:
    """``RunContext.context`` payload shared with every Investigator tool.

    Wired via the openai-agents SDK ``RunContextWrapper[PulseToolContext]``
    mechanism: the worker constructs one instance per Investigator stage and
    passes it as ``Runner.run(..., context=...)``; tools receive it via
    ``ctx.context``.

    Attributes:
        db_pool: A ``DBPoolBundle.worker_pool`` (or compatible) used by tools
            for synchronous ``with pool.connection() as conn`` queries.
        tool_calls_count: Running counter incremented by each tool entry.
        investigator_max_tool_calls: Per-route budget (3 for cex routes, 5 for
            meme — see OQ-1 decision).
        contributed_event_ids: Union of every tool's ``contributed_event_ids``;
            consumed by the worker hallucination guard.
    """

    db_pool: Any
    tool_calls_count: int = 0
    investigator_max_tool_calls: int = 5
    contributed_event_ids: set[str] = field(default_factory=set)


def _check_and_increment_budget(ctx: PulseToolContext) -> None:
    """Increment ``tool_calls_count`` and raise if the budget is exceeded.

    MUST be called as the very first statement of every Investigator tool
    function body, before any DB or external work.
    """
    ctx.tool_calls_count += 1
    if ctx.tool_calls_count > ctx.investigator_max_tool_calls:
        raise ToolBudgetExceeded(
            f"investigator tool call budget exceeded: "
            f"{ctx.tool_calls_count} > {ctx.investigator_max_tool_calls}"
        )
