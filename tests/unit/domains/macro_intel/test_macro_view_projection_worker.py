from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)

NOW_MS = 1_779_000_000_000


def test_macro_view_projection_worker_writes_latest_snapshot() -> None:
    repo = FakeMacroIntelRepository(
        observations=[
            {
                "source_name": "fred",
                "series_key": "fred:VIXCLS",
                "observed_at": "2026-05-20",
                "value_numeric": 18.2,
                "unit": "index",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-05-20",
            }
        ]
    )
    db = FakeDB(repo)
    worker = MacroViewProjectionWorker(
        name="macro_view_projection",
        settings=SimpleNamespace(batch_size=250, statement_timeout_seconds=30),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["projection_version"] == "macro_regime_v1"
    assert result.notes["status"] == "partial"
    assert db.sessions == ["macro_view_projection"]
    assert repo.latest_limit == 250
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["snapshot_id"] == "macro-view:macro_regime_v1:1779000000000"
    assert repo.snapshots[0]["panels_json"]["volatility"]["regime"] == "carry"


class FakeDB:
    def __init__(self, repo: FakeMacroIntelRepository) -> None:
        self.repo = repo
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(macro_intel=self.repo)


class FakeMacroIntelRepository:
    def __init__(self, *, observations: list[dict[str, object]]) -> None:
        self.observations = observations
        self.latest_limit: int | None = None
        self.snapshots: list[dict[str, object]] = []

    def latest_observations(self, *, limit: int) -> list[dict[str, object]]:
        self.latest_limit = limit
        return self.observations

    def insert_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)
