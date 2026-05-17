"""Internal shared context for OpenAI Investigator tools."""

from __future__ import annotations

from dataclasses import dataclass

from gmgn_twitter_intel.domains.pulse_lab.providers import PulseAgentToolRuntime


@dataclass
class PulseToolContext:
    """``RunContext.context`` payload shared with OpenAI tool wrappers.

    The concrete runtime is injected from ``app/runtime/provider_wiring`` and
    owns all Pulse-specific query assembly, budgeting, and contributed id state.
    """

    tool_runtime: PulseAgentToolRuntime

    @property
    def tool_calls_count(self) -> int:
        return int(self.tool_runtime.tool_calls_count)

    @tool_calls_count.setter
    def tool_calls_count(self, value: int) -> None:
        self.tool_runtime.tool_calls_count = int(value)

    @property
    def investigator_max_tool_calls(self) -> int:
        return int(self.tool_runtime.investigator_max_tool_calls)

    @property
    def contributed_event_ids(self) -> set[str]:
        return self.tool_runtime.contributed_event_ids
