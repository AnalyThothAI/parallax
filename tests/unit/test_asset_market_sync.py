from __future__ import annotations

from types import SimpleNamespace

import pytest

from parallax.domains.asset_market.services.asset_market_sync import BinanceUsdtPerpRoute, sync_binance_usdt_perp_routes


def test_sync_binance_usdt_perp_routes_writes_instruments_and_feeds_without_market_ticks():
    registry = _Registry()
    result = sync_binance_usdt_perp_routes(
        registry=registry,
        routes=_binance_routes(),
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
    assert registry.conn.events == ["enter", "exit"]
    assert registry.conn.commits == 0


def test_sync_binance_usdt_perp_routes_dry_run_does_not_write_or_commit():
    registry = _Registry()
    result = sync_binance_usdt_perp_routes(
        registry=registry,
        routes=_binance_routes(),
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
    assert registry.conn.events == []


def test_sync_binance_usdt_perp_routes_requires_formal_plan_count_repository_contract():
    registry = _RegistryWithoutPlanCounts()

    with pytest.raises(AttributeError, match="binance_usdt_perp_sync_plan_counts"):
        sync_binance_usdt_perp_routes(
            registry=registry,
            routes=_binance_routes(),
            observed_at_ms=1_778_000_000_000,
            dry_run=True,
            execute=False,
        )

    assert registry.conn.commits == 0
    assert registry.conn.events == []


def test_sync_binance_usdt_perp_routes_requires_transaction_before_writes():
    registry = _Registry(conn=object())

    with pytest.raises(RuntimeError, match="asset_market_sync_transaction_required"):
        sync_binance_usdt_perp_routes(
            registry=registry,
            routes=_binance_routes(),
            observed_at_ms=1_778_000_000_000,
            dry_run=False,
            execute=True,
        )

    assert registry.pricefeeds == []


def test_sync_binance_usdt_perp_routes_requires_formal_route_dto_without_object_reflection():
    registry = _Registry()

    with pytest.raises(RuntimeError, match="asset_market_sync_binance_route_contract_required"):
        sync_binance_usdt_perp_routes(
            registry=registry,
            routes=[
                SimpleNamespace(
                    native_market_id="BTCUSDT",
                    base_symbol="BTC",
                    quote_symbol="USDT",
                    multiplier=None,
                )
            ],
            observed_at_ms=1_778_000_000_000,
            dry_run=True,
            execute=False,
        )


def _binance_routes() -> list[BinanceUsdtPerpRoute]:
    return [
        BinanceUsdtPerpRoute(
            native_market_id="BTCUSDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            multiplier=None,
        )
    ]


class _Registry:
    def __init__(self, *, conn=None) -> None:
        self.conn = conn or _Conn()
        self.pricefeeds = []

    def upsert_cex_token(self, **kwargs):
        assert self.conn.transaction_depth == 1
        assert kwargs == {
            "base_symbol": "BTC",
            "source": "binance_cex",
            "observed_at_ms": 1_778_000_000_000,
            "commit": False,
        }
        return {"cex_token_id": "cex_token:BTC"}

    def upsert_pricefeed(self, **kwargs):
        assert self.conn.transaction_depth == 1
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


class _RegistryWithoutPlanCounts:
    def __init__(self) -> None:
        self.conn = _Conn()


class _Conn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_depth = 0
        self.events: list[str] = []

    def transaction(self):
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("sync_binance_usdt_perp_routes must use conn.transaction(), not conn.commit()")


class _Transaction:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        self.conn.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.events.append("rollback" if exc_type is not None else "exit")
        self.conn.transaction_depth -= 1
        return False
