from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from gmgn_twitter_intel.domains.macro_intel.services.macro_asset_correlation import (
    build_macro_asset_correlation,
)


def test_build_macro_asset_correlation_uses_aligned_daily_returns() -> None:
    dates = _dates(24)
    base_returns = [
        0.010,
        0.018,
        -0.006,
        0.012,
        -0.004,
        0.015,
        0.003,
        -0.011,
        0.020,
        0.006,
        -0.008,
        0.013,
        0.004,
        -0.003,
        0.017,
        -0.009,
        0.010,
        0.002,
        -0.005,
        0.014,
        0.007,
        -0.012,
        0.009,
    ]
    observations = [
        *_price_samples("asset:spy", dates, _prices_from_returns(base_returns), source="yahoo"),
        *_price_samples(
            "asset:qqq",
            dates,
            _prices_from_returns([value * 1.4 for value in base_returns]),
            source="yahoo",
        ),
        *_price_samples(
            "asset:tlt",
            dates,
            _prices_from_returns([value * -0.75 for value in base_returns]),
            source="yahoo",
        ),
    ]

    result = build_macro_asset_correlation(
        observations,
        assets=("asset:spy", "asset:qqq", "asset:tlt"),
        window="20d",
    )

    spy_qqq = _pair(result, "asset:spy", "asset:qqq")
    spy_tlt = _pair(result, "asset:spy", "asset:tlt")
    assert result["window"] == "20d"
    assert result["asof_date"] == "2026-05-20"
    assert [asset["concept_key"] for asset in result["assets"]] == [
        "asset:spy",
        "asset:qqq",
        "asset:tlt",
    ]
    assert spy_qqq["available"] is True
    assert spy_qqq["sample_size"] == 20
    assert spy_qqq["correlation"] == pytest.approx(1.0)
    assert spy_tlt["available"] is True
    assert spy_tlt["correlation"] == pytest.approx(-1.0)
    assert result["matrix"][0]["correlations"]["asset:spy"] == 1.0
    assert result["matrix"][0]["correlations"]["asset:qqq"] == pytest.approx(1.0)


def test_build_macro_asset_correlation_dedupes_by_source_priority() -> None:
    dates = _dates(24)
    returns = ([0.004, 0.009, -0.003, 0.014, 0.002, -0.005] * 4)[:-1]
    observations = [
        *_price_samples("asset:spy", dates, _prices_from_returns(returns), source="yahoo", priority=100),
        *_price_samples("asset:qqq", dates, _prices_from_returns(returns), source="yahoo", priority=100),
        _observation(
            "asset:spy",
            dates[-2],
            10_000.0,
            source="stale_vendor",
            priority=1,
            ingested_at_ms=9_999_999,
        ),
    ]

    result = build_macro_asset_correlation(
        observations,
        assets=("asset:spy", "asset:qqq"),
        window="20d",
    )

    assert _pair(result, "asset:spy", "asset:qqq")["correlation"] == pytest.approx(1.0)
    assert result["assets"][0]["sources"] == ["yahoo"]


def test_build_macro_asset_correlation_does_not_truncate_timestamp_dates() -> None:
    dates = _dates(24)
    observations = _price_samples("asset:spy", dates, _prices_from_returns(([0.004, -0.002, 0.007] * 8)[:-1]))
    observations.append(
        _observation(
            "asset:spy",
            "2026-05-21T00:00:00Z",
            999.0,
            source="timestamp_vendor",
            priority=200,
            ingested_at_ms=1_779_000_100_000,
        )
    )

    result = build_macro_asset_correlation(observations, assets=("asset:spy",), window="20d")

    assert result["asof_date"] == "2026-05-20"
    assert result["assets"][0]["latest_observed_at"] == "2026-05-20"
    assert result["assets"][0]["sources"] == ["yahoo"]


def test_build_macro_asset_correlation_marks_pairs_unavailable_when_overlap_is_too_small() -> None:
    dates = _dates(24)
    observations = [
        *_price_samples("asset:spy", dates, _prices_from_returns(([0.004, -0.002, 0.007] * 8)[:-1])),
        *_price_samples("crypto:eth", dates[-3:], [2000.0, 2015.0, 2008.0]),
    ]

    result = build_macro_asset_correlation(
        observations,
        assets=("asset:spy", "crypto:eth"),
        window="20d",
    )

    pair = _pair(result, "asset:spy", "crypto:eth")
    assert pair["available"] is False
    assert pair["sample_size"] == 2
    assert pair["reason"] == "insufficient_overlap"
    assert result["matrix"][0]["correlations"]["crypto:eth"] is None
    assert any(gap["code"] == "insufficient_overlap" for gap in result["data_gaps"])


def _pair(result: dict[str, object], left: str, right: str) -> dict[str, object]:
    pairs = result["pairs"]
    assert isinstance(pairs, list)
    for pair in pairs:
        assert isinstance(pair, dict)
        if pair["left"] == left and pair["right"] == right:
            return pair
    raise AssertionError(f"pair not found: {left}/{right}")


def _dates(count: int) -> list[date]:
    end = date(2026, 5, 20)
    return [end - timedelta(days=count - offset - 1) for offset in range(count)]


def _prices_from_returns(log_returns: list[float]) -> list[float]:
    price = 100.0
    prices = [price]
    for return_value in log_returns:
        price *= math.exp(return_value)
        prices.append(price)
    return prices


def _price_samples(
    concept_key: str,
    dates: list[date],
    values: list[float],
    *,
    source: str = "yahoo",
    priority: int = 100,
) -> list[dict[str, object]]:
    return [
        _observation(
            concept_key,
            observed_at,
            value,
            source=source,
            priority=priority,
            ingested_at_ms=1_779_000_000_000 + index,
        )
        for index, (observed_at, value) in enumerate(zip(dates, values, strict=True))
    ]


def _observation(
    concept_key: str,
    observed_at: date | str,
    value: float,
    *,
    source: str,
    priority: int,
    ingested_at_ms: int,
) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "series_key": f"series:{concept_key}",
        "source_name": source,
        "source_priority": priority,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": "price",
        "ingested_at_ms": ingested_at_ms,
    }
