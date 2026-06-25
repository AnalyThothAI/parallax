from __future__ import annotations

import pytest

from parallax.domains.cex_market_intel.repositories.cex_oi_radar_repository import (
    CexOiRadarRepository,
    _board_payload_hash,
)


def test_cex_oi_radar_repository_reads_binance_usdt_perp_universe_only():
    conn = _RecordingConn()

    rows = CexOiRadarRepository(conn).binance_usdt_perp_universe(limit=25)

    assert rows == [{"native_market_id": "BTCUSDT"}]
    sql = conn.sql_calls[-1]
    assert "provider = 'binance'" in sql
    assert "feed_type = 'cex_swap'" in sql
    assert "quote_symbol = 'USDT'" in sql
    assert "status = 'canonical'" in sql


@pytest.mark.parametrize(
    "limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("25", id="string"),
    ],
)
def test_cex_oi_radar_repository_requires_positive_universe_limit_before_sql(limit: object):
    conn = _RecordingConn()

    with pytest.raises(ValueError, match="cex_oi_radar_universe_limit_required"):
        CexOiRadarRepository(conn).binance_usdt_perp_universe(limit=limit)  # type: ignore[arg-type]

    assert conn.sql_calls == []


def test_publish_board_upserts_current_rows_with_stable_target_identity():
    conn = _RecordingConn()
    repo = CexOiRadarRepository(conn)
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_ms": 1_778_000_000_001,
        "observed_at_source": "provider",
    }

    written = repo.publish_board(
        rows=[row],
        computed_at_ms=1_778_000_000_123,
        period="5m",
        status="success",
        notes={"detail_snapshot_count": 1},
    )

    assert written == 1
    assert conn.committed is True
    all_sql = "\n".join(conn.sql_calls)
    assert "cex_oi_radar_publication_state" in all_sql
    assert "cex_oi_radar_rows" in all_sql
    assert "cex_oi_radar_runs" not in all_sql
    assert "run_id" not in all_sql
    assert "DELETE FROM cex_oi_radar_rows" in all_sql
    assert "AND NOT (row_id = ANY(%s::text[]))" in all_sql
    assert "WHERE cex_oi_radar_rows.rank IS DISTINCT FROM excluded.rank" in all_sql

    state_params = conn.params_for("INSERT INTO cex_oi_radar_publication_state")
    assert state_params[:7] == (
        "binance:USDT:PERPETUAL:5m",
        "binance",
        "binance",
        "USDT",
        "PERPETUAL",
        "5m",
        1_778_000_000_123,
    )
    assert state_params[7:9] == (1_778_000_000_001, 1)
    assert state_params[9].startswith("sha256:")
    assert state_params[10] == "success"

    row_params = conn.params_for("INSERT INTO cex_oi_radar_rows")
    assert row_params[1:7] == ("5m", "binance", "binance", "USDT", "PERPETUAL", 1)
    assert row_params[7:12] == ("binance:BTCUSDT", "pf-btc", "BTCUSDT", "BTC", "USDT")

    second_conn = _RecordingConn()
    CexOiRadarRepository(second_conn).publish_board(
        rows=[row],
        computed_at_ms=1_778_000_999_999,
        period="5m",
        status="success",
        notes={},
    )
    assert second_conn.params_for("INSERT INTO cex_oi_radar_rows")[0] == row_params[0]


def test_publish_board_requires_connection_transaction_before_sql_when_committing():
    conn = _NoTransactionConn()
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "score": 91.5,
        "observed_at_ms": 1_778_000_000_001,
    }

    with pytest.raises(TypeError, match="cex_oi_radar_transaction_required"):
        CexOiRadarRepository(conn).publish_board(
            rows=[row],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
        )

    assert conn.sql_calls == []


