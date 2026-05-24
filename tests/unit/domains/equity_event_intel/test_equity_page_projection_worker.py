from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_page_projection_worker import (
    EquityEventPageProjectionWorker,
)


def test_page_projection_worker_skips_event_scan_when_source_summary_is_unchanged() -> None:
    repo = _FakeEquityEventRepository(
        summaries=[
            _complete_summary(source_watermark_ms=1000),
            _complete_summary(source_watermark_ms=1000),
        ]
    )
    worker = _worker(repo)

    first_result = worker.run_once_sync(now_ms=2000)
    second_result = worker.run_once_sync(now_ms=3000)

    assert first_result.notes["event_scan"] == "scanned"
    assert second_result.notes["event_scan"] == "skipped"
    assert repo.event_projection_scan_count == 1


def test_page_projection_worker_scans_when_source_watermark_changes() -> None:
    repo = _FakeEquityEventRepository(
        summaries=[
            _complete_summary(source_watermark_ms=1000),
            _complete_summary(source_watermark_ms=2000),
        ]
    )
    worker = _worker(repo)

    worker.run_once_sync(now_ms=2000)
    result = worker.run_once_sync(now_ms=3000)

    assert result.notes["event_scan"] == "scanned"
    assert repo.event_projection_scan_count == 2


def test_page_projection_worker_scans_when_read_model_coverage_is_incomplete() -> None:
    repo = _FakeEquityEventRepository(
        summaries=[
            _complete_summary(source_watermark_ms=1000),
            {
                **_complete_summary(source_watermark_ms=1000),
                "timeline_row_count": 9,
            },
        ]
    )
    worker = _worker(repo)

    worker.run_once_sync(now_ms=2000)
    result = worker.run_once_sync(now_ms=3000)

    assert result.notes["event_scan"] == "scanned"
    assert repo.event_projection_scan_count == 2


def test_page_projection_worker_scans_when_alert_coverage_is_wrong() -> None:
    repo = _FakeEquityEventRepository(
        summaries=[
            _complete_summary(source_watermark_ms=1000),
            {
                **_complete_summary(source_watermark_ms=1000),
                "required_alert_count": 1,
                "alert_candidate_count": 0,
            },
        ]
    )
    worker = _worker(repo)

    worker.run_once_sync(now_ms=2000)
    result = worker.run_once_sync(now_ms=3000)

    assert result.notes["event_scan"] == "scanned"
    assert repo.event_projection_scan_count == 2


def _complete_summary(*, source_watermark_ms: int) -> dict[str, int]:
    return {
        "eligible_event_count": 10,
        "page_row_count": 10,
        "timeline_row_count": 10,
        "required_alert_count": 0,
        "alert_candidate_count": 0,
        "source_watermark_ms": source_watermark_ms,
    }


def _worker(repo: _FakeEquityEventRepository) -> EquityEventPageProjectionWorker:
    return EquityEventPageProjectionWorker(
        name="equity_event_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=None),
        db=_FakeDb(repo),
        telemetry=SimpleNamespace(),
    )


class _FakeDb:
    def __init__(self, repo: _FakeEquityEventRepository) -> None:
        self.repo = repo

    def worker_session(self, *_args: Any, **_kwargs: Any) -> _FakeSession:
        return _FakeSession(self.repo)


class _FakeSession:
    def __init__(self, repo: _FakeEquityEventRepository) -> None:
        self.equity_events = repo
        self.conn = _FakeConn()

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _FakeConn:
    def commit(self) -> None:
        return None


class _FakeEquityEventRepository:
    def __init__(self, *, summaries: list[dict[str, int]]) -> None:
        self._summaries = list(summaries)
        self.event_projection_scan_count = 0

    def page_projection_source_summary(self) -> dict[str, int]:
        if len(self._summaries) > 1:
            return self._summaries.pop(0)
        return self._summaries[0]

    def list_events_for_page_projection(self, *, limit: int) -> list[dict[str, Any]]:
        self.event_projection_scan_count += 1
        return []

    def list_expected_events_for_calendar_projection(self, *, limit: int, now_ms: int) -> list[dict[str, Any]]:
        return []

    def list_inactive_expected_event_ids_for_calendar_projection(self, *, limit: int) -> list[str]:
        return []
