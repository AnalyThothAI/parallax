from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from parallax.domains.asset_market.types import MarketTick


@dataclass(frozen=True, slots=True)
class MarketTickPersistenceResult:
    inserted_ids: list[str]
    changed_targets: list[tuple[str, str]]

    @property
    def inserted(self) -> int:
        return len(self.inserted_ids)


class MarketTickPersistenceService:
    def __init__(self, repos: Any) -> None:
        self.repos = repos

    def insert_ticks_and_enqueue_current_dirty(
        self,
        ticks: Iterable[MarketTick],
        *,
        reason: str,
        now_ms: int,
        fail_after_ticks_for_test: bool = False,
    ) -> MarketTickPersistenceResult:
        materialized = list(ticks)
        self.repos.require_transaction(operation="market_tick_persistence")
        if not materialized:
            return MarketTickPersistenceResult(inserted_ids=[], changed_targets=[])

        tick_by_id = {tick.tick_id: tick for tick in materialized}
        inserted_ids = [str(tick_id) for tick_id in self.repos.market_ticks.insert_ticks_returning_ids(materialized)]

        changed_targets: list[tuple[str, str]] = list(
            dict.fromkeys(
                (str(tick.target_type), str(tick.target_id))
                for inserted_id in inserted_ids
                if (tick := tick_by_id.get(inserted_id)) is not None
            )
        )
        if changed_targets:
            self.repos.market_tick_current_dirty_targets.enqueue_targets(
                changed_targets,
                reason=reason,
                now_ms=int(now_ms),
            )
        if fail_after_ticks_for_test:
            raise RuntimeError("fail_after_ticks_for_test")
        return MarketTickPersistenceResult(inserted_ids=inserted_ids, changed_targets=changed_targets)
