from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)


def test_cex_oi_radar_board_worker_persists_latest_run():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        cex_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.processed == 1
    assert db.repos.cex_oi_radar.started["universe_count"] == 1
    assert db.repos.cex_oi_radar.inserted[0]["target_id"] == "binance:BTCUSDT"
    assert db.repos.cex_oi_radar.finished["status"] == "success"


class _DB:
    def __init__(self) -> None:
        self.repos = SimpleNamespace(cex_oi_radar=_Repo())

    def worker_session(self, *_args, **_kwargs):
        return _Session(self.repos)


class _Session:
    def __init__(self, repos) -> None:
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, *_args):
        return None


class _Repo:
    def __init__(self) -> None:
        self.started = {}
        self.inserted = []
        self.finished = {}

    def binance_usdt_perp_universe(self, *, limit):
        return [{"pricefeed_id": "pf", "native_market_id": "BTCUSDT", "base_symbol": "BTC"}]

    def start_run(self, **kwargs):
        self.started = kwargs

    def insert_rows(self, *, run_id, rows, computed_at_ms):
        self.inserted = rows
        return len(rows)

    def finish_run(self, **kwargs):
        self.finished = kwargs


class _Client:
    def ticker_24hr(self):
        return [SimpleNamespace(symbol="BTCUSDT", last_price=100.0, quote_volume_24h=10_000_000.0)]

    def premium_index(self):
        return [SimpleNamespace(symbol="BTCUSDT", mark_price=101.0, last_funding_rate=0.0001)]

    def open_interest_hist(self, *, symbol, period, limit):
        return [
            SimpleNamespace(symbol=symbol, open_interest_value=1000.0, time_ms=1),
            SimpleNamespace(symbol=symbol, open_interest_value=1100.0, time_ms=2),
        ]
