from __future__ import annotations

from typing import Any

from .asset_repository import AssetRepository


class MarketRepository(AssetRepository):
    """Venue-market repository for V3 while asset registry is being split."""

    def __init__(self, conn: Any):
        super().__init__(conn)
