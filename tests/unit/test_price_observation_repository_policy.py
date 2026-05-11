from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository


def test_gmgn_payload_is_rejected_as_market_observation_provider() -> None:
    conn = _CaptureConnection()

    with pytest.raises(ValueError, match="identity evidence only"):
        PriceObservationRepository(conn).insert_observation(
            provider="gmgn_payload",
            pricefeed_id=None,
            observed_at_ms=1_700_086_420_000,
            subject_type="Asset",
            subject_id="asset:solana:token:TROLL",
            price_usd=0.222,
            price_basis="usd",
            market_cap_usd=222_000_000,
            liquidity_usd=7_000_000,
            volume_24h_usd=11_000_000,
            holders=88_000,
            commit=False,
        )

    assert conn.executed == []


class _CaptureConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _CaptureConnection:
        self.executed.append((str(sql), params))
        return self

    def fetchone(self) -> None:
        return None
