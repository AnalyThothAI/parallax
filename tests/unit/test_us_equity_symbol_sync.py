from __future__ import annotations

import pytest

from parallax.domains.asset_market.services.us_equity_symbol_sync import (
    NasdaqTraderSymbol,
    parse_nasdaq_trader_symbols,
    sync_us_equity_symbols,
)


def test_parse_nasdaq_trader_symbols_reads_nasdaq_and_other_listed_files():
    nasdaq_text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAOI|Applied Optoelectronics, Inc. Common Stock|Q|N|N|100|N|N",
            "TEST|Test Issue Common Stock|Q|Y|N|100|N|N",
            "QQQ|Invesco QQQ Trust, Series 1|G|N|N|100|Y|N",
            "File Creation Time: 0512202600:00|||||||",
        ]
    )
    other_text = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "RKLB|Rocket Lab USA, Inc. Common Stock|N|RKLB|N|100|N|RKLB",
            "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
            "SKIP|Skipped Test Issue|A|SKIP|N|100|Y|SKIP",
            "File Creation Time: 0512202600:00|||||||",
        ]
    )

    rows = parse_nasdaq_trader_symbols(nasdaq_listed_text=nasdaq_text, other_listed_text=other_text)

    assert rows == [
        NasdaqTraderSymbol(
            symbol="AAOI",
            exchange="NASDAQ",
            security_name="Applied Optoelectronics, Inc. Common Stock",
            instrument_type="equity",
            raw_payload={
                "Symbol": "AAOI",
                "Security Name": "Applied Optoelectronics, Inc. Common Stock",
                "Market Category": "Q",
                "Test Issue": "N",
                "Financial Status": "N",
                "Round Lot Size": "100",
                "ETF": "N",
                "NextShares": "N",
            },
        ),
        NasdaqTraderSymbol(
            symbol="QQQ",
            exchange="NASDAQ",
            security_name="Invesco QQQ Trust, Series 1",
            instrument_type="etf",
            raw_payload={
                "Symbol": "QQQ",
                "Security Name": "Invesco QQQ Trust, Series 1",
                "Market Category": "G",
                "Test Issue": "N",
                "Financial Status": "N",
                "Round Lot Size": "100",
                "ETF": "Y",
                "NextShares": "N",
            },
        ),
        NasdaqTraderSymbol(
            symbol="RKLB",
            exchange="N",
            security_name="Rocket Lab USA, Inc. Common Stock",
            instrument_type="equity",
            raw_payload={
                "ACT Symbol": "RKLB",
                "Security Name": "Rocket Lab USA, Inc. Common Stock",
                "Exchange": "N",
                "CQS Symbol": "RKLB",
                "ETF": "N",
                "Round Lot Size": "100",
                "Test Issue": "N",
                "NASDAQ Symbol": "RKLB",
            },
        ),
        NasdaqTraderSymbol(
            symbol="SPY",
            exchange="P",
            security_name="SPDR S&P 500 ETF Trust",
            instrument_type="etf",
            raw_payload={
                "ACT Symbol": "SPY",
                "Security Name": "SPDR S&P 500 ETF Trust",
                "Exchange": "P",
                "CQS Symbol": "SPY",
                "ETF": "Y",
                "Round Lot Size": "100",
                "Test Issue": "N",
                "NASDAQ Symbol": "SPY",
            },
        ),
    ]


def test_sync_us_equity_symbols_upserts_and_deactivates_missing_symbols():
    registry = _Registry()
    result = sync_us_equity_symbols(
        repos=_Repos(registry),
        symbols=[
            NasdaqTraderSymbol(
                symbol="AAOI",
                exchange="NASDAQ",
                security_name="Applied Optoelectronics, Inc. Common Stock",
                instrument_type="equity",
                raw_payload={"Symbol": "AAOI"},
            )
        ],
        observed_at_ms=1_778_000_000_000,
    )

    assert result == {
        "source": "nasdaq_trader",
        "symbols_seen": 1,
        "symbols_written": 1,
        "symbols_deactivated": 2,
        "observed_at_ms": 1_778_000_000_000,
    }
    assert registry.upserts == [
        {
            "symbol": "AAOI",
            "exchange": "NASDAQ",
            "security_name": "Applied Optoelectronics, Inc. Common Stock",
            "instrument_type": "equity",
            "source": "nasdaq_trader",
            "source_updated_at_ms": 1_778_000_000_000,
            "raw_payload": {"Symbol": "AAOI"},
            "observed_at_ms": 1_778_000_000_000,
        }
    ]
    assert registry.deactivate_call == {
        "source": "nasdaq_trader",
        "active_symbols": {"AAOI"},
        "observed_at_ms": 1_778_000_000_000,
    }
    assert registry.conn.events == ["enter", "exit"]
    assert registry.conn.commits == 0


def test_sync_us_equity_symbols_requires_transaction_before_writes():
    registry = _Registry(conn=object())

    with pytest.raises(AttributeError, match="transaction"):
        sync_us_equity_symbols(
            repos=_Repos(registry),
            symbols=[
                NasdaqTraderSymbol(
                    symbol="AAOI",
                    exchange="NASDAQ",
                    security_name="Applied Optoelectronics, Inc. Common Stock",
                    instrument_type="equity",
                    raw_payload={"Symbol": "AAOI"},
                )
            ],
            observed_at_ms=1_778_000_000_000,
        )

    assert registry.upserts == []
    assert registry.deactivate_call is None


class _Registry:
    def __init__(self, *, conn=None) -> None:
        self.conn = conn or _Conn()
        self.upserts = []
        self.deactivate_call = None

    def upsert_us_equity_symbol(self, **kwargs):
        assert self.conn.transaction_depth == 1
        self.upserts.append(kwargs)
        return {"symbol": kwargs["symbol"]}

    def deactivate_missing_us_equity_symbols(self, **kwargs):
        assert self.conn.transaction_depth == 1
        self.deactivate_call = kwargs
        return 2


class _Repos:
    def __init__(self, registry) -> None:
        self.registry = registry

    def transaction(self):
        return self.registry.conn.transaction()


class _Conn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_depth = 0
        self.events: list[str] = []

    def transaction(self):
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("sync_us_equity_symbols must use repos.transaction(), not conn.commit()")


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
