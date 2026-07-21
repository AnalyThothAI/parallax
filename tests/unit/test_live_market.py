from __future__ import annotations

from decimal import Decimal

from parallax.domains.asset_market.services.live_market import (
    live_market_snapshot,
    live_market_update_payload,
)


def test_live_market_snapshot_exposes_requested_product_identity_from_durable_current() -> None:
    row = _current_row()

    snapshot = live_market_snapshot(
        row,
        target_type="Asset",
        target_id="asset:eip155:1:erc20:0xabc",
        now_ms=1_700_000_000_100,
    )

    assert snapshot["target_type"] == "Asset"
    assert snapshot["target_id"] == "asset:eip155:1:erc20:0xabc"
    assert snapshot["status"] == "live"
    assert snapshot["price_usd"] == 1.23
    assert snapshot["provider"] == "okx_dex_ws"


def test_live_market_update_uses_product_key_not_concrete_market_key() -> None:
    payload = live_market_update_payload(
        {
            **_current_row(),
            "product_target_type": "Asset",
            "product_target_id": "asset:eip155:1:erc20:0xabc",
        }
    )

    assert payload["target_type"] == "Asset"
    assert payload["target_id"] == "asset:eip155:1:erc20:0xabc"
    assert payload["market"]["decision_latest"]["target_type"] == "Asset"
    assert payload["market"]["decision_latest"]["target_id"] == "asset:eip155:1:erc20:0xabc"


def test_missing_live_market_snapshot_is_explicit() -> None:
    snapshot = live_market_snapshot(
        None,
        target_type="CexToken",
        target_id="cex_token:BTC",
        now_ms=1_700_000_000_100,
    )

    assert snapshot["status"] == "missing"
    assert snapshot["price_usd"] is None


def _current_row() -> dict[str, object]:
    return {
        "target_type": "chain_token",
        "target_id": "eip155:1:0xabc",
        "tick_observed_at_ms": 1_700_000_000_000,
        "tick_id": "tick-1",
        "source_provider": "okx_dex_ws",
        "pricefeed_id": None,
        "price_usd": Decimal("1.23"),
        "market_cap_usd": Decimal("1000"),
        "liquidity_usd": Decimal("500"),
        "holders": 10,
        "volume_24h_usd": Decimal("100"),
        "open_interest_usd": None,
        "updated_at_ms": 1_700_000_000_001,
    }
