from inspect import signature

import pytest

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


def test_stocks_radar_service_constructor_has_no_quote_provider_parameter():
    assert "quote_provider" not in signature(StocksRadarService).parameters


def test_stocks_radar_returns_unavailable_quote_read_model_state_without_provider():
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

    stock_rows = StaticStockRows(rows)

    data = StocksRadarService(conn=FakeConn([]), stock_rows_query=stock_rows).stocks_radar(
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
    assert data["query"]["window_start_ms"] == 1_778_596_500_000
    assert {row["quote"]["status"] for row in data["rows"]} == {"unavailable"}
    assert {row["quote"]["error"] for row in data["rows"]} == {"quote_read_model_unavailable"}
    assert {row["quote"]["provider"] for row in data["rows"]} == {None}
    assert {row["row_health"][0] for row in data["rows"]} == {"quote_unavailable"}
    assert stock_rows.calls[-1]["limit"] == 6


def test_stocks_radar_allows_zero_limit_as_empty_result() -> None:
    stock_rows = StaticStockRows([{"target_id": "market_instrument:us_equity:BTC", "symbol": "BTC"}])

    data = StocksRadarService(conn=FakeConn([]), stock_rows_query=stock_rows).stocks_radar(
        window="1h",
        limit=0,
        scope="all",
        now_ms=1_778_600_100_000,
    )

    assert data["rows"] == []
    assert data["health"]["returned_count"] == 0
    assert stock_rows.calls[-1]["limit"] == 0


@pytest.mark.parametrize("limit", [-1, True, "6"])
def test_stocks_radar_rejects_malformed_limit_before_query(limit: object) -> None:
    stock_rows = StaticStockRows([])

    with pytest.raises(ValueError, match="stocks_radar_limit_required"):
        StocksRadarService(conn=FakeConn([]), stock_rows_query=stock_rows).stocks_radar(
            window="1h",
            limit=limit,  # type: ignore[arg-type]
            scope="all",
            now_ms=1_778_600_100_000,
        )

    assert stock_rows.calls == []


class StaticStockRows:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def stock_rows(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.rows[: kwargs["limit"]]
