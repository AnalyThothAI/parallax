from __future__ import annotations

from typing import Any, Protocol


class HandleTopicSummaryProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def request_audit(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def summarize_handle(
        self,
        *,
        handle: str,
        events: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


__all__ = ["HandleTopicSummaryProvider"]
