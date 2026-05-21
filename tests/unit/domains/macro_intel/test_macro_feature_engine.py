from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from gmgn_twitter_intel.domains.macro_intel.services.macro_feature_engine import build_macro_features

COMPUTED_AT_MS = int(datetime(2026, 5, 21, 12, tzinfo=UTC).timestamp() * 1000)


def test_feature_engine_computes_latest_delta_zscore_and_percentile() -> None:
    observations = _daily_observations(
        "fred:DGS10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["fred:DGS10"]
    assert dgs10["latest"] == {"value": pytest.approx(4.70), "observed_at": "2026-05-20", "unit": "percent"}
    assert dgs10["freshness_days"] == 1
    assert dgs10["delta"]["5d"] == pytest.approx(0.05)
    assert dgs10["delta"]["20d"] == pytest.approx(0.20)
    assert dgs10["delta"]["60d"] is None
    assert dgs10["zscore"]["lookback"] == 252
    assert math.isfinite(dgs10["zscore"]["value"])
    assert dgs10["percentile"]["lookback"] == 252
    assert math.isfinite(dgs10["percentile"]["value"])
    assert 0.0 <= dgs10["percentile"]["value"] <= 1.0
    assert dgs10["data_gaps"] == ["insufficient_history:60d"]


def test_feature_engine_marks_insufficient_history_for_all_deltas_when_history_is_short() -> None:
    observations = _daily_observations("fred:DGS10", start=date(2026, 5, 18), values=[4.55, 4.60, 4.70])

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["fred:DGS10"]
    assert dgs10["latest"]["value"] == pytest.approx(4.70)
    assert dgs10["delta"] == {"5d": None, "20d": None, "60d": None}
    assert dgs10["data_gaps"] == [
        "insufficient_history:5d",
        "insufficient_history:20d",
        "insufficient_history:60d",
    ]


def test_feature_engine_falls_back_to_numeric_value_and_ignores_non_numeric_values() -> None:
    observations = [
        _obs("fred:DGS10", "2026-05-17", value=4.5),
        _obs("fred:DGS10", "2026-05-18", value_numeric="not-a-number", value="n/a"),
        _obs("fred:DGS10", "2026-05-19", value=4.6),
        _obs("fred:DGS10", "2026-05-20", value=4.7),
    ]

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["fred:DGS10"]
    assert dgs10["latest"]["value"] == pytest.approx(4.7)
    assert dgs10["zscore"]["value"] is not None
    assert math.isfinite(dgs10["zscore"]["value"])
    assert "non_numeric_values:1" in dgs10["data_gaps"]


def test_repository_observations_for_series_queries_deduped_bounded_history() -> None:
    rows = [
        {
            "series_key": "fred:DGS10",
            "observed_at": "2026-05-20",
            "value_numeric": 4.7,
            "ingested_at_ms": 200,
        }
    ]
    conn = FakeConnection(rows)
    repo = MacroIntelRepository(conn)

    result = repo.observations_for_series(
        series_keys=("fred:DGS10", "nyfed:SOFR"),
        lookback_days=365,
        limit_per_series=252,
    )

    assert result == rows
    query, params = conn.executions[0]
    assert "series_key = ANY(%s)" in query
    assert "observed_at >= CURRENT_DATE - %s::int" in query
    assert "PARTITION BY series_key, observed_at" in query
    assert "ORDER BY ingested_at_ms DESC" in query
    assert "PARTITION BY series_key" in query
    assert "ORDER BY series_key ASC, observed_at DESC, ingested_at_ms DESC" in query
    assert params == (["fred:DGS10", "nyfed:SOFR"], 365, 252)


def test_repository_observations_for_series_bounds_positive_integer_inputs() -> None:
    conn = FakeConnection([])
    repo = MacroIntelRepository(conn)

    assert repo.observations_for_series(series_keys=("fred:DGS10",), lookback_days=0, limit_per_series=0) == []

    assert conn.executions[0][1] == (["fred:DGS10"], 1, 1)


def _daily_observations(series_key: str, *, start: date, values: list[float]) -> list[dict[str, object]]:
    return [
        _obs(series_key, (start + timedelta(days=index)).isoformat(), value_numeric=value)
        for index, value in enumerate(values)
    ]


def _obs(
    series_key: str,
    observed_at: str,
    *,
    value_numeric: object | None = None,
    value: object | None = None,
    unit: str = "percent",
) -> dict[str, object]:
    observation: dict[str, object] = {
        "source_name": series_key.split(":", 1)[0],
        "series_key": series_key,
        "observed_at": observed_at,
        "unit": unit,
        "ingested_at_ms": 100,
    }
    if value_numeric is not None:
        observation["value_numeric"] = value_numeric
    if value is not None:
        observation["value"] = value
    return observation


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> FakeCursor:
        self.executions.append((query, params))
        return FakeCursor(self.rows)


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows
