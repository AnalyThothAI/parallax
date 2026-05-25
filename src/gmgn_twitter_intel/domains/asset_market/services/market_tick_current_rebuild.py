from __future__ import annotations

from typing import Any


class MarketTickCurrentRebuildService:
    def __init__(self, repos: Any) -> None:
        self.repos = repos

    def rebuild_all(self, *, now_ms: int) -> dict[str, int]:
        with self.repos.transaction():
            self.repos.market_tick_current.truncate_current()
            changed = 0
            scanned = 0
            for tick_row in self.repos.market_tick_current.latest_ticks_for_all_targets():
                scanned += 1
                if self.repos.market_tick_current.upsert_current_from_tick(tick_row, now_ms=now_ms):
                    changed += 1
        return {"scanned": scanned, "changed": changed}
