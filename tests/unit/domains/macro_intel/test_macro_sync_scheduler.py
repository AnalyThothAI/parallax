from __future__ import annotations

from datetime import date

import pytest


def test_scheduler_bootstrap_partitions_missing_history_into_bounded_windows() -> None:
    from parallax.domains.macro_intel.services.macro_sync_scheduler import (
        ensure_due_macro_sync_windows,
    )

    repo = FakeMacroIntelRepository(max_observed_at=None)
    summary = ensure_due_macro_sync_windows(
        repos=FakeRepositorySession(repo),
        source_name="macrodata-cli",
        bundle_name="macro-core",
        now=date(2026, 5, 27),
        now_ms=1_779_000_000_000,
        bootstrap_lookback_days=95,
        max_window_days=31,
        steady_overlap_days=7,
        steady_interval_seconds=900.0,
        max_bootstrap_windows_per_cycle=2,
        max_attempts=8,
    )

    bootstrap_windows = [window for window in repo.enqueued if window["trigger_reason"] == "bootstrap"]
    assert summary["enqueued_bootstrap_windows"] == 2
    assert [(item["window_start"], item["window_end"]) for item in bootstrap_windows] == [
        (date(2026, 2, 21), date(2026, 3, 23)),
        (date(2026, 3, 24), date(2026, 4, 23)),
    ]
    assert all((item["window_end"] - item["window_start"]).days <= 30 for item in bootstrap_windows)
    assert repo.sync_state_reads == [{"source_name": "macrodata-cli", "bundle_name": "macro-core"}]
    assert repo.provider_calls == []


def test_scheduler_gap_and_steady_state_enqueues_due_windows() -> None:
    from parallax.domains.macro_intel.services.macro_sync_scheduler import (
        ensure_due_macro_sync_windows,
    )

    repo = FakeMacroIntelRepository(max_observed_at=date(2026, 5, 20))
    summary = ensure_due_macro_sync_windows(
        repos=FakeRepositorySession(repo),
        source_name="macrodata-cli",
        bundle_name="macro-core",
        now=date(2026, 5, 27),
        now_ms=1_779_000_000_000,
        bootstrap_lookback_days=1095,
        max_window_days=3,
        steady_overlap_days=7,
        steady_interval_seconds=900.0,
        max_bootstrap_windows_per_cycle=1,
        max_attempts=8,
    )

    assert summary["max_observed_at"] == "2026-05-20"
    assert [(item["trigger_reason"], item["window_start"], item["window_end"]) for item in repo.enqueued[:3]] == [
        ("gap", date(2026, 5, 21), date(2026, 5, 23)),
        ("gap", date(2026, 5, 24), date(2026, 5, 26)),
        ("gap", date(2026, 5, 27), date(2026, 5, 27)),
    ]
    assert repo.enqueued[3]["trigger_reason"] == "steady_overlap"
    assert (repo.enqueued[3]["window_start"], repo.enqueued[3]["window_end"]) == (
        date(2026, 5, 20),
        date(2026, 5, 27),
    )
    assert repo.sync_state_reads == [{"source_name": "macrodata-cli", "bundle_name": "macro-core"}]
    assert repo.provider_calls == []


def test_scheduler_steady_overlap_identity_is_stable_across_interval_buckets() -> None:
    from parallax.domains.macro_intel.services.macro_sync_scheduler import (
        ensure_due_macro_sync_windows,
    )

    repo = FakeMacroIntelRepository(max_observed_at=date(2026, 5, 27))

    ensure_due_macro_sync_windows(
        repos=FakeRepositorySession(repo),
        source_name="macrodata-cli",
        bundle_name="macro-core",
        now=date(2026, 5, 27),
        now_ms=1_779_000_000_000,
        bootstrap_lookback_days=1095,
        max_window_days=31,
        steady_overlap_days=7,
        steady_interval_seconds=900.0,
        max_bootstrap_windows_per_cycle=1,
        max_attempts=8,
    )
    ensure_due_macro_sync_windows(
        repos=FakeRepositorySession(repo),
        source_name="macrodata-cli",
        bundle_name="macro-core",
        now=date(2026, 5, 27),
        now_ms=1_779_000_100_000,
        bootstrap_lookback_days=1095,
        max_window_days=31,
        steady_overlap_days=7,
        steady_interval_seconds=900.0,
        max_bootstrap_windows_per_cycle=1,
        max_attempts=8,
    )
    ensure_due_macro_sync_windows(
        repos=FakeRepositorySession(repo),
        source_name="macrodata-cli",
        bundle_name="macro-core",
        now=date(2026, 5, 27),
        now_ms=1_779_000_300_000,
        bootstrap_lookback_days=1095,
        max_window_days=31,
        steady_overlap_days=7,
        steady_interval_seconds=900.0,
        max_bootstrap_windows_per_cycle=1,
        max_attempts=8,
    )

    steady_reasons = [window["trigger_reason"] for window in repo.enqueued]
    assert steady_reasons == ["steady_overlap", "steady_overlap", "steady_overlap"]


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"bootstrap_lookback_days": 0}, "macro_sync_bootstrap_lookback_days_required"),
        pytest.param({"bootstrap_lookback_days": True}, "macro_sync_bootstrap_lookback_days_required"),
        pytest.param({"max_window_days": 0}, "macro_sync_max_window_days_required"),
        pytest.param({"steady_overlap_days": 0}, "macro_sync_steady_overlap_days_required"),
        pytest.param({"steady_interval_seconds": -1.0}, "macro_sync_steady_interval_seconds_required"),
        pytest.param({"steady_interval_seconds": True}, "macro_sync_steady_interval_seconds_required"),
        pytest.param(
            {"max_bootstrap_windows_per_cycle": 0},
            "macro_sync_max_bootstrap_windows_per_cycle_required",
        ),
        pytest.param({"max_attempts": 0}, "macro_sync_max_attempts_required"),
        pytest.param({"max_attempts": "8"}, "macro_sync_max_attempts_required"),
    ],
)
def test_scheduler_rejects_malformed_boundaries_before_repository_read(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    from parallax.domains.macro_intel.services.macro_sync_scheduler import (
        ensure_due_macro_sync_windows,
    )

    repo = FakeMacroIntelRepository(max_observed_at=None)
    kwargs: dict[str, object] = {
        "repos": FakeRepositorySession(repo),
        "source_name": "macrodata-cli",
        "bundle_name": "macro-core",
        "now": date(2026, 5, 27),
        "now_ms": 1_779_000_000_000,
        "bootstrap_lookback_days": 95,
        "max_window_days": 31,
        "steady_overlap_days": 7,
        "steady_interval_seconds": 900.0,
        "max_bootstrap_windows_per_cycle": 2,
        "max_attempts": 8,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError, match=error_code):
        ensure_due_macro_sync_windows(**kwargs)  # type: ignore[arg-type]

    assert repo.sync_state_reads == []
    assert repo.enqueued == []


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel


class FakeMacroIntelRepository:
    def __init__(self, *, max_observed_at: date | None) -> None:
        self._max_observed_at = max_observed_at
        self.enqueued: list[dict[str, object]] = []
        self.provider_calls: list[object] = []
        self.sync_state_reads: list[dict[str, object]] = []

    def macro_sync_state_max_observed_at(self, *, source_name: str, bundle_name: str) -> date | None:
        self.sync_state_reads.append({"source_name": source_name, "bundle_name": bundle_name})
        return self._max_observed_at

    def enqueue_macro_sync_window(self, **kwargs: object) -> str:
        self.enqueued.append(dict(kwargs))
        return f"sync-window-{len(self.enqueued)}"
