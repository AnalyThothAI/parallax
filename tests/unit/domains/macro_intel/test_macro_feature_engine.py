from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from parallax.domains.macro_intel.repositories.macro_intel_repository import MacroIntelRepository
from parallax.domains.macro_intel.services import macro_feature_engine
from parallax.domains.macro_intel.services.macro_feature_engine import build_macro_features

COMPUTED_AT_MS = int(datetime(2026, 5, 21, 12, tzinfo=UTC).timestamp() * 1000)
JUNE_9_COMPUTED_AT_MS = int(datetime(2026, 6, 9, 12, tzinfo=UTC).timestamp() * 1000)


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


@pytest.mark.parametrize("concept_key", (None, " "))
def test_feature_engine_requires_concept_key_without_silent_drop(concept_key: str | None) -> None:
    observation = _obs("rates:dgs10", "2026-05-20", value_numeric=4.7)
    if concept_key is None:
        del observation["concept_key"]
    else:
        observation["concept_key"] = concept_key

    with pytest.raises(ValueError, match="macro_feature_concept_key_required"):
        build_macro_features([observation], computed_at_ms=COMPUTED_AT_MS)


@pytest.mark.parametrize("field_name", ("label", "short_label", "description", "unit_label"))
def test_feature_engine_requires_concept_display_metadata_without_raw_fallback(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
) -> None:
    metadata = dict(macro_feature_engine.MACRO_CONCEPT_METADATA["rates:dgs10"])
    metadata.pop(field_name)
    monkeypatch.setitem(macro_feature_engine.MACRO_CONCEPT_METADATA, "rates:dgs10", metadata)
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )

    with pytest.raises(ValueError, match=f"macro_feature_metadata_{field_name}_required:rates:dgs10"):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


@pytest.mark.parametrize(
    ("field_name", "message"),
    (
        ("source_name", "macro_feature_source_name_required:rates:dgs10"),
        ("series_key", "macro_feature_series_key_required:rates:dgs10"),
    ),
)
def test_feature_engine_requires_source_metadata_without_empty_string_fallback(
    field_name: str,
    message: str,
) -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )
    for observation in observations:
        del observation[field_name]

    with pytest.raises(ValueError, match=message):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


def test_feature_engine_requires_latest_unit_without_none_fallback() -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )
    for observation in observations:
        del observation["unit"]

    with pytest.raises(ValueError, match="macro_feature_unit_required:rates:dgs10"):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


@pytest.mark.parametrize(
    ("frequency", "message"),
    (
        (None, "macro_feature_frequency_required:rates:dgs10"),
        (" ", "macro_feature_frequency_required:rates:dgs10"),
        ("minutely", "macro_feature_frequency_unknown:rates:dgs10:minutely"),
    ),
)
def test_feature_engine_requires_supported_frequency_without_daily_fallback(
    frequency: str | None,
    message: str,
) -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )
    for observation in observations:
        if frequency is None:
            del observation["frequency"]
        else:
            observation["frequency"] = frequency

    with pytest.raises(ValueError, match=message):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


def test_feature_engine_supports_intraday_crypto_derivatives_frequency_without_daily_fallback() -> None:
    observations = _daily_observations(
        "crypto_derivatives:deribit_btc_basis",
        start=date(2026, 4, 21),
        values=[0.01 + i * 0.001 for i in range(30)],
        frequency="intraday",
        series_key="deribit:BTC-PERPETUAL:basis_pct",
        source_name="deribit",
    )

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    basis = features["crypto_derivatives:deribit_btc_basis"]
    assert basis["freshness_days"] == 1
    assert basis["stale_after_days"] == 2
    assert basis["latest"] == {"value": pytest.approx(0.039), "observed_at": "2026-05-20", "unit": "percent"}
    assert basis["source"] == {"name": "deribit", "series_key": "deribit:BTC-PERPETUAL:basis_pct"}
    assert not any(gap["code"].startswith("stale_latest") for gap in basis["data_gaps"])


