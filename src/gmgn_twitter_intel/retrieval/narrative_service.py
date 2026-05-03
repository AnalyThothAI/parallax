from __future__ import annotations

WINDOW_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


class NarrativeService:
    def __init__(self, enrichment):
        self.enrichment = enrichment

    def account_narratives(
        self,
        *,
        window: str = "24h",
        limit: int = 50,
        handles: set[str] | None = None,
    ) -> list[dict]:
        return self.enrichment.account_narratives(
            window_ms=WINDOW_MS[window],
            limit=limit,
            handles=handles,
        )

    def narrative_flow(self, *, window: str, limit: int = 20) -> list[dict]:
        return self.enrichment.narrative_flow(window=window, limit=limit)