def test_publish_board_requires_formal_period_identity_before_sql():
    conn = _RecordingConn()

    with pytest.raises(ValueError, match="cex_oi_radar_identity_required:period"):
        CexOiRadarRepository(conn).publish_board(
            rows=[_valid_board_row()],
            computed_at_ms=1_778_000_000_123,
            period=" ",
            status="success",
            notes={},
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("target_id", "native_market_id", "base_symbol", "quote_symbol"))
def test_publish_board_requires_formal_row_identity_before_sql(field: str):
    conn = _RecordingConn()
    row = {**_valid_board_row(), field: ""}

    with pytest.raises(ValueError, match=f"cex_oi_radar_identity_required:{field}"):
        CexOiRadarRepository(conn).publish_board(
            rows=[row],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("observed_at_ms", None, "cex_oi_radar_observation_required:observed_at_ms"),
        ("observed_at_source", "", "cex_oi_radar_observation_required:observed_at_source"),
        ("observed_at_source", "clock", "cex_oi_radar_observation_invalid:observed_at_source"),
    ),
)
def test_publish_board_requires_formal_observation_contract_before_sql(field: str, value, match: str):
    conn = _RecordingConn()
    row = {**_valid_board_row(), field: value}

    with pytest.raises(ValueError, match=match):
        CexOiRadarRepository(conn).publish_board(
            rows=[row],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("value", "match"),
    (
        (None, "cex_oi_radar_score_components_required"),
        ([], "cex_oi_radar_score_components_invalid"),
    ),
)
def test_publish_board_requires_formal_score_components_before_sql(value, match: str):
    conn = _RecordingConn()
    row = {**_valid_board_row(), "score_components": value}

    with pytest.raises(ValueError, match=match):
        CexOiRadarRepository(conn).publish_board(
            rows=[row],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
            commit=False,
        )

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("patch", "error_field"),
    (
        ({"period": " "}, "period"),
        ({"row": {"target_id": ""}}, "target_id"),
        ({"row": {"native_market_id": ""}}, "native_market_id"),
        ({"row": {"base_symbol": ""}}, "base_symbol"),
        ({"row": {"quote_symbol": ""}}, "quote_symbol"),
    ),
)
def test_board_payload_hash_requires_formal_board_identity_without_defaults(
    patch: dict[str, object],
    error_field: str,
):
    row = {**_valid_board_row(), **patch.get("row", {})}
    period = str(patch.get("period", "5m"))

    with pytest.raises(ValueError, match=f"cex_oi_radar_identity_required:{error_field}"):
        _board_payload_hash(
            rows=[row],
            period=period,
            source_frontier_ms=1_778_000_000_001,
        )


@pytest.mark.parametrize(
    ("row_patch", "match"),
    (
        ({"observed_at_ms": None}, "cex_oi_radar_observation_required:observed_at_ms"),
        ({"observed_at_source": ""}, "cex_oi_radar_observation_required:observed_at_source"),
        ({"observed_at_source": "clock"}, "cex_oi_radar_observation_invalid:observed_at_source"),
    ),
)
def test_board_payload_hash_requires_formal_observation_contract(row_patch: dict[str, object], match: str):
    row = {**_valid_board_row(), **row_patch}

    with pytest.raises(ValueError, match=match):
        _board_payload_hash(
            rows=[row],
            period="5m",
            source_frontier_ms=1_778_000_000_001,
        )


@pytest.mark.parametrize(
    ("value", "match"),
    (
        (None, "cex_oi_radar_score_components_required"),
        ([], "cex_oi_radar_score_components_invalid"),
    ),
)
def test_board_payload_hash_requires_formal_score_components(value, match: str):
    row = {**_valid_board_row(), "score_components": value}

    with pytest.raises(ValueError, match=match):
        _board_payload_hash(
            rows=[row],
            period="5m",
            source_frontier_ms=1_778_000_000_001,
        )


