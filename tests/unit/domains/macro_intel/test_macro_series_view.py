from __future__ import annotations

import pytest

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
            {"observed_at": "2026-05-19", "value": 4.6, "source_name": "fred", "data_quality": "ok"},
            {"observed_at": "2026-05-20", "value": 4.7, "source_name": "fred", "data_quality": "ok"},
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
            "score_participation": False,
            "concept_key": "crypto:btc",
        }
    ]
    assert view["data_gaps"] == [
        {
            "code": "insufficient_history_2_points",
            "label": "历史样本不足：至少需要 2 个点才能绘图",
            "severity": "warning",
            "score_participation": False,
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
            "label": "缺少序列数据：10Y",
            "severity": "error",
            "score_participation": False,
            "concept_key": "rates:dgs10",
        }
    ]
    assert view["data_gaps"] == [
        {
            "code": "series_missing",
            "label": "缺少序列数据：10Y",
            "severity": "error",
            "score_participation": False,
            "concept_key": "rates:dgs10",
        }
    ]


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


def _obs(
    concept_key: str,
    observed_at: str,
    value: float,
    *,
    source_name: str,
    unit: str,
    data_quality: str = "ok",
) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "source_name": source_name,
        "series_key": f"{source_name}:{concept_key}",
        "data_quality": data_quality,
    }
