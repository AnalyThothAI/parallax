from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import sync_binance_usdt_perp_routes


def test_sync_binance_usdt_perp_routes_writes_instruments_and_feeds_without_market_ticks():
    registry = _Registry()
    result = sync_binance_usdt_perp_routes(
        registry=registry,
        client=_BinanceClient(),
        observed_at_ms=1_778_000_000_000,
        dry_run=False,
        execute=True,
    )

    assert result["mode"] == "execute"
    assert result["provider"] == "binance"
    assert result["feed_type"] == "cex_swap"
    assert result["quote_symbol"] == "USDT"
    assert result["contract_type"] == "PERPETUAL"
    assert result["binance_usdt_perp_seen"] == 1
    assert result["cex_tokens_to_insert"] == 1
    assert result["cex_tokens_to_delete"] == 2
    assert result["pricefeeds_to_insert"] == 1
    assert result["old_okx_cex_rows_to_delete"] == 3
    assert result["cex_tokens_written"] == 1
    assert result["pricefeeds_written"] == 1
    assert result["affected_lookup_keys"] == ["cex_token:BTC", "project_symbol:BTC", "symbol:BTC"]
    assert isinstance(result["duration_ms"], int)
    assert registry.pricefeeds == [
        {
            "feed_type": "cex_swap",
            "provider": "binance",
            "subject_type": "CexToken",
            "subject_id": "cex_token:BTC",
            "native_market_id": "BTCUSDT",
            "base_cex_token_id": "cex_token:BTC",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "multiplier": None,
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
    ]
    assert registry.conn.commits == 1


def test_sync_binance_usdt_perp_routes_dry_run_does_not_write_or_commit():
    registry = _Registry()
    result = sync_binance_usdt_perp_routes(
        registry=registry,
        client=_BinanceClient(),
        observed_at_ms=1_778_000_000_000,
        dry_run=True,
        execute=False,
    )

    assert result["mode"] == "dry_run"
    assert result["binance_usdt_perp_seen"] == 1
    assert result["cex_tokens_written"] == 0
    assert result["pricefeeds_written"] == 0
    assert registry.pricefeeds == []
    assert registry.conn.commits == 0


class _BinanceClient:
    def usdt_perpetual_routes(self):
        return [
            SimpleNamespace(
                native_market_id="BTCUSDT",
                base_symbol="BTC",
                quote_symbol="USDT",
                multiplier=None,
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
            "source": "binance_cex",
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
        return {"cex_token_id": "cex_token:BTC"}

    def upsert_pricefeed(self, **kwargs):
        self.pricefeeds.append(kwargs)
        return {"pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT"}

    def binance_usdt_perp_sync_plan_counts(self, *, base_symbols, native_market_ids):
        assert base_symbols == ["BTC"]
        assert native_market_ids == ["BTCUSDT"]
        return {
            "cex_tokens_to_insert": 1,
            "cex_tokens_to_delete": 2,
            "pricefeeds_to_insert": 1,
            "old_okx_cex_rows_to_delete": 3,
        }


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