def test_publish_board_skips_serving_row_writes_when_payload_is_unchanged():
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_ms": 1_778_000_000_001,
        "observed_at_source": "provider",
    }
    conn = _RecordingConn(
        state={
            "board_key": "binance:USDT:PERPETUAL:5m",
            "current_payload_hash": _board_payload_hash(
                rows=[row],
                period="5m",
                source_frontier_ms=1_778_000_000_001,
            ),
        }
    )

    written = CexOiRadarRepository(conn).publish_board(
        rows=[row],
        computed_at_ms=1_778_000_999_999,
        period="5m",
        status="success",
        notes={},
    )

    assert written == 0
    assert conn.committed is True
    all_sql = "\n".join(conn.sql_calls)
    assert "SELECT current_payload_hash" in all_sql
    assert "DELETE FROM cex_oi_radar_rows" not in all_sql
    assert "INSERT INTO cex_oi_radar_rows" not in all_sql
    assert "current_published_at_ms = excluded.current_published_at_ms" not in all_sql


def test_board_payload_hash_ignores_detail_only_payload_fields():
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_ms": 1_778_000_000_001,
        "observed_at_source": "provider",
    }

    first_hash = _board_payload_hash(
        rows=[{**row, "detail_payload_hash": "sha256:detail-v1"}],
        period="5m",
        source_frontier_ms=1_778_000_000_001,
    )
    second_hash = _board_payload_hash(
        rows=[{**row, "detail_payload_hash": "sha256:detail-v2"}],
        period="5m",
        source_frontier_ms=1_778_000_000_001,
    )

    assert first_hash == second_hash


def test_board_payload_hash_ignores_computed_fallback_observed_timestamps():
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_source": "computed",
    }

    first_hash = _board_payload_hash(
        rows=[{**row, "observed_at_ms": 1_778_000_000_001}],
        period="5m",
        source_frontier_ms=1_778_000_000_001,
    )
    second_hash = _board_payload_hash(
        rows=[{**row, "observed_at_ms": 1_778_000_999_999}],
        period="5m",
        source_frontier_ms=1_778_000_999_999,
    )

    assert first_hash == second_hash


def test_board_payload_hash_keeps_successful_empty_board_stable_across_attempt_time():
    first_hash = _board_payload_hash(rows=[], period="5m", source_frontier_ms=1_778_000_000_001)
    second_hash = _board_payload_hash(rows=[], period="5m", source_frontier_ms=1_778_000_999_999)

    assert first_hash == second_hash


def test_publish_board_skips_serving_row_writes_when_only_computed_observed_time_changes():
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_source": "computed",
    }
    first = {**row, "observed_at_ms": 1_778_000_000_001}
    second = {**row, "observed_at_ms": 1_778_000_999_999}
    conn = _RecordingConn(
        state={
            "board_key": "binance:USDT:PERPETUAL:5m",
            "current_payload_hash": _board_payload_hash(
                rows=[first],
                period="5m",
                source_frontier_ms=1_778_000_000_001,
            ),
        }
    )

    written = CexOiRadarRepository(conn).publish_board(
        rows=[second],
        computed_at_ms=1_778_000_999_999,
        period="5m",
        status="success",
        notes={},
    )

    assert written == 0
    all_sql = "\n".join(conn.sql_calls)
    assert "DELETE FROM cex_oi_radar_rows" not in all_sql
    assert "INSERT INTO cex_oi_radar_rows" not in all_sql


def test_board_payload_hash_rejects_legacy_score_component_keys():
    row = {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {123: "legacy"},
        "observed_at_ms": 1_778_000_000_001,
        "observed_at_source": "provider",
    }

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _board_payload_hash(rows=[row], period="5m", source_frontier_ms=1_778_000_000_001)


def test_publish_board_with_result_reports_changed_empty_board_decision():
    conn = _RecordingConn(state={"current_payload_hash": "sha256:old"})

    result = CexOiRadarRepository(conn).publish_board_with_result(
        rows=[],
        computed_at_ms=1_778_000_000_123,
        period="5m",
        status="success",
        notes={},
    )

    assert result.board_changed is True
    assert result.board_rows_written == 0
    all_sql = "\n".join(conn.sql_calls)
    assert "DELETE FROM cex_oi_radar_rows" in all_sql
    assert "AND NOT (row_id = ANY(%s::text[]))" not in all_sql


def test_publish_board_requires_delete_rowcount_for_write_accounting():
    conn = _RowcountDriftConn(dml_cursors=[_MissingRowcountCursor(), _RowcountCursor(rowcount=1)])

    with pytest.raises(TypeError, match="cex_oi_radar_rowcount_required"):
        CexOiRadarRepository(conn).publish_board(
            rows=[_valid_board_row()],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
            commit=False,
        )

    all_sql = "\n".join(conn.sql_calls)
    assert "DELETE FROM cex_oi_radar_rows" in all_sql
    assert "INSERT INTO cex_oi_radar_rows" not in all_sql


@pytest.mark.parametrize("rowcount", ("unknown", True, -1))
def test_publish_board_rejects_invalid_upsert_rowcount_for_write_accounting(rowcount: object):
    conn = _RowcountDriftConn(dml_cursors=[_RowcountCursor(rowcount=0), _RowcountCursor(rowcount=rowcount)])

    with pytest.raises(TypeError, match="cex_oi_radar_rowcount_invalid"):
        CexOiRadarRepository(conn).publish_board(
            rows=[_valid_board_row()],
            computed_at_ms=1_778_000_000_123,
            period="5m",
            status="success",
            notes={},
            commit=False,
        )

    all_sql = "\n".join(conn.sql_calls)
    assert "DELETE FROM cex_oi_radar_rows" in all_sql
    assert "INSERT INTO cex_oi_radar_rows" in all_sql


def test_skipped_publish_preserves_existing_current_rows():
    conn = _RecordingConn()

    written = CexOiRadarRepository(conn).publish_board(
        rows=[],
        computed_at_ms=1_778_000_999_999,
        period="5m",
        status="skipped",
        notes={"reason": "empty_binance_universe"},
    )

    assert written == 0
    all_sql = "\n".join(conn.sql_calls)
    assert "DELETE FROM cex_oi_radar_rows" not in all_sql
    assert "INSERT INTO cex_oi_radar_rows" not in all_sql
    assert "current_published_at_ms = excluded.current_published_at_ms" not in all_sql


def test_latest_board_reads_publication_state_and_current_rows():
    conn = _RecordingConn(
        state={
            "board_key": "binance:USDT:PERPETUAL:5m",
            "provider": "binance",
            "period": "5m",
            "latest_attempt_status": "success",
            "current_published_at_ms": 1_778_000_000_123,
            "current_source_frontier_ms": 1_778_000_000_100,
            "current_row_count": 1,
        },
        board_rows=[{"target_id": "binance:BTCUSDT", "rank": 1}],
    )

    board = CexOiRadarRepository(conn).latest_board(limit=25)

    assert board["state"]["board_key"] == "binance:USDT:PERPETUAL:5m"
    assert board["publication"]["status"] == "success"
    assert board["publication"]["published_at_ms"] == 1_778_000_000_123
    assert board["publication"]["source_frontier_ms"] == 1_778_000_000_100
    assert board["publication"]["row_count"] == 1
    assert "run" not in board
    assert board["rows"] == [{"target_id": "binance:BTCUSDT", "rank": 1}]
    all_sql = "\n".join(conn.sql_calls)
    assert "FROM cex_oi_radar_publication_state" in all_sql
    assert "FROM cex_oi_radar_rows" in all_sql
    assert "cex_oi_radar_runs" not in all_sql
    assert "finished_at_ms" not in all_sql


@pytest.mark.parametrize(
    "limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("25", id="string"),
    ],
)
def test_latest_board_requires_positive_limit_before_sql(limit: object):
    conn = _RecordingConn()

    with pytest.raises(ValueError, match="cex_oi_radar_latest_board_limit_required"):
        CexOiRadarRepository(conn).latest_board(limit=limit)  # type: ignore[arg-type]

    assert conn.sql_calls == []


