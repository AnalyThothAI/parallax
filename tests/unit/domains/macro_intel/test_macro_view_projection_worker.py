from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)

NOW_MS = 1_779_000_000_000


def test_macro_view_projection_worker_writes_latest_snapshot() -> None:
    repo = FakeMacroIntelRepository(
        observations=[
            {
                "source_name": "fred",
                "concept_key": "vol:vix",
                "series_key": "fred:VIXCLS",
                "source_priority": 100,
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
        settings=SimpleNamespace(
            batch_size=250,
            lookback_days=730,
            limit_per_series=99,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["projection_version"] == "macro_regime_v4"
    assert result.notes["status"] == "partial"
    assert result.notes["history_coverage_ratio"] == "0.0"
    assert "data_gap_count" in result.notes
    assert int(result.notes["data_gap_count"]) > 0
    assert db.sessions == ["macro_view_projection"]
    assert repo.observations_for_series_call == {
        "concept_keys": MACRO_CORE_CONCEPTS,
        "lookback_days": 730,
        "limit_per_series": 99,
    }
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["snapshot_id"] == "macro-view:macro_regime_v4:1779000000000"
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
        self.observations_for_series_call: dict[str, object] | None = None
        self.snapshots: list[dict[str, object]] = []

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, object]]:
        self.observations_for_series_call = {
            "concept_keys": concept_keys,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.observations

    def insert_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)
