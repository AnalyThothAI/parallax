from __future__ import annotations

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
        registry=registry,
        client=_Client(
            [
                NasdaqTraderSymbol(
                    symbol="AAOI",
                    exchange="NASDAQ",
                    security_name="Applied Optoelectronics, Inc. Common Stock",
                    instrument_type="equity",
                    raw_payload={"Symbol": "AAOI"},
                )
            ]
        ),
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
            "commit": False,
        }
    ]
    assert registry.deactivate_call == {
        "source": "nasdaq_trader",
        "active_symbols": {"AAOI"},
        "observed_at_ms": 1_778_000_000_000,
        "commit": False,
    }
    assert registry.conn.commits == 1


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def symbols(self):
        return list(self.rows)


class _Registry:
    def __init__(self) -> None:
        self.conn = _Conn()
        self.upserts = []
        self.deactivate_call = None

    def upsert_us_equity_symbol(self, **kwargs):
        self.upserts.append(kwargs)
        return {"symbol": kwargs["symbol"]}

    def deactivate_missing_us_equity_symbols(self, **kwargs):
        self.deactivate_call = kwargs
        return 2


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
