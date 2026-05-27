from __future__ import annotations

from gmgn_twitter_intel.domains.cex_market_intel.repositories.cex_oi_radar_repository import (
    CexOiRadarRepository,
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


def test_publish_board_replaces_current_rows_with_stable_target_identity():
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
    assert state_params[7:10] == (1_778_000_000_001, 1, "success")

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


def test_latest_board_reads_publication_state_and_current_rows():
    conn = _RecordingConn(
        state={
            "board_key": "binance:USDT:PERPETUAL:5m",
            "provider": "binance",
            "period": "5m",
            "latest_attempt_status": "success",
            "latest_attempt_finished_at_ms": 1_778_000_000_123,
        },
        board_rows=[{"target_id": "binance:BTCUSDT", "rank": 1}],
    )

    board = CexOiRadarRepository(conn).latest_board(limit=25)

    assert board["state"]["board_key"] == "binance:USDT:PERPETUAL:5m"
    assert board["run"]["status"] == "success"
    assert board["run"]["finished_at_ms"] == 1_778_000_000_123
    assert board["rows"] == [{"target_id": "binance:BTCUSDT", "rank": 1}]
    all_sql = "\n".join(conn.sql_calls)
    assert "FROM cex_oi_radar_publication_state" in all_sql
    assert "FROM cex_oi_radar_rows" in all_sql
    assert "cex_oi_radar_runs" not in all_sql
    assert "finished_at_ms" not in all_sql


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
