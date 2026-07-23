from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from parallax.domains.macro_intel._constants import MACRO_EVIDENCE_PROJECTION_VERSION
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
    MACRO_PAGE_IDS,
    MacroPageId,
)
from parallax.domains.macro_intel.services.macro_credit_rules import build_credit_rules
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    build_cross_asset_rules,
    cross_asset_freshness,
    resolve_market_cutoff,
)
from parallax.domains.macro_intel.services.macro_dominant_shock import build_dominant_shock
from parallax.domains.macro_intel.services.macro_evidence import (
    build_evidence_index,
    claim_gap_status,
    date_value,
    evidence_sections,
    page_freshness,
    rule_hit,
    unavailable_capability,
)
from parallax.domains.macro_intel.services.macro_growth_liquidity_rules import (
    build_growth_labor_rules,
    build_liquidity_funding_rules,
)
from parallax.domains.macro_intel.services.macro_rates_inflation_rules import build_rates_inflation_rules

_PAGE_RULE_VERSIONS = {
    "overview": "macro_overview_rules_v1",
    "cross_asset": "macro_cross_asset_rules_v1",
    "rates_inflation": "macro_rates_inflation_rules_v1",
    "growth_labor": "macro_growth_labor_rules_v1",
    "liquidity_funding": "macro_liquidity_funding_rules_v1",
    "credit": "macro_credit_rules_v1",
}


