from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from gmgn_twitter_intel.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from gmgn_twitter_intel.domains.macro_intel.services.macro_feature_engine import build_macro_features

COMPUTED_AT_MS = int(datetime(2026, 5, 21, 12, tzinfo=UTC).timestamp() * 1000)


def test_feature_engine_computes_latest_delta_zscore_and_percentile() -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
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
    assert len(dgs10["history"]) == 30
    assert dgs10["history"][0] == {"observed_at": "2026-04-21", "value": pytest.approx(4.41)}
    assert dgs10["history"][-1] == {"observed_at": "2026-05-20", "value": pytest.approx(4.70)}
    assert dgs10["concept_key"] == "rates:dgs10"
    assert dgs10["label"] == "10年期美债收益率"
    assert dgs10["short_label"] == "10Y"
    assert dgs10["description"] == "美国长期无风险利率基准"
    assert dgs10["unit_label"] == "%"
    assert dgs10["history_points"] == 30
    assert dgs10["history_windows"]["20d"]["ready"] is True
    assert dgs10["history_windows"]["60d"] == {"points": 30, "required_points": 61, "ready": False}
    assert dgs10["history_windows"]["252d"]["ready"] is False
    assert dgs10["score_participation"] is False
    assert dgs10["data_quality"] == "ok"
    assert dgs10["source"] == {"name": "fred", "series_key": "fred:DGS10"}
    assert dgs10["data_gaps"] == [
        {
            "code": "insufficient_history_60d",
            "label": "历史样本不足：无法计算 60 日变化",
            "severity": "warning",
            "score_participation": False,
            "remediation_hint": "回填历史后重新生成宏观投影。",
        }
    ]


def test_feature_engine_marks_insufficient_history_for_all_deltas_when_history_is_short() -> None:
    observations = _daily_observations("rates:dgs10", start=date(2026, 5, 18), values=[4.55, 4.60, 4.70])

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["latest"]["value"] == pytest.approx(4.70)
    assert dgs10["history"] == [
        {"observed_at": "2026-05-18", "value": pytest.approx(4.55)},
        {"observed_at": "2026-05-19", "value": pytest.approx(4.60)},
        {"observed_at": "2026-05-20", "value": pytest.approx(4.70)},
    ]
    assert dgs10["delta"] == {"5d": None, "20d": None, "60d": None}
    assert [gap["code"] for gap in dgs10["data_gaps"]] == [
        "insufficient_history_5d",
        "insufficient_history_20d",
        "insufficient_history_60d",
    ]
    assert [gap["label"] for gap in dgs10["data_gaps"]] == [
        "历史样本不足：无法计算 5 日变化",
        "历史样本不足：无法计算 20 日变化",
        "历史样本不足：无法计算 60 日变化",
    ]


def test_feature_engine_falls_back_to_numeric_value_and_ignores_non_numeric_values() -> None:
    observations = [
        _obs("rates:dgs10", "2026-05-17", value=4.5),
        _obs("rates:dgs10", "2026-05-18", value_numeric="not-a-number", value="n/a"),
        _obs("rates:dgs10", "2026-05-19", value=4.6),
        _obs("rates:dgs10", "2026-05-20", value=4.7),
    ]

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["latest"]["value"] == pytest.approx(4.7)
    assert dgs10["zscore"]["value"] is not None
    assert math.isfinite(dgs10["zscore"]["value"])
    assert any(gap["code"] == "non_numeric_values_1" for gap in dgs10["data_gaps"])


def test_feature_engine_does_not_truncate_timestamp_dates() -> None:
    observations = [
        {
            "concept_key": "rates:dgs10",
            "observed_at": "2026-05-21T00:00:00Z",
            "value_numeric": 4.7,
            "unit": "percent",
            "frequency": "daily",
            "data_quality": "ok",
            "source_name": "fred",
            "series_key": "fred:DGS10",
        }
    ]

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["latest"]["value"] is None
    assert dgs10["latest"]["observed_at"] is None
    assert "missing_numeric_history" in {gap["code"] for gap in dgs10["data_gaps"]}


def test_feature_engine_marks_degraded_latest_data_quality_as_gap() -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2025, 11, 16),
        values=[4.0 + i * 0.01 for i in range(186)],
        data_quality="ok",
    )
    observations[-1]["data_quality"] = "degraded"

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["data_quality"] == "degraded"
    assert {
        "code": "data_quality_degraded",
        "label": "数据质量异常：degraded",
        "severity": "warning",
        "score_participation": False,
        "remediation_hint": "补齐数据源后重新投影。",
    } in dgs10["data_gaps"]