def test_record_attempt_failure_preserves_current_rows():
    conn = _RecordingConn()

    CexOiRadarRepository(conn).record_attempt_failure(
        computed_at_ms=1_778_000_000_123,
        period="5m",
        notes={"reason": "RuntimeError"},
    )

    assert conn.committed is True
    all_sql = "\n".join(conn.sql_calls)
    assert "cex_oi_radar_publication_state" in all_sql
    assert "latest_attempt_status = excluded.latest_attempt_status" in all_sql
    assert "current_published_at_ms = excluded.current_published_at_ms" not in all_sql
    assert "DELETE FROM cex_oi_radar_rows" not in all_sql
    params = conn.params_for("INSERT INTO cex_oi_radar_publication_state")
    assert params == (
        "binance:USDT:PERPETUAL:5m",
        "binance",
        "binance",
        "USDT",
        "PERPETUAL",
        "5m",
        "failed",
        1_778_000_000_123,
        1_778_000_000_123,
        "RuntimeError",
        1_778_000_000_123,
    )


def test_record_attempt_failure_requires_connection_transaction_before_sql_when_committing():
    conn = _NoTransactionConn()

    with pytest.raises(TypeError, match="cex_oi_radar_transaction_required"):
        CexOiRadarRepository(conn).record_attempt_failure(
            computed_at_ms=1_778_000_000_123,
            period="5m",
            notes={"reason": "RuntimeError"},
        )

    assert conn.sql_calls == []


def _valid_board_row() -> dict[str, object]:
    return {
        "rank": 1,
        "target_id": "binance:BTCUSDT",
        "pricefeed_id": "pf-btc",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "open_interest_change_pct_1h": 10.0,
        "volume_24h_usd": 10_000_000.0,
        "funding_rate": 0.0001,
        "mark_price": 101.0,
        "score": 91.5,
        "score_components": {"oi": 1},
        "observed_at_ms": 1_778_000_000_001,
        "observed_at_source": "provider",
    }


class _RecordingConn:
    def __init__(self, *, state=None, board_rows=None) -> None:
        self.sql_calls: list[str] = []
        self.params_calls: list[tuple[str, tuple]] = []
        self.committed = False
        self.rollbacks = 0
        self.transaction_depth = 0
        self.rowcount = 0
        self._state = state
        self._board_rows = board_rows or [{"native_market_id": "BTCUSDT"}]

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.sql_calls.append(sql_text)
        self.params_calls.append((sql_text, tuple(params or ())))
        if "INSERT INTO cex_oi_radar_rows" in sql_text:
            self.rowcount = 1
        elif "DELETE FROM cex_oi_radar_rows" in sql_text:
            self.rowcount = 0
        else:
            self.rowcount = 0
        return self

    def fetchall(self):
        return self._board_rows

    def fetchone(self):
        return self._state

    def commit(self):
        self.committed = True

    def transaction(self):
        return _Transaction(self)

    def params_for(self, sql_fragment: str) -> tuple:
        for sql, params in self.params_calls:
            if sql_fragment in sql:
                return params
        raise AssertionError(f"missing sql fragment: {sql_fragment}")


class _NoTransactionConn(_RecordingConn):
    transaction = None


class _RowcountDriftConn(_RecordingConn):
    def __init__(self, *, dml_cursors: list[object]) -> None:
        super().__init__()
        self._dml_cursors = list(dml_cursors)

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.sql_calls.append(sql_text)
        self.params_calls.append((sql_text, tuple(params or ())))
        if "DELETE FROM cex_oi_radar_rows" in sql_text or "INSERT INTO cex_oi_radar_rows" in sql_text:
            return self._dml_cursors.pop(0)
        return self


class _RowcountCursor:
    def __init__(self, *, rowcount: object) -> None:
        self.rowcount = rowcount


class _MissingRowcountCursor:
    pass


class _Transaction:
    def __init__(self, conn: _RecordingConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args):
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.committed = True
        else:
            self.conn.rollbacks += 1
        return False
