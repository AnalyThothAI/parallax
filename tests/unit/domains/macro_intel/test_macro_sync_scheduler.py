from __future__ import annotations

from datetime import date


def test_scheduler_bootstrap_partitions_missing_history_into_bounded_windows() -> None:
    from gmgn_twitter_intel.domains.macro_intel.services.macro_sync_scheduler import (
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
    assert repo.provider_calls == []


def test_scheduler_gap_and_steady_state_enqueues_due_windows() -> None:
    from gmgn_twitter_intel.domains.macro_intel.services.macro_sync_scheduler import (
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
    assert repo.enqueued[3]["trigger_reason"].startswith("steady_overlap:")
    assert (repo.enqueued[3]["window_start"], repo.enqueued[3]["window_end"]) == (
        date(2026, 5, 20),
        date(2026, 5, 27),
    )
    assert repo.provider_calls == []


def test_scheduler_steady_overlap_identity_changes_by_interval_bucket() -> None:
    from gmgn_twitter_intel.domains.macro_intel.services.macro_sync_scheduler import (
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
    assert steady_reasons[0] == steady_reasons[1]
    assert steady_reasons[1] != steady_reasons[2]
    assert all(str(reason).startswith("steady_overlap:") for reason in steady_reasons)


class FakeRepositorySession:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel


class FakeMacroIntelRepository:
    def __init__(self, *, max_observed_at: date | None) -> None:
        self._max_observed_at = max_observed_at
        self.enqueued: list[dict[str, object]] = []
        self.provider_calls: list[object] = []

    def macro_observations_max_observed_at(self) -> date | None:
        return self._max_observed_at

    def enqueue_macro_sync_window(self, **kwargs: object) -> str:
        self.enqueued.append(dict(kwargs))
        return f"sync-window-{len(self.enqueued)}"
