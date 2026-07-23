from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from parallax.domains.macro_intel.services.macro_evidence import build_evidence_index, page_freshness
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    observation,
    series,
)


@pytest.mark.parametrize(
    ("concept_key", "values", "step_days", "expected_change", "expected_window", "expected_count"),
    [
        ("asset:spy", [100.0] * 20 + [110.0], 1, 10.0, "20_sessions", 21),
        ("labor:initial_claims", [200_000.0] * 4 + [225_000.0], 7, 25_000.0, "4_releases", 5),
        ("inflation:cpi", [100.0, 101.0], 30, 1.0, "1_release", 2),
        ("economy:gdp_real", [25_000.0, 25_100.0], 90, 100.0, "1_release", 2),
    ],
)
def test_change_windows_use_frequency_specific_periods_and_actual_samples(
    concept_key: str,
    values: list[float],
    step_days: int,
    expected_change: float,
    expected_window: str,
    expected_count: int,
) -> None:
    observations = series(concept_key, values, step_days=step_days)

    item = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)[concept_key]

    assert item["change"] == pytest.approx(expected_change)
    assert item["change_window"] == expected_window
    assert item["sample"] == {
        "start": observations[0]["observed_at"].isoformat(),
        "end": observations[-1]["observed_at"].isoformat(),
        "count": expected_count,
    }
    assert item["derivation"]["inputs"][0]["observed_at"] == observations[0]["observed_at"].isoformat()
    assert item["derivation"]["inputs"][-1]["observed_at"] == observations[-1]["observed_at"].isoformat()


def test_monthly_and_quarterly_freshness_uses_period_end_not_release_offset() -> None:
    computed_date = date(2026, 7, 23)
    observations = [
        observation("inflation:cpi", 320.0, observed_at=date(2026, 6, 1)),
        observation("economy:gdp_real", 25_000.0, observed_at=date(2026, 4, 1)),
    ]
    evidence = build_evidence_index(
        observations,
        computed_at_ms=int(datetime.combine(computed_date, datetime.min.time(), tzinfo=UTC).timestamp() * 1000),
    )

    assert evidence["inflation:cpi"]["freshness"]["age_days"] == 23
    assert evidence["economy:gdp_real"]["freshness"]["age_days"] == 23
    assert evidence["inflation:cpi"]["freshness"]["status"] == "fresh"
    assert evidence["economy:gdp_real"]["freshness"]["status"] == "fresh"


def test_stale_critical_observation_fails_page_claim_closed() -> None:
    observations = series(
        "asset:spy",
        [100.0] * 20 + [101.0],
        end=COMPUTED_DATE - timedelta(days=8),
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    freshness = page_freshness("cross_asset", evidence)

    assert evidence["asset:spy"]["status"] == "stale"
    assert freshness["status"] == "insufficient_evidence"
    assert "asset:spy" in freshness["critical_stale"]


def test_event_evidence_has_no_numeric_change_or_hidden_forecast() -> None:
    event = observation(
        "event:fomc_decision_next",
        3,
        observed_at=COMPUTED_DATE + timedelta(days=3),
    )

    item = build_evidence_index([event], computed_at_ms=COMPUTED_AT_MS)["event:fomc_decision_next"]

    assert item["status"] == "available"
    assert item["unit"] == "days_until"
    assert item["change"] is None
    assert item["change_window"] is None
    assert item["sample"]["count"] == 1
    assert item["derivation"] is None
