import inspect

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


def test_stocks_radar_is_provider_free_and_marks_quotes_unavailable():
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

    data = StocksRadarService(conn=conn).stocks_radar(
        window="1h",
        limit=10,
        scope="all",
        now_ms=1_778_600_100_000,
    )

    assert data["health"] == {
        "returned_count": 2,
        "quote_ready_count": 0,
        "quote_unavailable_count": 2,
    }
    assert data["query"]["window_start_ms"] == 1_778_596_500_000
    assert data["rows"][0]["target"]["target_type"] == "MarketInstrument"
    assert data["rows"][0]["quote"]["status"] == "unavailable"
    assert data["rows"][0]["quote"]["error"] == "read_model_unavailable"
    assert data["rows"][1]["quote"]["status"] == "unavailable"
    assert data["rows"][1]["row_health"] == ["quote_unavailable"]


def test_stocks_radar_constructor_has_no_legacy_quote_provider_slot():
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

    assert "quote_provider" not in inspect.signature(StocksRadarService).parameters
    assert data["health"] == {
        "returned_count": 6,
        "quote_ready_count": 0,
        "quote_unavailable_count": 6,
    }
    assert {row["quote"]["error"] for row in data["rows"]} == {"read_model_unavailable"}


class StaticStockRows:
    def __init__(self, rows):
        self.rows = rows

    def stock_rows(self, **_kwargs):
        return self.rows