def test_feature_engine_supports_irregular_core_frequency_without_daily_fallback() -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 1),
        values=[4.41 + i * 0.01 for i in range(30)],
        frequency="irregular",
    )

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["freshness_days"] == 21
    assert dgs10["stale_after_days"] == 140
    assert dgs10["latest"] == {"value": pytest.approx(4.70), "observed_at": "2026-04-30", "unit": "percent"}
    assert not any(gap["code"].startswith("stale_latest") for gap in dgs10["data_gaps"])


@pytest.mark.parametrize(
    ("data_quality", "message"),
    (
        (None, "macro_feature_data_quality_required:rates:dgs10"),
        (" ", "macro_feature_data_quality_required:rates:dgs10"),
    ),
)
def test_feature_engine_requires_data_quality_without_ok_fallback(
    data_quality: str | None,
    message: str,
) -> None:
    observations = _daily_observations(
        "rates:dgs10",
        start=date(2026, 4, 21),
        values=[4.41 + i * 0.01 for i in range(30)],
    )
    for observation in observations:
        if data_quality is None:
            del observation["data_quality"]
        else:
            observation["data_quality"] = data_quality

    with pytest.raises(ValueError, match=message):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


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


def test_feature_engine_requires_value_numeric_without_raw_value_fallback() -> None:
    observations = [
        _obs("rates:dgs10", "2026-05-17", value=4.5),
        _obs("rates:dgs10", "2026-05-18", value_numeric="not-a-number", value="n/a"),
        _obs("rates:dgs10", "2026-05-19", value=4.6),
        _obs("rates:dgs10", "2026-05-20", value=4.7),
    ]

    features = build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)

    dgs10 = features["rates:dgs10"]
    assert dgs10["latest"]["value"] is None
    assert dgs10["zscore"]["value"] is None
    assert [gap["code"] for gap in dgs10["data_gaps"]] == [
        "non_numeric_values_4",
        "missing_numeric_history",
    ]


def test_feature_engine_rejects_timestamp_dates_without_truncating_to_day() -> None:
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

    with pytest.raises(ValueError, match="macro_feature_observed_at_required:rates:dgs10"):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


def test_feature_engine_rejects_malformed_observed_at_without_silent_drop() -> None:
    observations = [
        _obs("rates:dgs10", "2026-05-20", value_numeric=4.7),
        _obs("rates:dgs10", "2026-05-21T00:00:00Z", value_numeric=4.8),
    ]

    with pytest.raises(ValueError, match="macro_feature_observed_at_required:rates:dgs10"):
        build_macro_features(observations, computed_at_ms=COMPUTED_AT_MS)


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


def test_feature_engine_ages_periodic_observations_from_period_end_without_hiding_daily_staleness() -> None:
    observations = [
        _obs(
            "inflation:cpi",
            "2026-04-01",
            value_numeric=3.1,
            frequency="monthly",
            series_key="fred:CPIAUCSL",
        ),
        _obs(
            "economy:gdp_real",
            "2026-01-01",
            value_numeric=23_000,
            frequency="quarterly",
            series_key="fred:GDPC1",
        ),
        _obs(
            "commodity:wti",
            "2026-06-01",
            value_numeric=74.0,
            frequency="daily",
            series_key="fred:DCOILWTICO",
            unit="usd",
        ),
    ]

    features = build_macro_features(observations, computed_at_ms=JUNE_9_COMPUTED_AT_MS)

    cpi = features["inflation:cpi"]
    assert cpi["freshness_days"] == 40
    assert cpi["stale_after_days"] == 65
    assert not any(gap["code"].startswith("stale_latest") for gap in cpi["data_gaps"])

    gdp = features["economy:gdp_real"]
    assert gdp["freshness_days"] == 70
    assert gdp["stale_after_days"] == 140
    assert not any(gap["code"].startswith("stale_latest") for gap in gdp["data_gaps"])

    wti = features["commodity:wti"]
    assert wti["freshness_days"] == 8
    assert wti["stale_after_days"] == 7
    assert any(gap["code"] == "stale_latest_8d" for gap in wti["data_gaps"])


