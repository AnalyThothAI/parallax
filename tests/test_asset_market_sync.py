from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxCexInstrument, OkxCexTicker
from gmgn_twitter_intel.pipeline.asset_market_sync import sync_okx_cex_universe


def test_sync_okx_cex_universe_writes_instruments_and_market_snapshots():
    assets = FakeAssets()
    client = FakeOkxCexClient()

    result = sync_okx_cex_universe(
        assets=assets,
        client=client,
        inst_types=("SPOT",),
        observed_at_ms=1_700_000_000_000,
    )

    assert result == {"inst_types": ["SPOT"], "venues_written": 1, "market_snapshots_written": 1}
    assert assets.instruments == [
        {
            "exchange": "okx",
            "inst_type": "SPOT",
            "inst_id": "BTC-USDT",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
        }
    ]
    assert assets.market_snapshots == [
        {
            "asset_id": "asset:cex:BTC",
            "venue_id": "venue:cex:okx:SPOT:BTC-USDT",
            "provider": "okx_cex",
            "price_usd": 69000.0,
            "volume_24h_usd": 1234567.0,
            "open_interest_usd": None,
        }
    ]


class FakeOkxCexClient:
    def instruments(self, *, inst_type):
        return [
            OkxCexInstrument(
                inst_id="BTC-USDT",
                inst_type=inst_type,
                base_symbol="BTC",
                quote_symbol="USDT",
                state="live",
                raw={"instId": "BTC-USDT"},
            )
        ]

    def tickers(self, *, inst_type):
        return [
            OkxCexTicker(
                inst_id="BTC-USDT",
                inst_type=inst_type,
                last_price=69000.0,
                volume_24h=1234567.0,
                open_interest=None,
                raw={"instId": "BTC-USDT"},
            )
        ]


class FakeAssets:
    def __init__(self):
        self.instruments = []
        self.market_snapshots = []
        self.conn = FakeConn()

    def upsert_cex_instrument(
        self,
        *,
        exchange,
        inst_type,
        inst_id,
        base_symbol,
        quote_symbol,
        observed_at_ms,
        source_payload_hash=None,
        commit=False,
    ):
        self.instruments.append(
            {
                "exchange": exchange,
                "inst_type": inst_type,
                "inst_id": inst_id,
                "base_symbol": base_symbol,
                "quote_symbol": quote_symbol,
            }
        )
        return FakeAssetResolutionResult(
            asset={"asset_id": f"asset:cex:{base_symbol}"},
            venue={"venue_id": f"venue:cex:okx:{inst_type}:{inst_id}"},
        )

    def venue_for_cex_instrument(self, *, exchange, inst_type, inst_id):
        return {
            "asset_id": "asset:cex:BTC",
            "venue_id": f"venue:cex:{exchange}:{inst_type}:{inst_id}",
        }

    def insert_market_snapshot(self, **kwargs):
        self.market_snapshots.append(
            {
                "asset_id": kwargs["asset_id"],
                "venue_id": kwargs["venue_id"],
                "provider": kwargs["provider"],
                "price_usd": kwargs["price_usd"],
                "volume_24h_usd": kwargs["volume_24h_usd"],
                "open_interest_usd": kwargs["open_interest_usd"],
            }
        )
        return kwargs


class FakeAssetResolutionResult:
    def __init__(self, *, asset, venue):
        self.asset = asset
        self.venue = venue


class FakeConn:
    def commit(self):
        return None
