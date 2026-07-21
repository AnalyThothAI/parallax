from __future__ import annotations

from datetime import date, timedelta

import pytest

from parallax.domains.macro_intel.services.macro_assets_brief import build_macro_assets_brief
from parallax.domains.macro_intel.services.macro_module_catalog import MACRO_MODULE_IDS
from parallax.domains.macro_intel.services.macro_module_views import (
    build_macro_module_view,
    build_macro_module_views,
)


def test_build_macro_module_views_projects_every_catalog_module() -> None:
    snapshot = _snapshot()
    observations = [
        _observation("rates:dgs10", "2026-07-20", 4.25),
        _observation("rates:dgs10", "2026-07-19", 4.20),
        _observation("asset:spx", "2026-07-20", 6320.0),
    ]

    views = build_macro_module_views(snapshot=snapshot, observations=observations)

    assert tuple(views) == MACRO_MODULE_IDS
    assert all(view["snapshot"]["module_id"] == module_id for module_id, view in views.items())
    assert views["rates/yield-curve"]["primary_chart"]["status"] == "ready"
    assert views["assets"]["daily_brief"] == build_macro_assets_brief(snapshot=snapshot)


def test_build_macro_module_view_uses_only_persisted_module_observations() -> None:
    view = build_macro_module_view(
        "assets/equities",
        snapshot=_snapshot(),
        observations=[
            _observation("asset:spx", "2026-07-19", 6300.0, source="fred"),
            _observation("asset:spx", "2026-07-20", 6320.0, source="fred"),
        ],
    )

    assert [tile["concept_key"] for tile in view["tiles"]] == ["asset:spx"]
    assert view["tiles"][0]["value"] == 6320.0
    assert view["primary_chart"]["status"] == "ready"
    assert view["provenance"]["rows"] == [
        {
            "row_id": "source:fred",
            "source_label": "fred",
            "status": "ok",
            "status_label": "正常",
            "latest_observed_at": "2026-07-20",
            "concept_count": 1,
            "notes": "",
        }
    ]


def test_overview_event_flow_contains_macro_events_without_news_lane() -> None:
    event = {
        **_observation("event:fomc_decision_next", "2026-07-22", 1.0, source="official_calendar"),
        "series_key": "official_calendar:fomc_next",
        "event_metadata_json": {
            "event_code": "official_calendar:fomc_next",
            "text_value": "FOMC decision",
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        },
    }

    view = build_macro_module_view("overview", snapshot=_snapshot(), observations=[event])

    rows = view["module_read"]["market_event_flow"]["rows"]
    assert len(rows) == 1
    assert rows[0]["kind"] == "calendar"
    assert rows[0]["source"] == "official_calendar"
    assert all(row["kind"] != "news" for row in rows)


def test_module_projection_is_deterministic_for_equal_business_input() -> None:
    snapshot = _snapshot(computed_at_ms=1_779_000_000_000)
    observations = [_observation("vol:vix", "2026-07-20", 18.2)]

    assert build_macro_module_views(snapshot=snapshot, observations=observations) == build_macro_module_views(
        snapshot=snapshot,
        observations=observations,
    )


def test_route_ready_chart_payload_has_bounded_cardinality() -> None:
    start = date(2025, 1, 1)
    observations = [
        _observation("asset:spx", (start + timedelta(days=index)).isoformat(), float(index)) for index in range(300)
    ]

    view = build_macro_module_view("assets/equities", snapshot=_snapshot(), observations=observations)

    assert len(view["primary_chart"]["series"][0]["points"]) == 260


def test_present_snapshot_requires_formal_sections() -> None:
    snapshot = _snapshot()
    del snapshot["features_json"]

    with pytest.raises(ValueError, match="macro_view_snapshot_section_required:features_json"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def _snapshot(*, computed_at_ms: int = 1_779_000_000_000) -> dict[str, object]:
    return {
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-07-20",
        "status": "partial",
        "regime": "data_gap",
        "overall_score": 0.0,
        "panels_json": {},
        "indicators_json": {},
        "triggers_json": [],
        "data_gaps_json": [],
        "source_coverage_json": {"latest_observed_at": "2026-07-20"},
        "features_json": {},
        "chain_json": {},
        "scenario_json": {},
        "scorecard_json": {},
        "computed_at_ms": computed_at_ms,
    }


def _observation(
    concept_key: str,
    observed_at: str,
    value: float,
    *,
    source: str = "fred",
) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "source_name": source,
        "series_key": f"{source}:{concept_key}",
        "unit": "index",
        "frequency": "daily",
        "data_quality": "ok",
        "event_metadata_json": {},
    }
