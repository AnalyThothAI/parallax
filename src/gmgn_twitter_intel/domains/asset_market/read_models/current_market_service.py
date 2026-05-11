from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.market_field_facts import (
    DEFAULT_MARKET_METADATA_FRESH_MS,
    DEFAULT_PRICE_FRESH_MS,
    field_fact,
)

_PRICE_FIELDS = frozenset({"price_usd", "price_quote", "quote_symbol", "price_basis"})
_MARKET_FIELD_KEYS = (
    "price_usd",
    "price_quote",
    "quote_symbol",
    "price_basis",
    "market_cap_usd",
    "liquidity_usd",
    "holders",
    "volume_24h_usd",
    "open_interest_usd",
)


class CurrentMarketService:
    def __init__(self, *, current_market: Any) -> None:
        self.current_market = current_market

    def current_market_snapshot(self, *, target_type: str, target_id: str, now_ms: int) -> dict[str, Any]:
        snapshots = self.current_market.current_for_subjects(
            [{"target_type": target_type, "target_id": target_id}],
            now_ms=now_ms,
        )
        return snapshots.get((target_type, target_id)) or _missing_snapshot(
            target_type=target_type,
            target_id=target_id,
            now_ms=now_ms,
        )


def _missing_snapshot(*, target_type: str, target_id: str, now_ms: int) -> dict[str, Any]:
    fields = {
        key: field_fact(
            value=None,
            observed_at_ms=None,
            now_ms=now_ms,
            provider=None,
            observation_id=None,
            fresh_ms=DEFAULT_PRICE_FRESH_MS if key in _PRICE_FIELDS else DEFAULT_MARKET_METADATA_FRESH_MS,
        )
        for key in _MARKET_FIELD_KEYS
    }
    return {
        "target_type": target_type,
        "target_id": target_id,
        "market_status": "missing",
        "fields": fields,
    }
