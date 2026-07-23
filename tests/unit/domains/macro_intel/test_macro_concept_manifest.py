from __future__ import annotations

import pytest

from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
    MACRO_EVIDENCE_CONCEPTS,
    MACRO_PAGE_IDS,
    concepts_for_page,
)


def test_manifest_owns_exact_six_pages_and_required_metadata() -> None:
    assert MACRO_PAGE_IDS == (
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    )
    assert tuple(MACRO_CONCEPT_MANIFEST) == MACRO_EVIDENCE_CONCEPTS
    assert set(MACRO_CONCEPT_MANIFEST) == {
        concept_key for page in MACRO_PAGE_IDS for concept_key in concepts_for_page(page)
    }
    for concept_key, spec in MACRO_CONCEPT_MANIFEST.items():
        assert spec.concept_key == concept_key
        assert spec.page in MACRO_PAGE_IDS
        assert spec.section
        assert spec.evidence_role
        assert spec.unit
        assert spec.source_unit
        assert spec.frequency
        assert spec.stale_after_days > 0
        assert spec.criticality in {"critical", "optional"}
        assert spec.claim_effect


@pytest.mark.parametrize(
    ("concept_key", "frequency", "change_window", "change_periods"),
    [
        ("asset:spy", "daily", "20_sessions", 20),
        ("labor:initial_claims", "weekly", "4_releases", 4),
        ("inflation:cpi", "monthly", "1_release", 1),
        ("economy:gdp_real", "quarterly", "1_release", 1),
        ("event:fomc_decision_next", "event", None, 0),
    ],
)
def test_manifest_change_windows_are_frequency_aware(
    concept_key: str,
    frequency: str,
    change_window: str | None,
    change_periods: int,
) -> None:
    spec = MACRO_CONCEPT_MANIFEST[concept_key]

    assert spec.frequency == frequency
    assert spec.legal_change_window == change_window
    assert spec.change_periods == change_periods


def test_manifest_is_immutable_and_calendar_unit_matches_current_source_contract() -> None:
    assert MACRO_CONCEPT_MANIFEST["event:fomc_decision_next"].unit == "days_until"
    assert MACRO_CONCEPT_MANIFEST["credit:hy_oas"].unit == "basis_points"
    assert MACRO_CONCEPT_MANIFEST["credit:hy_oas"].source_unit == "percent"
    assert MACRO_CONCEPT_MANIFEST["credit:hy_yield"].unit == "percent"
    assert MACRO_CONCEPT_MANIFEST["credit:hy_yield"].source_unit == "percent"

    with pytest.raises(TypeError):
        MACRO_CONCEPT_MANIFEST["asset:spy"] = MACRO_CONCEPT_MANIFEST["asset:hyg"]  # type: ignore[index]
