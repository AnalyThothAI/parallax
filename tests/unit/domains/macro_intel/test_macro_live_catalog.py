from __future__ import annotations

from parallax.domains.macro_intel.services.macro_live_catalog import (
    MACRO_LIVE_CATALOG,
    MACRO_LIVE_VIEW_IDS,
    concepts_for_live_view,
)


def test_live_catalog_restores_exactly_108_presentation_concepts() -> None:
    assert len(MACRO_LIVE_CATALOG) == 108
    assert MACRO_LIVE_VIEW_IDS == (
        "overview",
        "rates-inflation",
        "growth-labor",
        "liquidity-funding",
        "credit",
        "cross-asset",
    )
    assert len(concepts_for_live_view("overview")) == 9
    assert len(concepts_for_live_view("rates-inflation")) == 31
    assert len(concepts_for_live_view("growth-labor")) == 15
    assert len(concepts_for_live_view("liquidity-funding")) == 14
    assert len(concepts_for_live_view("credit")) == 22
    assert len(concepts_for_live_view("cross-asset")) == 17


def test_live_catalog_contains_only_presentation_and_math_metadata() -> None:
    forbidden = {
        "claim_effect",
        "confidence",
        "criticality",
        "direction",
        "no_call",
        "quadrant",
        "readiness",
        "risk",
        "stale_after_days",
        "sufficiency",
    }

    assert forbidden.isdisjoint(MACRO_LIVE_CATALOG["rates:dgs10"].__dataclass_fields__)
    assert MACRO_LIVE_CATALOG["rates:dgs10"].display_label == "美国 10 年期国债收益率"
    assert MACRO_LIVE_CATALOG["fed:effr"].preferred_series_key == "nyfed:EFFR"
    assert MACRO_LIVE_CATALOG["asset:spy"].change_kind == "return_pct"
    assert MACRO_LIVE_CATALOG["event:fomc_decision_next"].change_kind == "none"
