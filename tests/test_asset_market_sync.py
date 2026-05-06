from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxCexInstrument, OkxCexTicker, OkxDexTokenPrice
from gmgn_twitter_intel.pipeline.asset_market_sync import sync_okx_cex_universe, sync_okx_dex_prices
from gmgn_twitter_intel.pipeline.asset_market_sync_worker import AssetMarketSyncWorker


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
            "market_cap_usd": None,
            "liquidity_usd": None,
            "holders": None,
        }
    ]


def test_asset_market_sync_worker_runs_one_cex_sync_cycle():
    assets = FakeAssets()
    client = FakeOkxCexClient()
    session = FakeRepositorySession(assets)
    worker = AssetMarketSyncWorker(
        client=client,
        repository_session=lambda: session,
        inst_types=("SPOT",),
        interval_seconds=300,
    )

    result = worker.sync_once(now_ms=1_700_000_000_000)

    assert result["market_snapshots_written"] == 1
    assert worker.last_result is None
    assert assets.market_snapshots[0]["price_usd"] == 69000.0


def test_sync_okx_dex_prices_refreshes_active_dex_venues_in_batches():
    assets = FakeAssets()
    assets.dex_refresh_rows = [
        {
            "asset_id": "asset:dex:bsc:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "venue_id": "venue:dex:bsc:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain": "bsc",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
            "market_cap_usd": 22_000.0,
            "liquidity_usd": 9_000.0,
            "holders": 123,
        }
    ]
    client = FakeOkxDexPriceClient()

    result = sync_okx_dex_prices(
        assets=assets,
        client=client,
        observed_at_ms=1_778_085_100_000,
        stale_after_ms=300_000,
        limit=100,
    )

    assert result == {"venues_scanned": 1, "price_requests": 1, "market_snapshots_written": 1}
    assert client.price_requests == [
        [{"chainIndex": "56", "tokenContractAddress": "0x8f32420f2e3728c49399b00dd0a796602d984444"}]
    ]
    assert assets.market_snapshots[-1] == {
        "asset_id": "asset:dex:bsc:0x8f32420f2e3728c49399b00dd0a796602d984444",
        "venue_id": "venue:dex:bsc:0x8f32420f2e3728c49399b00dd0a796602d984444",
        "provider": "okx_dex_price",
        "price_usd": 0.00002237,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "market_cap_usd": 22_000.0,
        "liquidity_usd": 9_000.0,
        "holders": 123,
    }


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


class FakeOkxDexPriceClient:
    def __init__(self):
        self.price_requests = []

    def token_prices(self, tokens):
        self.price_requests.append(tokens)
        return [
            OkxDexTokenPrice(
                chain_index="56",
                address="0x8f32420f2e3728c49399b00dd0a796602d984444",
                observed_at_ms=1_778_085_000_000,
                price_usd=0.00002237,
                raw={"price": "0.00002237"},
            )
        ]


class FakeAssets:
    def __init__(self):
        self.instruments = []
        self.market_snapshots = []
        self.dex_refresh_rows = []
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
                "market_cap_usd": kwargs.get("market_cap_usd"),
                "liquidity_usd": kwargs.get("liquidity_usd"),
                "holders": kwargs.get("holders"),
            }
        )
        return kwargs

    def dex_venues_needing_market_refresh(self, *, stale_before_ms, limit):
        return self.dex_refresh_rows[:limit]


class FakeAssetResolutionResult:
    def __init__(self, *, asset, venue):
        self.asset = asset
        self.venue = venue


class FakeConn:
    def commit(self):
        return None


class FakeRepositorySession:
    def __init__(self, assets):
        self.assets = assets

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None
