from __future__ import annotations

from typing import Any, Protocol


class SocialEventEnrichmentProvider(Protocol):
    provider: str
    model: str
    timeout_seconds: float

    def request_audit(
        self,
        *,
        event: dict[str, Any],
        entities: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def enrich_event(
        self,
        *,
        event: dict[str, Any],
        entities: list[dict[str, Any]],
        run_id: str,
        job: dict[str, Any],
    ) -> Any: ...


__all__ = ["SocialEventEnrichmentProvider"]