def test_repository_observations_for_concepts_reads_projected_bounded_history() -> None:
    rows = [
        {
            "concept_key": "rates:dgs10",
            "series_key": "fred:DGS10",
            "observed_at": "2026-05-20",
            "value_numeric": 4.7,
            "source_name": "fred",
            "unit": "percent",
            "frequency": "daily",
            "data_quality": "ok",
            "event_metadata_json": {},
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
    assert "CROSS JOIN LATERAL" in query
    assert "FROM macro_observation_series_rows AS series" in query
    assert "macro_observation_series_active_generation" not in query
    assert "generation_id" not in query
    assert "projection_version = %s" in query
    assert "series.concept_key = requested.concept_key" in query
    assert "observed_at >= CURRENT_DATE - %s::int" in query
    assert "LIMIT %s" in query
    assert "FROM macro_observations" not in query
    assert "row_number() OVER" not in query
    assert "ORDER BY rows.concept_key ASC, rows.observed_at DESC" in query
    assert "series_key = ANY(%s)" not in query
    assert params == (["rates:dgs10", "liquidity:sofr"], "macro_regime_v4", 365, 252)


def test_repository_observations_for_concepts_returns_early_for_empty_concepts() -> None:
    conn = FakeConnection([])
    repo = MacroIntelRepository(conn)

    assert repo.observations_for_concepts(concept_keys=(), lookback_days=60, limit_per_series=20) == []

    assert conn.executions == []


def test_repository_latest_snapshot_filters_current_projection_version_by_default() -> None:
    conn = LatestSnapshotConnection(
        current_row={"projection_version": "macro_regime_v4", "computed_at_ms": 100},
        any_version_row={"projection_version": "macro_regime_v1", "computed_at_ms": 200},
    )
    repo = MacroIntelRepository(conn)

    assert repo.latest_snapshot() == {
        "projection_version": "macro_regime_v4",
        "computed_at_ms": 100,
    }
    query, params = conn.executions[0]
    assert "WHERE projection_version = %s" in query
    assert params == ("macro_regime_v4",)


def test_repository_latest_snapshot_rejects_unbounded_projection_version() -> None:
    conn = LatestSnapshotConnection(
        current_row={"projection_version": "macro_regime_v3", "computed_at_ms": 100},
        any_version_row={"projection_version": "macro_regime_v1", "computed_at_ms": 200},
    )
    repo = MacroIntelRepository(conn)

    with pytest.raises(ValueError, match="projection_version is required"):
        repo.latest_snapshot(projection_version=None)

    assert conn.executions == []


def _daily_observations(
    concept_key: str,
    *,
    start: date,
    values: list[float],
    data_quality: str = "ok",
    frequency: str = "daily",
    series_key: str = "fred:DGS10",
    source_name: str = "fred",
) -> list[dict[str, object]]:
    return [
        _obs(
            concept_key,
            (start + timedelta(days=index)).isoformat(),
            value_numeric=value,
            data_quality=data_quality,
            frequency=frequency,
            series_key=series_key,
            source_name=source_name,
        )
        for index, value in enumerate(values)
    ]


def _obs(
    concept_key: str,
    observed_at: str,
    *,
    value_numeric: object | None = None,
    value: object | None = None,
    unit: str = "percent",
    frequency: str = "daily",
    series_key: str = "fred:DGS10",
    source_name: str = "fred",
    data_quality: str = "ok",
) -> dict[str, object]:
    observation: dict[str, object] = {
        "source_name": source_name,
        "concept_key": concept_key,
        "series_key": series_key,
        "source_priority": 100,
        "observed_at": observed_at,
        "unit": unit,
        "ingested_at_ms": 100,
        "frequency": frequency,
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
