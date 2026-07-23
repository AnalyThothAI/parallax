from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    build_cross_asset_rules,
    resolve_market_cutoff,
)
from parallax.domains.macro_intel.services.macro_evidence import build_evidence_index
from tests.unit.domains.macro_intel.macro_evidence_test_support import (
    COMPUTED_AT_MS,
    COMPUTED_DATE,
    flatten,
    observation,
    series,
)


def _new_york_ms(year: int, month: int, day: int, hour: int, minute: int) -> int:
    instant = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))
    return int(instant.astimezone(UTC).timestamp() * 1000)


def test_returns_require_the_shared_market_cutoff() -> None:
    observations = flatten(
        (
            series("asset:spy", [100.0 + index for index in range(21)]),
            series(
                "asset:hyg",
                [90.0 + index for index in range(21)],
                end=COMPUTED_DATE - timedelta(days=1),
            ),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)
    cutoff = resolve_market_cutoff(computed_at_ms=COMPUTED_AT_MS)

    result = build_cross_asset_rules(observations, evidence=evidence, market_cutoff=cutoff)
    spy = _asset(result, "asset:spy")
    hyg = _asset(result, "asset:hyg")

    assert cutoff == COMPUTED_DATE
    assert spy["return_20"]["status"] == "available"
    assert spy["return_20"]["sample"] == {
        "start": (COMPUTED_DATE - timedelta(days=20)).isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 21,
    }
    assert hyg["status"] == "unavailable"
    assert hyg["reason"] == "missing_at_market_cutoff"
    assert hyg["return_20"]["status"] == "unavailable"
    assert hyg["return_20"]["reason"] == "missing_at_market_cutoff"


@pytest.mark.parametrize(
    ("computed_at_ms", "expected_cutoff"),
    [
        (_new_york_ms(2026, 7, 23, 15, 59), "2026-07-22"),
        (_new_york_ms(2026, 7, 23, 16, 0), "2026-07-23"),
        (_new_york_ms(2026, 7, 25, 12, 0), "2026-07-24"),
        (_new_york_ms(2026, 4, 3, 12, 0), "2026-04-02"),
        (_new_york_ms(2026, 11, 27, 13, 0), "2026-11-27"),
        (_new_york_ms(2027, 12, 31, 16, 0), "2027-12-31"),
    ],
)
def test_market_cutoff_is_latest_completed_us_session(
    computed_at_ms: int,
    expected_cutoff: str,
) -> None:
    cutoff = resolve_market_cutoff(computed_at_ms=computed_at_ms)

    assert cutoff is not None
    assert cutoff.isoformat() == expected_cutoff


def test_correlations_align_common_price_intervals_before_returns() -> None:
    common_dates = [COMPUTED_DATE - timedelta(days=2 * offset) for offset in reversed(range(21))]
    spy_values = [100.0 * (1.01**index) for index in range(21)]
    spy = [
        observation("asset:spy", value, observed_at=day) for day, value in zip(common_dates, spy_values, strict=True)
    ]
    btc_by_date = {COMPUTED_DATE - timedelta(days=offset): 200.0 + offset for offset in range(41)}
    for day, value in zip(common_dates, spy_values, strict=True):
        btc_by_date[day] = value * 2.0
    btc = [observation("crypto:btc", value, observed_at=day) for day, value in sorted(btc_by_date.items())]
    observations = [*spy, *btc]
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_cross_asset_rules(
        observations,
        evidence=evidence,
        market_cutoff=COMPUTED_DATE,
    )
    correlation = _correlation(result["correlations_20"], "asset:spy", "crypto:btc")

    assert correlation["status"] == "available"
    assert correlation["reason"] is None
    assert correlation["correlation"] == pytest.approx(1.0)
    assert correlation["sample"] == {
        "start": common_dates[0].isoformat(),
        "end": COMPUTED_DATE.isoformat(),
        "count": 20,
    }


def test_correlations_do_not_label_partial_samples_as_full_windows() -> None:
    observations = flatten(
        (
            series("asset:spy", [100.0 + index for index in range(20)]),
            series("asset:qqq", [200.0 + index * 2 for index in range(20)]),
        )
    )
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_cross_asset_rules(
        observations,
        evidence=evidence,
        market_cutoff=COMPUTED_DATE,
    )
    correlation = _correlation(result["correlations_20"], "asset:spy", "asset:qqq")

    assert correlation["window"] == "20_sessions"
    assert correlation["status"] == "unavailable"
    assert correlation["reason"] == "insufficient_overlap"
    assert correlation["sample"]["count"] == 19


def test_invalid_current_metadata_cannot_enter_returns_or_correlations() -> None:
    observations = flatten(
        (
            series("asset:spy", [100.0 + index for index in range(21)]),
            series("asset:qqq", [200.0 + index for index in range(21)]),
        )
    )
    observations[-1]["data_quality"] = "partial"
    evidence = build_evidence_index(observations, computed_at_ms=COMPUTED_AT_MS)

    result = build_cross_asset_rules(
        observations,
        evidence=evidence,
        market_cutoff=COMPUTED_DATE,
    )
    qqq = _asset(result, "asset:qqq")
    correlation = _correlation(result["correlations_20"], "asset:spy", "asset:qqq")

    assert evidence["asset:qqq"]["status"] == "invalid"
    assert qqq["status"] == "unavailable"
    assert qqq["reason"] == "evidence_not_current"
    assert correlation["status"] == "unavailable"


def _asset(result: dict[str, object], concept_key: str) -> dict[str, object]:
    return next(item for item in result["asset_returns"] if item["concept_key"] == concept_key)  # type: ignore[union-attr]


def _correlation(
    items: object,
    left: str,
    right: str,
) -> dict[str, object]:
    assert isinstance(items, list)
    return next(item for item in items if item["left"] == left and item["right"] == right)
