from __future__ import annotations

import pytest

from parallax.domains.macro_intel.services.macro_concept_manifest import MACRO_EVIDENCE_CONCEPTS
from parallax.domains.macro_intel.services.macro_series_view import (
    UnsupportedMacroConceptError,
    UnsupportedMacroSeriesWindowError,
    build_macro_series_view,
    macro_series_query_bounds,
)


def test_build_macro_series_view_returns_concept_keyed_series_with_provenance() -> None:
    view = build_macro_series_view(
        concept_keys=("rates:dgs10", "crypto:btc"),
        observations=[
            _obs("rates:dgs10", "2026-05-20", 4.7, source_name="fred", unit="percent"),
            _obs("rates:dgs10", "2026-05-19", 4.6, source_name="fred", unit="percent"),
            _obs("crypto:btc", "2026-05-20", 110_000, source_name="yahoo", unit="usd"),
        ],
        window="60d",
    )

    assert view["window"] == "60d"
    assert tuple(view["series"]) == ("rates:dgs10", "crypto:btc")
    assert view["series"]["rates:dgs10"] == {
        "concept_key": "rates:dgs10",
        "status": "ok",
        "unit": "percent",
        "sources": ["fred"],
        "latest_observed_at": "2026-05-20",
        "data_quality": "ok",
        "points": [
            {
                "observed_at": "2026-05-19",
                "value": 4.6,
                "source_name": "fred",
                "series_key": "fred:rates:dgs10",
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "event_metadata": {},
            },
            {
                "observed_at": "2026-05-20",
                "value": 4.7,
                "source_name": "fred",
                "series_key": "fred:rates:dgs10",
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "event_metadata": {},
            },
        ],
        "data_gaps": [],
    }
    assert view["series"]["crypto:btc"]["sources"] == ["yahoo"]
    assert view["series"]["crypto:btc"]["status"] == "insufficient_history"
    assert view["series"]["crypto:btc"]["data_gaps"] == [
        {
            "code": "insufficient_history_2_points",
            "label": "历史样本不足：至少需要 2 个点才能绘图",
            "severity": "warning",
            "concept_key": "crypto:btc",
        }
    ]
    assert view["data_gaps"] == [
        {
            "code": "insufficient_history_2_points",
            "label": "历史样本不足：至少需要 2 个点才能绘图",
            "severity": "warning",
            "concept_key": "crypto:btc",
        }
    ]


def test_build_macro_series_view_reports_missing_concept_series() -> None:
    view = build_macro_series_view(
        concept_keys=("rates:dgs10",),
        observations=[],
        window="20d",
    )

    assert view["series"]["rates:dgs10"]["points"] == []
    assert view["series"]["rates:dgs10"]["status"] == "missing"
    assert view["series"]["rates:dgs10"]["data_gaps"] == [
        {
            "code": "series_missing",
            "label": "缺少序列数据：rates:dgs10",
            "severity": "error",
            "concept_key": "rates:dgs10",
        }
    ]
    assert view["data_gaps"] == [
        {
            "code": "series_missing",
            "label": "缺少序列数据：rates:dgs10",
            "severity": "error",
            "concept_key": "rates:dgs10",
        }
    ]


def test_macro_series_view_requires_observation_quality_field() -> None:
    observation = _obs("rates:dgs10", "2026-05-20", 4.7, source_name="fred", unit="percent")
    del observation["data_quality"]

    with pytest.raises(ValueError, match="macro_series_observation_quality_required:rates:dgs10"):
        build_macro_series_view(concept_keys=("rates:dgs10",), observations=[observation], window="20d")


def test_macro_series_view_maps_only_whitelisted_event_metadata() -> None:
    observation = _obs(
        "event:fomc_decision_next",
        "2026-05-20",
        3,
        source_name="official_calendar",
        unit="days_until",
        frequency="event",
    )
    observation["event_metadata_json"] = {
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "event_time_et": "2:00 PM",
        "announcement_date": "2026-05-20",
        "reopening": False,
        "forecast": 0.25,
        "score": 99,
    }

    point = build_macro_series_view(
        concept_keys=("event:fomc_decision_next",),
        observations=[observation],
        window="20d",
    )["series"]["event:fomc_decision_next"]["points"][0]

    assert set(point) == {
        "observed_at",
        "value",
        "source_name",
        "series_key",
        "unit",
        "frequency",
        "data_quality",
        "event_metadata",
    }
    assert point["event_metadata"] == {
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "event_time_et": "2:00 PM",
        "announcement_date": "2026-05-20",
        "reopening": False,
    }


def test_macro_series_view_rejects_provider_series_keys() -> None:
    with pytest.raises(UnsupportedMacroConceptError) as exc_info:
        build_macro_series_view(concept_keys=("fred:DGS10",), observations=[], window="60d")

    assert exc_info.value.code == "unsupported_macro_concept"
    assert exc_info.value.concept_key == "fred:DGS10"


def test_macro_series_view_rejects_unknown_concepts() -> None:
    with pytest.raises(UnsupportedMacroConceptError) as exc_info:
        build_macro_series_view(concept_keys=("coinglass:BTC",), observations=[], window="60d")

    assert exc_info.value.code == "unsupported_macro_concept"
    assert exc_info.value.concept_key == "coinglass:BTC"


def test_macro_series_view_rejects_unsupported_window() -> None:
    with pytest.raises(UnsupportedMacroSeriesWindowError) as exc_info:
        build_macro_series_view(concept_keys=("rates:dgs10",), observations=[], window="5y")

    assert exc_info.value.code == "unsupported_macro_series_window"
    assert exc_info.value.window == "5y"


def test_macro_series_query_bounds_are_bounded() -> None:
    assert macro_series_query_bounds("20d") == {"lookback_days": 35, "limit_per_series": 35}
    assert macro_series_query_bounds("3y") == {"lookback_days": 1095, "limit_per_series": 800}


def test_macro_evidence_concepts_are_the_only_supported_series_keys() -> None:
    assert MACRO_EVIDENCE_CONCEPTS
    assert (
        build_macro_series_view(
            concept_keys=MACRO_EVIDENCE_CONCEPTS,
            observations=[],
            window="20d",
        )["series"].keys()
        == dict.fromkeys(MACRO_EVIDENCE_CONCEPTS).keys()
    )


def _obs(
    concept_key: str,
    observed_at: str,
    value: float,
    *,
    source_name: str,
    unit: str,
    frequency: str = "daily",
    data_quality: str = "ok",
) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "source_name": source_name,
        "series_key": f"{source_name}:{concept_key}",
        "frequency": frequency,
        "data_quality": data_quality,
        "event_metadata_json": {},
    }
