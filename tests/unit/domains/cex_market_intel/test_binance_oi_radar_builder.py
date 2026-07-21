from __future__ import annotations

import pytest

from parallax.domains.cex_market_intel.providers import (
    CexFundingPremium,
    CexOiTicker24h,
    CexOpenInterestPoint,
)
from parallax.domains.cex_market_intel.services.binance_oi_radar_builder import (
    build_binance_oi_radar_rows,
)


def test_build_binance_oi_radar_rows_scores_and_ranks_binance_universe():
    rows = build_binance_oi_radar_rows(
        universe=[
            {
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ],
        client=_Client(),
        now_ms=1_778_000_000_000,
        period="5m",
        limit=10,
    )

    assert rows["processed"] == 1
    assert rows["failed"] == 0
    assert rows["rows"][0]["rank"] == 1
    assert rows["rows"][0]["target_id"] == "binance:BTCUSDT"
    assert rows["rows"][0]["open_interest_usd"] == 1100.0
    assert rows["rows"][0]["open_interest_change_pct_1h"] == 10.0
    assert rows["rows"][0]["funding_rate"] == 0.0001
    assert rows["rows"][0]["score"] > 0
    assert rows["rows"][0]["observed_at_source"] == "provider"


def test_build_binance_oi_radar_rows_accepts_tuple_provider_sequences():
    rows = build_binance_oi_radar_rows(
        universe=[
            {
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ],
        client=_TupleClient(),
        now_ms=1_778_000_000_000,
        period="5m",
        limit=10,
    )

    row = rows["rows"][0]
    assert row["volume_24h_usd"] == 10_000_000.0
    assert row["funding_rate"] == 0.0001
    assert row["mark_price"] == 101.0


def test_build_binance_oi_radar_rows_marks_now_ms_fallback_observed_timestamp_as_computed():
    rows = build_binance_oi_radar_rows(
        universe=[
            {
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ],
        client=_NoObservedAtClient(),
        now_ms=1_778_000_000_000,
        period="5m",
        limit=10,
    )

    row = rows["rows"][0]
    assert row["observed_at_ms"] == 1_778_000_000_000
    assert row["observed_at_source"] == "computed"


def test_build_binance_oi_radar_rows_rejects_malformed_provider_history_points():
    try:
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                }
            ],
            client=_MalformedHistoryClient(),
            now_ms=1_778_000_000_000,
            period="5m",
            limit=10,
        )
    except ValueError as exc:
        assert str(exc) == "cex_oi_radar_provider_contract_required:open_interest_value"
    else:
        raise AssertionError("malformed Binance open-interest DTO must not be converted to empty metrics")


def test_build_binance_oi_radar_rows_rejects_malformed_provider_ticker_metrics():
    try:
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                }
            ],
            client=_MalformedTickerClient(),
            now_ms=1_778_000_000_000,
            period="5m",
            limit=10,
        )
    except ValueError as exc:
        assert str(exc) == "cex_oi_radar_provider_contract_required:quote_volume_24h"
    else:
        raise AssertionError("malformed Binance ticker DTO must not be converted to empty metrics")


@pytest.mark.parametrize(
    ("client_kind", "field"),
    [
        pytest.param("ticker", "quote_volume_24h", id="ticker-string"),
        pytest.param("funding", "last_funding_rate", id="funding-nan"),
        pytest.param("history", "observed_at_ms", id="history-timestamp-string"),
    ],
)
def test_build_binance_oi_radar_rows_rejects_invalid_provider_numeric_values(client_kind: str, field: str):
    client = {
        "ticker": _InvalidNumericTickerClient,
        "funding": _InvalidNumericFundingClient,
        "history": _InvalidNumericHistoryClient,
    }[client_kind]()
    with pytest.raises(ValueError, match=rf"cex_oi_radar_provider_contract_required:{field}"):
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                }
            ],
            client=client,
            now_ms=1_778_000_000_000,
            period="5m",
            limit=10,
        )


def test_build_binance_oi_radar_rows_preserves_zero_mark_price_from_premium():
    rows = build_binance_oi_radar_rows(
        universe=[
            {
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ],
        client=_ZeroMarkPriceClient(),
        now_ms=1_778_000_000_000,
        period="5m",
        limit=10,
    )

    assert rows["rows"][0]["mark_price"] == 0.0


def test_build_binance_oi_radar_rows_requires_native_market_id_before_provider_io():
    client = _CallRecordingClient()

    try:
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:broken",
                    "native_market_id": "",
                    "base_symbol": "BTC",
                }
            ],
            client=client,
            now_ms=1_778_000_000_000,
            period="5m",
            limit=10,
        )
    except ValueError as exc:
        assert str(exc) == "cex_oi_radar_identity_required:native_market_id"
    else:
        raise AssertionError("missing Binance native market id must fail before provider calls")

    assert client.calls == []


