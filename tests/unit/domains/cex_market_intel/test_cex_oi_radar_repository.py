from __future__ import annotations

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


class _RecordingConn:
    def __init__(self, *, state=None, board_rows=None) -> None:
        self.sql_calls: list[str] = []
        self.params_calls: list[tuple[str, tuple]] = []
        self.committed = False
        self._state = state
        self._board_rows = board_rows or [{"native_market_id": "BTCUSDT"}]

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.sql_calls.append(sql_text)
        self.params_calls.append((sql_text, tuple(params or ())))
        return self

    def fetchall(self):
        return self._board_rows

    def fetchone(self):
        return self._state

    def commit(self):
        self.committed = True

    def params_for(self, sql_fragment: str) -> tuple:
        for sql, params in self.params_calls:
            if sql_fragment in sql:
                return params
        raise AssertionError(f"missing sql fragment: {sql_fragment}")
