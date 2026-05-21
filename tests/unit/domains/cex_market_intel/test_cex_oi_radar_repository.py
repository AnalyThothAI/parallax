from __future__ import annotations

from gmgn_twitter_intel.domains.cex_market_intel.repositories.cex_oi_radar_repository import (
    CexOiRadarRepository,
    oi_radar_run_id,
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


def test_oi_radar_run_id_is_deterministic():
    assert oi_radar_run_id(started_at_ms=123) == "cex-oi-radar:binance-usdt-perp:123"


class _RecordingConn:
    def __init__(self) -> None:
        self.sql_calls: list[str] = []

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        return self

    def fetchall(self):
        return [{"native_market_id": "BTCUSDT"}]