def test_build_binance_oi_radar_rows_requires_base_symbol_before_provider_io():
    client = _CallRecordingClient()

    try:
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:broken",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "",
                }
            ],
            client=client,
            now_ms=1_778_000_000_000,
            period="5m",
            limit=10,
        )
    except ValueError as exc:
        assert str(exc) == "cex_oi_radar_identity_required:base_symbol"
    else:
        raise AssertionError("missing Binance base symbol must fail before provider calls")

    assert client.calls == []


@pytest.mark.parametrize(
    "limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_build_binance_oi_radar_rows_requires_positive_limit_before_provider_io(limit: object):
    client = _CallRecordingClient()

    with pytest.raises(ValueError, match="cex_oi_radar_limit_required"):
        build_binance_oi_radar_rows(
            universe=[
                {
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                }
            ],
            client=client,
            now_ms=1_778_000_000_000,
            period="5m",
            limit=limit,  # type: ignore[arg-type]
        )

    assert client.calls == []


class _Client:
    def list_24h_tickers(self, symbol=None):
        assert symbol is None
        return [
            CexOiTicker24h(
                symbol="BTCUSDT",
                last_price=100.0,
                quote_volume_24h=10_000_000.0,
                price_change_pct_24h=1.0,
            )
        ]

    def list_funding_premium(self, symbol=None):
        assert symbol is None
        return [CexFundingPremium(symbol="BTCUSDT", mark_price=101.0, last_funding_rate=0.0001)]

    def list_open_interest_history(self, symbol, period, limit):
        assert symbol == "BTCUSDT"
        assert period == "5m"
        assert limit == 2
        return [
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1000.0, observed_at_ms=1),
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1100.0, observed_at_ms=2),
        ]


class _TupleClient(_Client):
    def list_24h_tickers(self, symbol=None):
        return tuple(super().list_24h_tickers(symbol=symbol))

    def list_funding_premium(self, symbol=None):
        return tuple(super().list_funding_premium(symbol=symbol))


class _NoObservedAtClient(_Client):
    def list_open_interest_history(self, symbol, period, limit):
        assert symbol == "BTCUSDT"
        assert period == "5m"
        assert limit == 2
        return [
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1000.0, observed_at_ms=None),
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1100.0, observed_at_ms=None),
        ]


class _MalformedOpenInterestPoint:
    observed_at_ms = 2


class _MalformedHistoryClient(_Client):
    def list_open_interest_history(self, symbol, period, limit):
        assert symbol == "BTCUSDT"
        assert period == "5m"
        assert limit == 2
        return [
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1000.0, observed_at_ms=1),
            _MalformedOpenInterestPoint(),
        ]


class _MalformedTicker:
    symbol = "BTCUSDT"
    last_price = 100.0
    price_change_pct_24h = 1.0


class _MalformedTickerClient(_Client):
    def list_24h_tickers(self, symbol=None):
        assert symbol is None
        return [_MalformedTicker()]


class _InvalidNumericTickerClient(_Client):
    def list_24h_tickers(self, symbol=None):
        assert symbol is None
        return [
            CexOiTicker24h(
                symbol="BTCUSDT",
                last_price=100.0,
                quote_volume_24h="not-a-number",  # type: ignore[arg-type]
                price_change_pct_24h=1.0,
            )
        ]


class _InvalidNumericFundingClient(_Client):
    def list_funding_premium(self, symbol=None):
        assert symbol is None
        return [CexFundingPremium(symbol="BTCUSDT", mark_price=101.0, last_funding_rate=float("nan"))]


class _InvalidNumericHistoryClient(_Client):
    def list_open_interest_history(self, symbol, period, limit):
        assert symbol == "BTCUSDT"
        assert period == "5m"
        assert limit == 2
        return [
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1000.0, observed_at_ms=1),
            CexOpenInterestPoint(
                symbol=symbol,
                open_interest_value=1100.0,
                observed_at_ms="bad",  # type: ignore[arg-type]
            ),
        ]


class _ZeroMarkPriceClient(_Client):
    def list_funding_premium(self, symbol=None):
        assert symbol is None
        return [CexFundingPremium(symbol="BTCUSDT", mark_price=0.0, last_funding_rate=0.0001)]


class _CallRecordingClient(_Client):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_24h_tickers(self, symbol=None):
        self.calls.append("list_24h_tickers")
        return super().list_24h_tickers(symbol=symbol)

    def list_funding_premium(self, symbol=None):
        self.calls.append("list_funding_premium")
        return super().list_funding_premium(symbol=symbol)

    def list_open_interest_history(self, symbol, period, limit):
        self.calls.append("list_open_interest_history")
        return super().list_open_interest_history(symbol, period, limit)
