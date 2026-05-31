from parallax.domains.token_intel.read_models.stocks_radar_service import StocksRadarService


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


def test_stocks_radar_uses_quote_provider_and_keeps_per_row_failures():
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
    quote_provider = FakeQuoteProvider(
        {
            "AAPL": {
                "status": "ready",
                "price": 200.0,
                "reference_close_price": 190.0,
                "change_pct": 0.0526315789,
                "asof": "2026-05-20",
                "provider": "yahoo",
                "provider_symbol": "AAPL",
                "latency_class": "daily",
                "freshness_class": "daily",
                "error": None,
            },
            "RKLB": {
                "status": "unavailable",
                "price": None,
                "reference_close_price": None,
                "change_pct": None,
                "asof": None,
                "provider": "yahoo",
                "provider_symbol": "RKLB",
                "latency_class": "daily",
                "freshness_class": "daily",
                "error": "no_data",
            },
        }
    )

    data = StocksRadarService(conn=conn, quote_provider=quote_provider).stocks_radar(
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
    assert data["rows"][0]["quote"]["provider"] == "yahoo"
    assert data["rows"][0]["row_health"] == []
    assert data["rows"][1]["quote"]["status"] == "unavailable"
    assert data["rows"][1]["quote"]["error"] == "no_data"
    assert data["rows"][1]["row_health"] == ["quote_unavailable"]
    assert quote_provider.calls == ["AAPL", "RKLB"]


def test_stocks_radar_marks_quotes_unavailable_when_provider_is_missing():
    rows = [
        {
            "target_id": f"market_instrument:us_equity:SYM{index}",
            "symbol": f"SYM{index}",
            "security_name": f"Symbol {index}",
            "exchange": "NASDAQ",
            "instrument_type": "equity",
            "mentions": 1,
            "unique_authors": 1,
            "watched_mentions": 0,
            "latest_seen_ms": 1_778_600_000_000,
            "latest_event_id": f"event-{index}",
            "latest_author_handle": "toly",
            "latest_text": f"$SYM{index}",
            "source_event_ids": [f"event-{index}"],
        }
        for index in range(6)
    ]

    data = StocksRadarService(conn=FakeConn([]), stock_rows_query=StaticStockRows(rows)).stocks_radar(
        window="1h",
        limit=6,
        scope="all",
        now_ms=1_778_600_100_000,
    )

    assert data["health"] == {
        "returned_count": 6,
        "quote_ready_count": 0,
        "quote_unavailable_count": 6,
    }
    assert {row["quote"]["error"] for row in data["rows"]} == {"quote_provider_unavailable"}


class FakeQuoteProvider:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = []

    def quote(self, symbol):
        self.calls.append(symbol)
        return self.quotes[symbol]


class StaticStockRows:
    def __init__(self, rows):
        self.rows = rows

    def stock_rows(self, **_kwargs):
        return self.rows