def build_macro_evidence_snapshot(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, Any]:
    if isinstance(computed_at_ms, bool) or int(computed_at_ms) < 0:
        raise ValueError("macro_evidence_computed_at_ms_invalid")
    computed_at_ms = int(computed_at_ms)
    market_cutoff = resolve_market_cutoff(computed_at_ms=computed_at_ms)
    claim_observations = _claim_observations_at_cutoff(observations, cutoff=market_cutoff)
    evidence = build_evidence_index(claim_observations, computed_at_ms=computed_at_ms)
    fact_watermark = _fact_watermark(claim_observations, computed_at_ms=computed_at_ms)
    snapshot_metadata = {
        "projection_version": MACRO_EVIDENCE_PROJECTION_VERSION,
        "fact_watermark": fact_watermark,
        "market_cutoff": market_cutoff,
        "computed_at_ms": computed_at_ms,
    }

    cross_sections = evidence_sections("cross_asset", evidence)
    cross_rules = build_cross_asset_rules(claim_observations, evidence=evidence, market_cutoff=market_cutoff)
    cross_asset = _page_document(
        page_id="cross_asset",
        snapshot=snapshot_metadata,
        evidence_items=_flatten_sections(cross_sections),
        freshness=cross_asset_freshness(
            page_freshness("cross_asset", evidence),
            cross_rules,
        ),
        judgment=str(cross_rules["judgment"]),
        rule_hits=_mapping_sequence(cross_rules["rule_hits"]),
        unavailable_evidence=[
            unavailable_capability("etf_premium_discount", "source_not_ingested"),
            unavailable_capability("dealer_inventory", "source_not_ingested"),
        ],
        extra={
            "asset_returns": _attach_return_evidence(cross_rules["asset_returns"], evidence),
            "volatility": cross_sections.get("volatility", []),
            "correlations_20": cross_rules["correlations_20"],
            "correlations_60": cross_rules["correlations_60"],
            "divergences": cross_rules["divergences"],
        },
    )

    rates_sections = evidence_sections("rates_inflation", evidence)
    rates_rules = build_rates_inflation_rules(claim_observations, evidence=evidence)
    corridor = dict(rates_rules["policy_funding_corridor"])
    corridor["evidence"] = rates_sections.get("policy_funding_corridor", [])
    rates_inflation = _page_document(
        page_id="rates_inflation",
        snapshot=snapshot_metadata,
        evidence_items=_flatten_sections(rates_sections),
        freshness=page_freshness("rates_inflation", evidence),
        judgment=str(rates_rules["judgment"]),
        rule_hits=_mapping_sequence(rates_rules["rule_hits"]),
        unavailable_evidence=[
            unavailable_capability("treasury_term_premium", "source_not_ingested"),
            unavailable_capability("fedwatch", "source_not_ingested"),
        ],
        extra={
            "nominal_curve": _ordered_evidence(
                rates_sections.get("nominal_curve", []), rates_rules["nominal_tenor_order"]
            ),
            "curve_slopes": rates_rules["curve_slopes"],
            "real_yields": rates_sections.get("real_yields", []),
            "breakevens": rates_sections.get("breakevens", []),
            "term_premium": unavailable_capability("treasury_term_premium", "source_not_ingested"),
            "policy_funding_corridor": corridor,
            "inflation_releases": rates_rules["inflation_releases"],
            "curve_shape": rates_rules["curve_shape"],
        },
    )

    growth_sections = evidence_sections("growth_labor", evidence)
    growth_rules = build_growth_labor_rules(claim_observations, evidence=evidence)
    growth_labor = _page_document(
        page_id="growth_labor",
        snapshot=snapshot_metadata,
        evidence_items=_flatten_sections(growth_sections),
        freshness=page_freshness("growth_labor", evidence),
        judgment=str(growth_rules["judgment"]),
        rule_hits=_mapping_sequence(growth_rules["rule_hits"]),
        unavailable_evidence=[
            unavailable_capability("consensus_forecasts", "source_not_ingested"),
            unavailable_capability("economic_surprise", "source_not_ingested"),
        ],
        extra={
            "growth_leading": growth_sections.get("growth_leading", []),
            "growth_lagging": growth_sections.get("growth_lagging", []),
            "labor_leading": growth_sections.get("labor_leading", []),
            "labor_lagging": growth_sections.get("labor_lagging", []),
            "growth_metrics": growth_rules["growth_metrics"],
        },
    )

    liquidity_sections = evidence_sections("liquidity_funding", evidence)
    liquidity_rules = build_liquidity_funding_rules(evidence=evidence)
    net_liquidity = dict(liquidity_rules["net_liquidity"])
    liquidity_funding = _page_document(
        page_id="liquidity_funding",
        snapshot=snapshot_metadata,
        evidence_items=_with_dependencies(
            [*_flatten_sections(liquidity_sections), net_liquidity],
            evidence,
            ("liquidity:sofr", "fed:iorb", "fed:effr"),
        ),
        freshness=page_freshness(
            "liquidity_funding",
            evidence,
            extra_critical_concepts=("liquidity:sofr", "fed:iorb", "fed:effr"),
        ),
        judgment=str(liquidity_rules["judgment"]),
        rule_hits=_mapping_sequence(liquidity_rules["rule_hits"]),
        unavailable_evidence=[unavailable_capability("dealer_inventory", "source_not_ingested")],
        extra={
            "central_bank_balance_sheet": liquidity_sections.get("central_bank_balance_sheet", []),
            "treasury_cash": liquidity_sections.get("treasury_cash", []),
            "reverse_repo": liquidity_sections.get("reverse_repo", []),
            "reserves": liquidity_sections.get("reserves", []),
            "net_liquidity": net_liquidity,
            "secured_funding": {
                "evidence": _with_dependencies(
                    liquidity_sections.get("secured_funding", []),
                    evidence,
                    ("liquidity:sofr", "fed:iorb"),
                ),
                "spreads": liquidity_rules["secured_funding_spreads"],
            },
            "unsecured_funding": {
                "evidence": _with_dependencies(
                    liquidity_sections.get("unsecured_funding", []),
                    evidence,
                    ("fed:effr", "fed:iorb"),
                ),
                "spreads": liquidity_rules["unsecured_funding_spreads"],
            },
        },
    )

    credit_sections = evidence_sections("credit", evidence)
    credit_rules = build_credit_rules(evidence=evidence)
    ccc_minus_bb_oas = dict(credit_rules["ccc_minus_bb_oas"])
    credit_evidence_items = [*_flatten_sections(credit_sections), ccc_minus_bb_oas]
    credit = _page_document(
        page_id="credit",
        snapshot=snapshot_metadata,
        evidence_items=_with_dependencies(credit_evidence_items, evidence, ("rates:dgs10",)),
        freshness=page_freshness("credit", evidence, extra_critical_concepts=("rates:dgs10",)),
        judgment=str(credit_rules["judgment"]),
        rule_hits=_mapping_sequence(credit_rules["rule_hits"]),
        unavailable_evidence=[
            unavailable_capability("trace_transactions", "source_not_ingested"),
            unavailable_capability("etf_premium_discount", "source_not_ingested"),
            unavailable_capability("dealer_inventory", "source_not_ingested"),
        ],
        extra={
            "aggregate_spreads": credit_sections.get("aggregate_spreads", []),
            "rating_tail": [*credit_sections.get("rating_tail", []), ccc_minus_bb_oas],
            "effective_yields": credit_sections.get("effective_yields", []),
            "credit_supply": credit_sections.get("credit_supply", []),
            "realized_damage": credit_sections.get("realized_damage", []),
            "financial_conditions_liquidity": credit_sections.get("financial_conditions_liquidity", []),
            "treasury_spread_quadrant": credit_rules["treasury_spread_quadrant"],
            "credit_state": credit_rules["credit_state"],
        },
    )

    dominant_shock = build_dominant_shock(
        cross_asset=cross_rules,
        rates_inflation=rates_rules,
        growth_labor=growth_rules,
        liquidity_funding=liquidity_rules,
        credit=credit_rules,
    )
    overview_rule_hits = _dominant_shock_hits(dominant_shock)
    overview_evidence = _overview_evidence(evidence, dominant_shock=dominant_shock)
    official_catalysts, catalyst_gaps = _official_catalysts(observations, computed_at_ms=computed_at_ms)
    overview_freshness = _overview_freshness(
        overview_evidence,
        dominant_shock=dominant_shock,
        optional_gaps=tuple(str(item["capability"]) for item in catalyst_gaps),
    )
    overview = _page_document(
        page_id="overview",
        snapshot=snapshot_metadata,
        evidence_items=overview_evidence,
        freshness=overview_freshness,
        judgment=str(dominant_shock.get("candidate") or dominant_shock.get("status") or "insufficient_evidence"),
        rule_hits=overview_rule_hits,
        unavailable_evidence=catalyst_gaps,
        extra={
            "dominant_shock": dominant_shock,
            "official_catalysts": official_catalysts,
        },
        forced_status=(
            "insufficient_evidence"
            if dominant_shock.get("status") == "insufficient_evidence"
            else "degraded"
            if dominant_shock.get("status") in {"provisional", "divergent"}
            else None
        ),
    )

    result = {
        **snapshot_metadata,
        "overview": overview,
        "cross_asset": cross_asset,
        "rates_inflation": rates_inflation,
        "growth_labor": growth_labor,
        "liquidity_funding": liquidity_funding,
        "credit": credit,
    }
    _require_exact_pages(result)
    return result


