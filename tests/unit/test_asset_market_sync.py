from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.providers import CexTicker
from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import sync_cex_routes


def test_sync_cex_routes_writes_instruments_and_feeds_without_price_observations():
    registry = _Registry()
    result = sync_cex_routes(
        registry=registry,
        cex_market=_CexMarket(),
        inst_types=("spot",),
        observed_at_ms=1_778_000_000_000,
    )

    assert result == {
        "inst_types": ["SPOT"],
        "cex_tokens_written": 1,
        "pricefeeds_written": 1,
        "affected_lookup_keys": ["cex_token:BTC", "project_symbol:BTC", "symbol:BTC"],
    }
    assert registry.pricefeeds == [
        {
            "feed_type": "cex_spot",
            "provider": "okx",
            "subject_type": "CexToken",
            "subject_id": "cex_token:BTC",
            "native_market_id": "BTC-USDT",
            "base_cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
    ]
    assert registry.conn.commits == 1


class _CexMarket:
    def tickers(self, *, inst_type: str):
        assert inst_type == "SPOT"
        return [
            CexTicker(
                inst_id="BTC-USDT",
                inst_type="SPOT",
                last_price=70_000.0,
                volume_24h=123.0,
                open_interest=None,
                raw={"instId": "BTC-USDT"},
            )
        ]


class _Registry:
    def __init__(self) -> None:
        self.conn = _Conn()
        self.pricefeeds = []

    def upsert_cex_token(self, **kwargs):
        assert kwargs == {
            "base_symbol": "BTC",
            "project_id": None,
            "source": "okx_cex",
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
        return {"cex_token_id": "cex_token:BTC"}

    def upsert_pricefeed(self, **kwargs):
        self.pricefeeds.append(kwargs)
        return {"pricefeed_id": "pricefeed:cex:okx:spot:BTC-USDT"}


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
