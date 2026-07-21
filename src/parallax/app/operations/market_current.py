from __future__ import annotations

import time
from typing import Any

from parallax.app.runtime.repository_session import repositories
from parallax.domains.asset_market.services.market_tick_persistence import (
    MarketTickPersistenceService,
)
from parallax.platform.config.settings import Settings


def rebuild_market_tick_current_batch(
    settings: Settings,
    *,
    after: tuple[str, str] | None,
    limit: int,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Rebuild one stable-key batch of market current rows from material facts."""
    with repositories(settings) as repos, repos.transaction():
        result = MarketTickPersistenceService(repos).rebuild_current_batch(
            after=after,
            limit=limit,
            now_ms=_now_ms() if now_ms is None else int(now_ms),
        )
    return {
        "scanned_targets": result.scanned_targets,
        "changed_targets": len(result.changed_targets),
        "next_cursor": (
            {
                "target_type": result.next_cursor[0],
                "target_id": result.next_cursor[1],
            }
            if result.next_cursor is not None
            else None
        ),
        "batch_full": result.scanned_targets == int(limit),
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["rebuild_market_tick_current_batch"]