def _page_document(
    *,
    page_id: MacroPageId,
    snapshot: Mapping[str, Any],
    evidence_items: Sequence[Mapping[str, Any]],
    freshness: Mapping[str, Any],
    judgment: str,
    rule_hits: Sequence[Mapping[str, Any]],
    unavailable_evidence: Sequence[Mapping[str, Any]],
    extra: Mapping[str, Any],
    forced_status: str | None = None,
) -> dict[str, Any]:
    freshness_status = str(freshness.get("status") or "insufficient_evidence")
    if freshness_status == "insufficient_evidence" or judgment == "insufficient_evidence":
        status = "insufficient_evidence"
    elif forced_status is not None:
        status = forced_status
    elif freshness_status == "degraded":
        status = "degraded"
    else:
        status = "supported"
    final_judgment = "insufficient_evidence" if status == "insufficient_evidence" else judgment
    hits = [dict(item) for item in rule_hits]
    drivers = [_decision_item(item) for item in hits if item.get("outcome") == "trigger"]
    confirmations = [_decision_item(item) for item in hits if item.get("outcome") == "confirmation"]
    contradictions = [_decision_item(item) for item in hits if item.get("outcome") == "contradiction"]
    invalidations = [_decision_item(item) for item in hits if item.get("outcome") == "invalidation"]
    evidence_refs = list(
        dict.fromkeys(
            [
                str(item.get("concept_key") or "")
                for item in evidence_items
                if str(item.get("status") or "") in {"available", "stale"}
            ]
            + [ref for item in hits for ref in _string_sequence(item.get("evidence_refs"))]
        )
    )
    evidence_refs = [ref for ref in evidence_refs if ref]
    upgrade, static_invalidations = _upgrade_invalidation(page_id, final_judgment)
    return {
        "page_id": page_id,
        "snapshot": dict(snapshot),
        "conclusion": {
            "status": status,
            "judgment": final_judgment,
            "rule_version": _PAGE_RULE_VERSIONS[page_id],
            "rule_hits": hits,
        },
        "horizon": "1_4_weeks",
        "drivers": drivers,
        "confirmations": confirmations,
        "contradictions": contradictions,
        "upgrade_invalidation": {
            "upgrade": upgrade,
            "invalidation": [*invalidations, *static_invalidations],
        },
        "evidence_refs": evidence_refs,
        "freshness": dict(freshness),
        "evidence": [dict(item) for item in evidence_items],
        "unavailable_evidence": [dict(item) for item in unavailable_evidence],
        **dict(extra),
    }


