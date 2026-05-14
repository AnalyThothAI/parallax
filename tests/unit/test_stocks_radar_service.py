from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.read_models.stocks_radar_service import StocksRadarService


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.params = None

    def execute(self, _sql, params):
        self.params = params
        return FakeResult(self.rows)


class FakeQuoteProvider:
    def quote(self, symbol: str):
        if symbol == "RKLB":
            raise RuntimeError("quote failed")
        return {
            "price": 100,
            "reference_close_price": 95,
            "asof": "2026-05-12T14:30:00Z",
            "provider": "test",
            "provider_symbol": symbol,
            "latency_class": "delayed_15m",
        }


def test_stocks_radar_normalizes_quotes_and_keeps_failed_quote_rows():
    conn = FakeConn(
        [
            {
                "target_id": "market_instrument:us_equity:AAPL",
                "symbol": "AAPL",
                "security_name": "Apple Inc.",
                "exchange": "NASDAQ",
                "instrument_type": "equity",
                "mentions": 2,
                "unique_authors": 2,
                "watched_mentions": 1,
                "latest_seen_ms": 1_778_600_000_000,
                "latest_event_id": "event-aapl-2",
                "latest_author_handle": "toly",
                "latest_text": "$AAPL breakout",
                "source_event_ids": ["event-aapl-2", "event-aapl-1"],
            },
            {
                "target_id": "market_instrument:us_equity:RKLB",
                "symbol": "RKLB",
                "security_name": "Rocket Lab USA, Inc.",
                "exchange": "NASDAQ",
                "instrument_type": "equity",
                "mentions": 1,
                "unique_authors": 1,
                "watched_mentions": 0,
                "latest_seen_ms": 1_778_599_000_000,
                "latest_event_id": "event-rklb-1",
                "latest_author_handle": "elonmusk",
                "latest_text": "$RKLB launch cadence",
                "source_event_ids": ["event-rklb-1"],
            },
        ]
    )

    data = StocksRadarService(conn=conn, quote_provider=FakeQuoteProvider()).stocks_radar(
        window="1h",
        limit=10,
        scope="all",
        now_ms=1_778_600_100_000,
    )

    assert data["health"] == {
        "returned_count": 2,
        "quote_ready_count": 1,
        "quote_unavailable_count": 1,
    }
    assert data["query"]["window_start_ms"] == 1_778_596_500_000
    assert data["rows"][0]["target"]["target_type"] == "MarketInstrument"
    assert data["rows"][0]["quote"]["status"] == "ready"
    assert data["rows"][0]["quote"]["change_pct"] == (100 - 95) / 95
    assert data["rows"][1]["quote"]["status"] == "unavailable"
    assert data["rows"][1]["row_health"] == ["quote_unavailable"]
