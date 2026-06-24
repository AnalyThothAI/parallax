from __future__ import annotations

import pytest

from parallax.domains.cex_market_intel.repositories.cex_derivative_series_repository import (
    CexDerivativeSeriesRepository,
    _series_id,
)


def test_upsert_open_interest_points_requires_connection_transaction_before_sql_when_committing() -> None:
    conn = _NoTransactionConn()

    with pytest.raises(TypeError, match="cex_derivative_series_transaction_required"):
        CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
            provider="binance",
            exchange="binance",
            native_market_id="BTCUSDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            period="5m",
            points=[{"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0}],
        )

    assert conn.sql_calls == []


def test_upsert_open_interest_points_uses_one_transaction_when_committing() -> None:
    conn = _RecordingConn()

    written = CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
        provider="binance",
        exchange="binance",
        native_market_id="BTCUSDT",
        base_symbol="BTC",
        quote_symbol="USDT",
        period="5m",
        points=[
            {"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0, "raw_payload": {"openInterest": "100"}},
            {"observed_at_ms": 1_778_000_300_000, "value_usd": 120.0, "raw_payload": {"openInterest": "120"}},
        ],
    )

    assert written == 2
    assert len(conn.sql_calls) == 2
    assert conn.commits == 1
    assert conn.sql_depths == [1, 1]


def test_upsert_open_interest_points_commit_false_is_caller_owned() -> None:
    conn = _RecordingConn()

    written = CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
        provider="binance",
        exchange="binance",
        native_market_id="BTCUSDT",
        base_symbol="BTC",
        quote_symbol="USDT",
        period="5m",
        points=[{"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0, "raw_payload": {"openInterest": "100"}}],
        commit=False,
    )

    assert written == 1
    assert conn.commits == 0
    assert conn.sql_depths == [0]


def test_upsert_open_interest_points_reports_zero_for_unchanged_conflict_rows() -> None:
    conn = _RecordingConn(rowcounts=[0])

    written = CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
        provider="binance",
        exchange="binance",
        native_market_id="BTCUSDT",
        base_symbol="BTC",
        quote_symbol="USDT",
        period="5m",
        points=[{"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0, "raw_payload": {"openInterest": "100"}}],
        commit=False,
    )

    assert written == 0
    assert "WHERE cex_derivative_series.value_numeric IS DISTINCT FROM excluded.value_numeric" in conn.sql_calls[0]


@pytest.mark.parametrize(
    ("cursor_kind", "match"),
    (
        ("missing", "cex_derivative_series_rowcount_required"),
        ("string", "cex_derivative_series_rowcount_invalid"),
        ("bool", "cex_derivative_series_rowcount_invalid"),
        ("negative", "cex_derivative_series_rowcount_invalid"),
    ),
)
def test_upsert_open_interest_points_requires_real_cursor_rowcount(cursor_kind: str, match: str) -> None:
    rowcounts: dict[str, object] = {"string": "unknown", "bool": True, "negative": -1}
    cursor = object() if cursor_kind == "missing" else _Cursor(rowcount=rowcounts[cursor_kind])
    conn = _CursorConn(cursor=cursor)

    with pytest.raises(TypeError, match=match):
        CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
            provider="binance",
            exchange="binance",
            native_market_id="BTCUSDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            period="5m",
            points=[
                {
                    "observed_at_ms": 1_778_000_000_000,
                    "value_usd": 100.0,
                    "raw_payload": {"openInterest": "100"},
                }
            ],
            commit=False,
        )

    assert len(conn.sql_calls) == 1


@pytest.mark.parametrize(
    ("point", "match"),
    (
        ({"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0}, "cex_derivative_series_raw_payload_required"),
        (
            {"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0, "raw_payload": None},
            "cex_derivative_series_raw_payload_required",
        ),
        (
            {"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0, "raw_payload": []},
            "cex_derivative_series_raw_payload_invalid",
        ),
    ),
)
def test_upsert_open_interest_points_requires_formal_raw_payload_before_sql(
    point: dict[str, object], match: str
) -> None:
    conn = _RecordingConn()

    with pytest.raises(ValueError, match=match):
        CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
            provider="binance",
            exchange="binance",
            native_market_id="BTCUSDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            period="5m",
            points=[point],
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("provider", "exchange", "native_market_id", "period"))
def test_upsert_open_interest_points_requires_formal_series_identity_before_sql(field: str) -> None:
    conn = _RecordingConn()
    params = {
        "provider": "binance",
        "exchange": "binance",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "period": "5m",
    }
    params[field] = " "

    with pytest.raises(ValueError, match=f"cex_derivative_series_identity_required:{field}"):
        CexDerivativeSeriesRepository(conn).upsert_open_interest_points(
            **params,
            points=[{"observed_at_ms": 1_778_000_000_000, "value_usd": 100.0}],
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("overrides", "field"),
    (
        ({"provider": " "}, "provider"),
        ({"native_market_id": " "}, "native_market_id"),
        ({"metric": " "}, "metric"),
        ({"period": " "}, "period"),
    ),
)
def test_series_id_requires_formal_identity_without_empty_hash_segments(overrides: dict[str, str], field: str) -> None:
    params = {
        "provider": "binance",
        "native_market_id": "BTCUSDT",
        "metric": "open_interest",
        "period": "5m",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=f"cex_derivative_series_identity_required:{field}"):
        _series_id(**params, observed_at_ms=1_778_000_000_000)


class _RecordingConn:
    def __init__(self, *, rowcounts: list[int] | None = None) -> None:
        self.sql_calls: list[str] = []
        self.sql_depths: list[int] = []
        self.commits = 0
        self.rollbacks = 0
        self.transaction_depth = 0
        self._rowcounts = list(rowcounts or [])

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        self.sql_depths.append(self.transaction_depth)
        rowcount = self._rowcounts.pop(0) if self._rowcounts else 1
        return _Cursor(rowcount=rowcount)

    def transaction(self):
        return _Transaction(self)


class _NoTransactionConn(_RecordingConn):
    transaction = None


class _Cursor:
    def __init__(self, *, rowcount: object) -> None:
        self.rowcount = rowcount


class _CursorConn(_RecordingConn):
    def __init__(self, *, cursor: object) -> None:
        super().__init__()
        self.cursor = cursor

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        self.sql_depths.append(self.transaction_depth)
        return self.cursor


class _Transaction:
    def __init__(self, conn: _RecordingConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args):
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.commits += 1
        else:
            self.conn.rollbacks += 1
        return False
