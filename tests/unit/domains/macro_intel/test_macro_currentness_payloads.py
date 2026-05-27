from __future__ import annotations

from datetime import date


def test_api_macro_currentness_marks_projection_behind_when_facts_exist_without_snapshot() -> None:
    from gmgn_twitter_intel.app.surfaces.api.routes_macro import _macro_currentness

    repo = FakeMacroIntelRepository(
        facts_max_observed_at=date(2026, 5, 27),
        latest_sync={
            "sync_run_id": "sync-run-1",
            "status": "ok",
            "asof_date": date(2026, 5, 27),
            "max_observed_at": date(2026, 5, 27),
            "imported_observation_count": 12,
            "completed_at_ms": 1_779_000_000_000,
        },
    )

    payload = _macro_currentness(FakeRepositorySession(repo), snapshot=None)

    assert payload == {
        "latest_sync_run": {
            "status": "ok",
            "completed_at_ms": 1_779_000_000_000,
            "asof_date": "2026-05-27",
            "max_observed_at": "2026-05-27",
            "imported_observation_count": 12,
            "error_code": None,
        },
        "facts_max_observed_at": "2026-05-27",
        "projection_lag_days": None,
        "projection_behind_facts": True,
    }


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        facts_max_observed_at: date | None,
        latest_sync: dict[str, object] | None,
    ) -> None:
        self._facts_max_observed_at = facts_max_observed_at
        self._latest_sync = latest_sync

    def macro_observations_max_observed_at(self) -> date | None:
        return self._facts_max_observed_at

    def latest_macro_sync_run(self) -> dict[str, object] | None:
        return self._latest_sync
