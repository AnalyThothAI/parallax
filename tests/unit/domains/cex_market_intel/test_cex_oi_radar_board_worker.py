from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.cex_market_intel.providers import (
    CexFundingPremium,
    CexOiTicker24h,
    CexOpenInterestPoint,
)
from parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)


def test_cex_oi_radar_board_worker_publishes_current_board():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.processed == 1
    published = db.repos.cex_oi_radar.published[0]
    assert published["period"] == "5m"
    assert published["status"] == "success"
    assert published["rows"][0]["target_id"] == "binance:BTCUSDT"
    assert published["notes"] == {"failed_symbols": [], "detail_snapshot_count": 1}
    assert db.repos.cex_detail_snapshots.upserted[0]["target_id"] == "cex_token:BTC"
    assert db.repos.cex_detail_snapshots.upserted[0]["oi_change_pct_1h"] is None
    assert "run_id" not in result.notes
    assert result.notes["source_rows_scanned"] == 1
    assert result.notes["targets_loaded"] == 1
    assert result.notes["rows_written"] == 2
    assert result.notes["board_changed"] is True
    assert result.notes["board_rows_written"] == 1
    assert result.notes["detail_changed_count"] == 1
    assert result.notes["detail_rows_written"] == 1


def test_cex_oi_radar_board_worker_zero_writes_when_board_and_detail_unchanged():
    db = _DB(board_rows_written=0, detail_rows_written=0)
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.notes["rows_written"] == 0
    assert result.notes["board_changed"] is False
    assert result.notes["board_rows_written"] == 0
    assert result.notes["detail_changed_count"] == 0
    assert result.notes["detail_rows_written"] == 0
    assert db.repos.cex_oi_radar.serving_rows_written == 0
    assert db.repos.cex_detail_snapshots.serving_rows_written == 0
    assert db.publication_events == ["transaction_begin", "publish_board_with_result", "upsert_detail", "commit"]


def test_cex_oi_radar_board_worker_changed_board_unchanged_detail_only_writes_board_rows():
    db = _DB(board_rows_written=1, detail_rows_written=0)
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.notes["rows_written"] == 1
    assert result.notes["board_changed"] is True
    assert result.notes["board_rows_written"] == 1
    assert result.notes["detail_changed_count"] == 0
    assert result.notes["detail_rows_written"] == 0
    assert db.repos.cex_oi_radar.serving_rows_written == 1
    assert db.repos.cex_detail_snapshots.serving_rows_written == 0
    assert db.publication_events == ["transaction_begin", "publish_board_with_result", "upsert_detail", "commit"]


def test_cex_oi_radar_board_worker_unchanged_board_changed_detail_only_writes_detail_rows():
    db = _DB(board_rows_written=0, detail_rows_written=1)
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.notes["rows_written"] == 1
    assert result.notes["board_changed"] is False
    assert result.notes["board_rows_written"] == 0
    assert result.notes["detail_changed_count"] == 1
    assert result.notes["detail_rows_written"] == 1
    assert db.repos.cex_oi_radar.serving_rows_written == 0
    assert db.repos.cex_detail_snapshots.serving_rows_written == 1
    assert db.publication_events == ["transaction_begin", "publish_board_with_result", "upsert_detail", "commit"]


def test_cex_oi_radar_board_worker_rolls_back_board_publication_when_detail_write_fails():
    db = _DB(detail_raises=True)
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    try:
        worker.run_once_sync()
    except RuntimeError as exc:
        assert str(exc) == "detail boom"
    else:
        raise AssertionError("expected detail failure")

    assert db.publication_events == [
        "transaction_begin",
        "publish_board_with_result",
        "upsert_detail",
        "rollback",
    ]
    assert db.repos.cex_oi_radar.published == []
    assert db.repos.cex_oi_radar.serving_rows_written == 0
    assert db.repos.cex_oi_radar.failed_attempts == [
        {
            "computed_at_ms": 1_778_000_000_000,
            "period": "5m",
            "notes": {"reason": "RuntimeError"},
        }
    ]


def test_cex_oi_radar_board_worker_skips_when_previous_thread_still_finishing():
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=_DB(),
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )
    worker._local_run_lock.acquire()
    try:
        result = worker.run_once_sync()
    finally:
        worker._local_run_lock.release()

    assert result.skipped == 1
    assert result.notes["reason"] == "previous_run_still_finishing"
    assert result.notes["source_rows_scanned"] == 0
    assert result.notes["targets_loaded"] == 0
    assert result.notes["rows_written"] == 0


def test_cex_oi_radar_board_worker_caps_universe_to_batch_size():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(
            enabled=True,
            batch_size=1,
            universe_limit=500,
            period="5m",
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    worker.run_once_sync()

    assert db.repos.cex_oi_radar.requested_limit == 1
    assert len(db.repos.cex_oi_radar.published[0]["rows"]) == 1


def test_cex_oi_radar_board_worker_publishes_skipped_board_for_empty_universe():
    db = _DB(universe=[])
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.skipped == 1
    assert db.repos.cex_oi_radar.published == [
        {
            "rows": [],
            "computed_at_ms": 1_778_000_000_000,
            "period": "5m",
            "status": "skipped",
            "notes": {"reason": "empty_binance_universe"},
        }
    ]
    assert "run_id" not in result.notes


def test_cex_oi_radar_board_worker_records_failed_attempt_without_clearing_current_board():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_FailingClient(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    try:
        worker.run_once_sync()
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected RuntimeError")

    assert db.repos.cex_oi_radar.published == []
    assert db.repos.cex_oi_radar.failed_attempts == [
        {
            "computed_at_ms": 1_778_000_000_000,
            "period": "5m",
            "notes": {"reason": "RuntimeError"},
        }
    ]


def test_cex_oi_radar_board_worker_does_not_publish_empty_board_when_all_symbols_fail():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(enabled=True, batch_size=10, period="5m", statement_timeout_seconds=30),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_OpenInterestFailingClient(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    result = worker.run_once_sync()

    assert result.failed == 1
    assert db.repos.cex_oi_radar.published == []
    assert db.repos.cex_oi_radar.failed_attempts == [
        {
            "computed_at_ms": 1_778_000_000_000,
            "period": "5m",
            "notes": {"reason": "all_symbols_failed", "failed_symbols": ["BTCUSDT"]},
        }
    ]


def test_cex_oi_radar_board_worker_adds_coinglass_enrichment_to_detail_snapshot():
    db = _DB()
    worker = CexOiRadarBoardWorker(
        name="cex_oi_radar_board",
        settings=SimpleNamespace(
            enabled=True,
            batch_size=10,
            universe_limit=10,
            period="5m",
            statement_timeout_seconds=30,
            coinglass_enrichment_limit=1,
            coinglass_level_limit=2,
        ),
        db=db,
        telemetry=SimpleNamespace(),
        oi_market=_Client(),
        coinglass_derivatives=_CoinglassClient(),
        clock_ms=lambda: 1_778_000_000_000,
    )

    worker.run_once_sync()

    snapshot = db.repos.cex_detail_snapshots.upserted[0]
    assert snapshot["coinglass_status"] == "ready"
    assert snapshot["oi_change_pct_1h"] == 10.0
    assert snapshot["cvd_delta_4h"] == 125.0
    assert snapshot["level_bands"][0]["kind"] == "resistance"


class _DB:
    def __init__(
        self,
        *,
        universe=None,
        board_rows_written=None,
        detail_rows_written=None,
        detail_raises=False,
    ) -> None:
        self.publication_events = []
        self.repos = _Repos(
            cex_oi_radar=_Repo(
                universe=universe,
                publication_events=self.publication_events,
                board_rows_written=board_rows_written,
            ),
            cex_detail_snapshots=_DetailRepo(
                publication_events=self.publication_events,
                detail_rows_written=detail_rows_written,
                detail_raises=detail_raises,
            ),
            publication_events=self.publication_events,
        )

    def worker_session(self, *_args, **_kwargs):
        return _Session(self.repos)


class _Session:
    def __init__(self, repos) -> None:
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, *_args):
        return None


class _Repos(SimpleNamespace):
    def __init__(self, *, cex_oi_radar, cex_detail_snapshots, publication_events) -> None:
        super().__init__(cex_oi_radar=cex_oi_radar, cex_detail_snapshots=cex_detail_snapshots)
        self._publication_events = publication_events

    def transaction(self):
        return _Transaction(self)


class _Transaction:
    def __init__(self, repos) -> None:
        self.repos = repos
        self._published_snapshot = None
        self._board_written_snapshot = 0

    def __enter__(self):
        self.repos._publication_events.append("transaction_begin")
        self._published_snapshot = list(self.repos.cex_oi_radar.published)
        self._board_written_snapshot = int(self.repos.cex_oi_radar.serving_rows_written)

    def __exit__(self, exc_type, *_args):
        if exc_type is None:
            self.repos._publication_events.append("commit")
            return False
        self.repos.cex_oi_radar.published = list(self._published_snapshot or [])
        self.repos.cex_oi_radar.serving_rows_written = self._board_written_snapshot
        self.repos._publication_events.append("rollback")
        return False


class _Repo:
    def __init__(self, *, universe=None, publication_events=None, board_rows_written=None) -> None:
        self._universe = universe
        self._publication_events = publication_events
        self._board_rows_written = board_rows_written
        self.published = []
        self.failed_attempts = []
        self.requested_limit = None
        self.serving_rows_written = 0

    def binance_usdt_perp_universe(self, *, limit):
        self.requested_limit = limit
        if self._universe is not None:
            return self._universe
        return [
            {
                "pricefeed_id": "pf",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ]

    def publish_board(self, *, rows, computed_at_ms, period, status, notes):
        if self._publication_events is not None:
            self._publication_events.append("publish_board")
        self.published.append(
            {
                "rows": list(rows),
                "computed_at_ms": computed_at_ms,
                "period": period,
                "status": status,
                "notes": notes,
            }
        )
        written = int(self._board_rows_written if self._board_rows_written is not None else len(rows))
        self.serving_rows_written += written
        return written

    def publish_board_with_result(self, *, rows, computed_at_ms, period, status, notes, commit=True):
        if commit:
            raise AssertionError("worker must publish board inside explicit transaction with commit=False")
        written = self.publish_board(
            rows=rows,
            computed_at_ms=computed_at_ms,
            period=period,
            status=status,
            notes=notes,
        )
        if self._publication_events is not None:
            self._publication_events[-1] = "publish_board_with_result"
        return SimpleNamespace(board_changed=written > 0, board_rows_written=written)

    def record_attempt_failure(self, *, computed_at_ms, period, notes):
        self.failed_attempts.append(
            {
                "computed_at_ms": computed_at_ms,
                "period": period,
                "notes": notes,
            }
        )


class _DetailRepo:
    def __init__(self, *, publication_events=None, detail_rows_written=None, detail_raises=False) -> None:
        self._publication_events = publication_events
        self._detail_rows_written = detail_rows_written
        self._detail_raises = detail_raises
        self.upserted = []
        self.serving_rows_written = 0

    def upsert_many(self, snapshots, *, commit=False):
        if commit:
            raise AssertionError("worker must upsert detail inside explicit transaction with commit=False")
        if self._publication_events is not None:
            self._publication_events.append("upsert_detail")
        if self._detail_raises:
            raise RuntimeError("detail boom")
        self.upserted = list(snapshots)
        written = int(self._detail_rows_written if self._detail_rows_written is not None else len(self.upserted))
        self.serving_rows_written += written
        return written


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
        return [
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1000.0, observed_at_ms=1),
            CexOpenInterestPoint(symbol=symbol, open_interest_value=1100.0, observed_at_ms=2),
        ]


class _FailingClient(_Client):
    def list_24h_tickers(self, symbol=None):
        del symbol
        raise RuntimeError("boom")


class _OpenInterestFailingClient(_Client):
    def list_open_interest_history(self, symbol, period, limit):
        del symbol, period, limit
        raise RuntimeError("oi boom")


class _CoinglassClient:
    def fetch_oi_history(self, *, symbol, time_type, lookback):
        values = {"1": (100, 110), "2": (100, 125), "4": (100, 150)}[time_type]
        return {"data": [{"timestamp": 1, "usd": values[0]}, {"timestamp": 2, "usd": values[1]}]}

    def fetch_cvd_history(self, *, symbol, time_type, lookback):
        deltas = {"1": [10, -5], "2": [100, 25], "4": [300, -50]}[time_type]
        return {"data": [{"timestamp": index, "delta": delta} for index, delta in enumerate(deltas)]}

    def fetch_long_short_ratio_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.1}, {"timestamp": 2, "longShortRatio": 1.3}]}

    def fetch_top_trader_position_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.4}, {"timestamp": 2, "longShortRatio": 1.6}]}

    def fetch_liquidation_levels(self, *, symbol, range):
        return {"levels": [{"price": 72_000, "size": 2_000_000_000, "side": 2}]}
