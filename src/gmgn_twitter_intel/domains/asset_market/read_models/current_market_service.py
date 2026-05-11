from __future__ import annotations

from typing import Any


class CurrentMarketService:
    def __init__(self, *, current_market):
        self.current_market = current_market

    def current_market_snapshot(self, *, target_type: str, target_id: str, now_ms: int) -> dict[str, Any]:
        snapshots = self.current_market.current_for_subjects(
            [{"target_type": target_type, "target_id": target_id}],
            now_ms=now_ms,
        )
        return snapshots.get((target_type, target_id)) or {
            "target_type": target_type,
            "target_id": target_id,
            "market_status": "missing",
            "fields": {},
        }