def _upgrade_invalidation(page_id: MacroPageId, judgment: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conditions: dict[str, tuple[tuple[str, tuple[str, ...]], tuple[str, tuple[str, ...]]]] = {
        "overview": (
            ("additional_cross_domain_confirmation", ("credit:hy_oas", "vol:vix")),
            ("primary_trigger_reversal", ("liquidity:sofr", "credit:hy_oas", "rates:dgs10")),
        ),
        "cross_asset": (
            ("credit_and_volatility_confirm", ("asset:hyg", "vol:vix")),
            ("risk_asset_direction_reverses", ("asset:spy", "asset:hyg")),
        ),
        "rates_inflation": (
            ("real_and_nominal_rates_confirm", ("rates:real_10y", "rates:dgs10")),
            ("rate_impulse_reverses", ("rates:real_10y", "rates:dgs10", "inflation:10y_breakeven")),
        ),
        "growth_labor": (
            ("leading_and_lagging_confirm", ("labor:initial_claims", "labor:payrolls", "economy:gdp_real")),
            ("labor_growth_reaccelerates", ("labor:payrolls", "labor:unemployment")),
        ),
        "liquidity_funding": (
            ("secured_and_unsecured_confirm", ("liquidity:sofr", "fed:effr", "fed:iorb")),
            ("funding_spreads_normalize", ("liquidity:sofr", "fed:iorb")),
        ),
        "credit": (
            ("aggregate_and_tail_confirm", ("credit:hy_oas", "credit:ig_oas", "credit:hy_ccc_oas")),
            ("credit_spreads_reverse", ("credit:hy_oas", "credit:ig_oas")),
        ),
    }
    upgrade, invalidation = conditions[page_id]
    if judgment == "insufficient_evidence":
        return [], [{"code": "claim_not_established", "evidence_refs": []}]
    return (
        [{"code": upgrade[0], "evidence_refs": list(upgrade[1])}],
        [{"code": invalidation[0], "evidence_refs": list(invalidation[1])}],
    )


def _official_catalysts(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    computed_date = datetime.fromtimestamp(computed_at_ms / 1000, tz=UTC).date()
    end_date = computed_date + timedelta(days=7)
    event_concepts = tuple(
        concept_key for concept_key, spec in MACRO_CONCEPT_MANIFEST.items() if spec.claim_effect == "catalyst_only"
    )
    observations_by_concept: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if concept_key not in event_concepts:
            continue
        observations_by_concept.setdefault(concept_key, []).append(observation)
    catalysts: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for concept_key in event_concepts:
        concept_observations = observations_by_concept.get(concept_key, [])
        if not concept_observations:
            gaps.append(
                unavailable_capability(
                    f"official_catalyst:{concept_key}",
                    "source_not_ingested",
                )
            )
            continue
        dated = [
            (event_date, observation)
            for observation in concept_observations
            if (event_date := date_value(observation.get("observed_at"))) is not None
        ]
        if not dated:
            gaps.append(
                unavailable_capability(
                    f"official_catalyst:{concept_key}",
                    "missing_event_date",
                )
            )
            continue
        upcoming = sorted(
            ((event_date, observation) for event_date, observation in dated if event_date >= computed_date),
            key=lambda item: item[0],
        )
        if not upcoming:
            gaps.append(
                unavailable_capability(
                    f"official_catalyst:{concept_key}",
                    "no_upcoming_event",
                )
            )
            continue
        event_date, observation = upcoming[0]
        if event_date > end_date:
            continue
        metadata = observation.get("event_metadata_json")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        event_time_et = str(metadata.get("event_time_et") or "").strip()
        event_time = event_time_et or str(metadata.get("event_time") or "").strip()
        timezone = _catalyst_timezone(metadata, event_time_et=event_time_et, event_time=event_time)
        source_url = str(metadata.get("source_url") or "").strip()
        spec = MACRO_CONCEPT_MANIFEST.get(concept_key)
        metadata_valid = (
            spec is not None
            and str(observation.get("unit") or "") == spec.source_unit
            and str(observation.get("frequency") or "") == spec.frequency
            and str(observation.get("data_quality") or "").lower() in {"ok", "ready"}
            and bool(str(observation.get("source_name") or "").strip())
            and bool(str(observation.get("series_key") or "").strip())
        )
        missing_fields = [
            field
            for field, present in (
                ("valid_observation_metadata", metadata_valid),
                ("event_time", bool(event_time)),
                ("timezone", bool(timezone)),
                ("source_url", bool(source_url)),
            )
            if not present
        ]
        if missing_fields:
            gaps.append(
                unavailable_capability(
                    f"official_catalyst:{concept_key}",
                    "missing_" + "_and_".join(missing_fields),
                )
            )
            continue
        catalysts.append(
            {
                "concept_key": concept_key,
                "event_date": event_date,
                "event_time": event_time,
                "timezone": timezone,
                "source_name": str(observation.get("source_name") or ""),
                "series_key": str(observation.get("series_key") or ""),
                "source_url": source_url,
                "release_status": "today" if event_date == computed_date else "upcoming",
                "evidence_ref": concept_key,
            }
        )
    catalysts.sort(key=lambda item: (item["event_date"], item["event_time"], item["concept_key"]))
    gaps.sort(key=lambda item: item["capability"])
    return catalysts, gaps


def _dominant_shock_hits(dominant_shock: Mapping[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    trigger = dominant_shock.get("primary_trigger")
    if isinstance(trigger, Mapping):
        hits.append(
            rule_hit(
                str(trigger.get("code") or "dominant_shock_trigger"),
                "trigger",
                _string_sequence(trigger.get("evidence_refs")),
            )
        )
    hits.extend(
        rule_hit(
            str(item.get("code") or "dominant_shock_confirmation"),
            "confirmation",
            _string_sequence(item.get("evidence_refs")),
        )
        for item in _mapping_sequence(dominant_shock.get("cross_domain_confirmations"))
    )
    hits.extend(
        rule_hit(
            str(item.get("code") or "dominant_shock_contradiction"),
            "contradiction",
            _string_sequence(item.get("evidence_refs")),
        )
        for item in _mapping_sequence(dominant_shock.get("critical_contradictions"))
    )
    return hits


def _overview_evidence(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    dominant_shock: Mapping[str, Any],
) -> list[dict[str, Any]]:
    default_keys = (
        "asset:spy",
        "asset:hyg",
        "fx:dxy",
        "vol:vix",
        "rates:dgs10",
        "rates:real_10y",
        "inflation:10y_breakeven",
        "labor:initial_claims",
        "labor:payrolls",
        "liquidity:sofr",
        "fed:iorb",
        "liquidity:reserve_balances",
        "credit:hy_oas",
        "credit:ig_oas",
        "credit:hy_ccc_oas",
    )
    hit_keys = _string_sequence(dominant_shock.get("hit_evidence"))
    keys = tuple(dict.fromkeys((*hit_keys, *default_keys)))
    return [dict(evidence[key]) for key in keys if key in evidence]


def _overview_freshness(
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    dominant_shock: Mapping[str, Any],
    optional_gaps: Sequence[str] = (),
) -> dict[str, Any]:
    critical_missing = sorted(
        str(item.get("concept_key") or "")
        for item in evidence_items
        if item.get("criticality") == "critical" and claim_gap_status(item) == "missing"
    )
    critical_stale = sorted(
        str(item.get("concept_key") or "")
        for item in evidence_items
        if item.get("criticality") == "critical" and item.get("status") == "stale"
    )
    optional_unavailable = {
        str(item.get("concept_key") or "")
        for item in evidence_items
        if item.get("criticality") != "critical" and claim_gap_status(item) in {"missing", "stale"}
    }
    optional_unavailable.update(str(item) for item in optional_gaps if str(item))
    if critical_missing or critical_stale or dominant_shock.get("status") == "insufficient_evidence":
        status = "insufficient_evidence"
    elif optional_unavailable or dominant_shock.get("status") in {"provisional", "divergent"}:
        status = "degraded"
    else:
        status = "fresh"
    return {
        "status": status,
        "critical_missing": critical_missing,
        "critical_stale": critical_stale,
        "optional_unavailable": sorted(optional_unavailable),
    }


def _claim_observations_at_cutoff(
    observations: Sequence[Mapping[str, Any]],
    *,
    cutoff: date,
) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        spec = MACRO_CONCEPT_MANIFEST.get(concept_key)
        if spec is None or spec.claim_effect == "catalyst_only":
            continue
        observed_at = date_value(observation.get("observed_at"))
        if observed_at is None or observed_at <= cutoff:
            result.append(observation)
    return result


def _fact_watermark(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> date | None:
    computed_date = datetime.fromtimestamp(computed_at_ms / 1000, tz=UTC).date()
    observed_dates = []
    for item in observations:
        concept_key = str(item.get("concept_key") or "")
        spec = MACRO_CONCEPT_MANIFEST.get(concept_key)
        observed_at = date_value(item.get("observed_at"))
        if (
            spec is not None
            and spec.claim_effect != "catalyst_only"
            and observed_at is not None
            and observed_at <= computed_date
        ):
            observed_dates.append(observed_at)
    valid_dates = [item for item in observed_dates if item is not None]
    return max(valid_dates) if valid_dates else None


def _catalyst_timezone(
    metadata: Mapping[str, Any],
    *,
    event_time_et: str,
    event_time: str,
) -> str:
    if event_time_et:
        return "America/New_York"
    explicit = str(metadata.get("timezone") or metadata.get("event_timezone") or "").strip()
    if explicit:
        return explicit
    normalized_time = event_time.upper().strip()
    if normalized_time.endswith((" ET", " EST", " EDT")):
        return "America/New_York"
    return ""


def _flatten_sections(sections: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    return [dict(item) for values in sections.values() for item in values]


def _with_dependencies(
    items: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
    concept_keys: Sequence[str],
) -> list[dict[str, Any]]:
    result = [dict(item) for item in items]
    present = {str(item.get("concept_key") or "") for item in result}
    result.extend(dict(evidence[key]) for key in concept_keys if key in evidence and key not in present)
    return result


def _attach_return_evidence(
    returns: object,
    evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for item in _mapping_sequence(returns):
        concept_key = str(item.get("concept_key") or "")
        result.append({**item, "evidence": dict(evidence[concept_key]) if concept_key in evidence else None})
    return result


def _ordered_evidence(items: object, order: object) -> list[dict[str, Any]]:
    values = {str(item.get("concept_key") or ""): item for item in _mapping_sequence(items)}
    return [dict(values[key]) for key in _string_sequence(order) if key in values]


def _decision_item(hit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": str(hit.get("rule_id") or ""),
        "evidence_refs": _string_sequence(hit.get("evidence_refs")),
    }


def _mapping_sequence(value: object) -> list[dict[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if str(item)]
    return []


def _require_exact_pages(snapshot: Mapping[str, Any]) -> None:
    pages: set[MacroPageId] = {page_id for page_id in MACRO_PAGE_IDS if page_id in snapshot}
    expected: set[MacroPageId] = set(MACRO_PAGE_IDS)
    if pages != expected:
        raise RuntimeError(
            "macro_evidence_pages_mismatch:"
            f"missing={','.join(sorted(expected - pages))}:extra={','.join(sorted(pages - expected))}"
        )


__all__ = ["build_macro_evidence_snapshot"]