def test_repository_observations_for_concepts_reads_projected_bounded_history() -> None:
    rows = [
        {
            "concept_key": "rates:dgs10",
            "series_key": "fred:DGS10",
            "observed_at": "2026-05-20",
            "value_numeric": 4.7,
            "source_priority": 100,
            "ingested_at_ms": 200,
        }
    ]
    conn = FakeConnection(rows)
    repo = MacroIntelRepository(conn)

    result = repo.observations_for_concepts(
        concept_keys=("rates:dgs10", "liquidity:sofr"),
        lookback_days=365,
        limit_per_series=252,
    )

    assert result == rows
    query, params = conn.executions[0]
    assert "FROM macro_observation_series_rows AS rows" in query
    assert "macro_observation_series_active_generation" not in query
    assert "generation_id" not in query
    assert "projection_version = %s" in query
    assert "concept_key = ANY(%s)" in query
    assert "observed_at >= CURRENT_DATE - %s::int" in query
    assert "series_rank <= %s" in query
    assert "FROM macro_observations" not in query
    assert "row_number() OVER" not in query
    assert "ORDER BY rows.concept_key ASC, rows.observed_at DESC" in query
    assert "series_key = ANY(%s)" not in query
    assert params == ("macro_regime_v4", ["rates:dgs10", "liquidity:sofr"], 365, 252)


def test_repository_observations_for_concepts_bounds_positive_integer_inputs() -> None:
    conn = FakeConnection([])
    repo = MacroIntelRepository(conn)

    assert repo.observations_for_concepts(concept_keys=("rates:dgs10",), lookback_days=0, limit_per_series=0) == []

    assert conn.executions[0][1] == ("macro_regime_v4", ["rates:dgs10"], 1, 1)


def test_repository_latest_snapshot_filters_current_projection_version_by_default() -> None:
    conn = LatestSnapshotConnection(
        current_row={"snapshot_id": "v4", "projection_version": "macro_regime_v4", "computed_at_ms": 100},
        any_version_row={"snapshot_id": "v1-newer", "projection_version": "macro_regime_v1", "computed_at_ms": 200},
    )
    repo = MacroIntelRepository(conn)

    assert repo.latest_snapshot() == {
        "snapshot_id": "v4",
        "projection_version": "macro_regime_v4",
        "computed_at_ms": 100,
    }
    query, params = conn.executions[0]
    assert "WHERE projection_version = %s" in query
    assert params == ("macro_regime_v4",)


def test_repository_latest_snapshot_can_read_any_projection_version_when_requested() -> None:
    conn = LatestSnapshotConnection(
        current_row={"snapshot_id": "v3", "projection_version": "macro_regime_v3", "computed_at_ms": 100},
        any_version_row={"snapshot_id": "v1-newer", "projection_version": "macro_regime_v1", "computed_at_ms": 200},
    )
    repo = MacroIntelRepository(conn)

    assert repo.latest_snapshot(projection_version=None) == {
        "snapshot_id": "v1-newer",
        "projection_version": "macro_regime_v1",
        "computed_at_ms": 200,
    }
    query, params = conn.executions[0]
    assert "WHERE projection_version = %s" not in query
    assert params == ()


def _daily_observations(
    series_key: str,
    *,
    start: date,
    values: list[float],
    data_quality: str = "ok",
) -> list[dict[str, object]]:
    return [
        _obs(series_key, (start + timedelta(days=index)).isoformat(), value_numeric=value, data_quality=data_quality)
        for index, value in enumerate(values)
    ]


def _obs(
    concept_key: str,
    observed_at: str,
    *,
    value_numeric: object | None = None,
    value: object | None = None,
    unit: str = "percent",
    data_quality: str = "ok",
) -> dict[str, object]:
    observation: dict[str, object] = {
        "source_name": "fred",
        "concept_key": concept_key,
        "series_key": "fred:DGS10",
        "source_priority": 100,
        "observed_at": observed_at,
        "unit": unit,
        "ingested_at_ms": 100,
        "data_quality": data_quality,
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

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executions.append((query, params))
        return FakeCursor(self.rows)


class LatestSnapshotConnection:
    def __init__(
        self,
        *,
        current_row: dict[str, object],
        any_version_row: dict[str, object],
    ) -> None:
        self.current_row = current_row
        self.any_version_row = any_version_row
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.executions.append((query, params))
        if params:
            return FakeCursor([self.current_row])
        return FakeCursor([self.any_version_row])


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None
