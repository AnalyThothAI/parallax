from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_page_projection_worker import (
    EquityEventPageProjectionWorker,
)


def test_page_projection_worker_empty_dirty_queue_reports_claimed_without_event_scan_note() -> None:
    dirty_repo = _FakeDirtyTargetRepository()
    worker = EquityEventPageProjectionWorker(
        name="equity_event_page_projection",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=None),
        db=_FakeDb(_FakeEquityEventRepository(), dirty_repo),
        telemetry=SimpleNamespace(),
    )

    result = worker.run_once_sync(now_ms=2_000)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert "event_scan" not in result.notes
    assert dirty_repo.claimed_projection_names == ["page", "timeline", "alert", "calendar"]


class _FakeDb:
    def __init__(self, repo: _FakeEquityEventRepository, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.repo = repo
        self.dirty_repo = dirty_repo

    def worker_session(self, *_args: Any, **_kwargs: Any) -> _FakeSession:
        return _FakeSession(self.repo, self.dirty_repo)


class _FakeSession:
    def __init__(self, repo: _FakeEquityEventRepository, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.equity_events = repo
        self.equity_projection_dirty_targets = dirty_repo
        self.conn = _FakeConn()

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _FakeConn:
    def commit(self) -> None:
        return None


class _FakeDirtyTargetRepository:
    def __init__(self) -> None:
        self.claimed_projection_names: list[str] = []

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        projection_name: str | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        self.claimed_projection_names.append(str(projection_name))
        return []


class _FakeEquityEventRepository:
    pass
