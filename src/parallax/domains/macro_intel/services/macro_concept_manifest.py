from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, NamedTuple

MacroPageId = Literal[
    "overview",
    "cross_asset",
    "rates_inflation",
    "growth_labor",
    "liquidity_funding",
    "credit",
]
MacroFrequency = Literal["daily", "weekly", "monthly", "quarterly", "irregular", "event"]
MacroCriticality = Literal["critical", "optional"]
MacroChangeKind = Literal["difference", "return_pct", "none"]


class _MacroConceptPolicy(NamedTuple):
    frequency: MacroFrequency
    stale_after_days: int
    legal_change_window: str | None
    change_periods: int
    change_kind: MacroChangeKind


@dataclass(frozen=True, slots=True)
class MacroConceptSpec:
    concept_key: str
    page: MacroPageId
    section: str
    evidence_role: str
    unit: str
    frequency: MacroFrequency
    stale_after_days: int
    legal_change_window: str | None
    change_periods: int
    change_kind: MacroChangeKind
    criticality: MacroCriticality
    claim_effect: str
    source_unit: str


def _concept(
    concept_key: str,
    page: MacroPageId,
    section: str,
    evidence_role: str,
    unit: str,
    frequency: MacroFrequency,
    stale_after_days: int,
    legal_change_window: str | None,
    change_periods: int,
    change_kind: MacroChangeKind,
    criticality: MacroCriticality,
    claim_effect: str,
    source_unit: str | None = None,
) -> MacroConceptSpec:
    return MacroConceptSpec(
        concept_key=concept_key,
        page=page,
        section=section,
        evidence_role=evidence_role,
        unit=unit,
        frequency=frequency,
        stale_after_days=stale_after_days,
        legal_change_window=legal_change_window,
        change_periods=change_periods,
        change_kind=change_kind,
        criticality=criticality,
        claim_effect=claim_effect,
        source_unit=source_unit or unit,
    )


_D = _MacroConceptPolicy("daily", 7, "20_sessions", 20, "difference")
_P = _MacroConceptPolicy("daily", 7, "20_sessions", 20, "return_pct")
_W = _MacroConceptPolicy("weekly", 21, "4_releases", 4, "difference")
_M = _MacroConceptPolicy("monthly", 65, "1_release", 1, "difference")
_Q = _MacroConceptPolicy("quarterly", 140, "1_release", 1, "difference")
_I = _MacroConceptPolicy("irregular", 140, "1_release", 1, "difference")
_E = _MacroConceptPolicy("event", 8, None, 0, "none")


_CONCEPTS = (
    # Overview catalysts. These rows are calendar evidence, never forecasts or surprise data.
    _concept(
        "event:fomc_decision_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:bea_gdp_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:bea_pce_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:bls_cpi_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:bls_employment_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:bls_ppi_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:treasury_auction_2y_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:treasury_auction_10y_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    _concept(
        "event:treasury_auction_30y_next",
        "overview",
        "official_catalysts",
        "catalyst",
        "days_until",
        *_E,
        "optional",
        "catalyst_only",
    ),
    # Cross-asset levels are converted to cutoff-aligned returns before comparison.
    _concept(
        "asset:spx", "cross_asset", "asset_returns", "confirmation", "index", *_P, "optional", "risk_asset_direction"
    ),
    _concept("asset:spy", "cross_asset", "asset_returns", "primary", "price", *_P, "critical", "risk_asset_direction"),
    _concept(
        "asset:qqq",
        "cross_asset",
        "asset_returns",
        "confirmation",
        "price",
        *_P,
        "optional",
        "duration_equity_direction",
    ),
    _concept(
        "asset:iwm",
        "cross_asset",
        "asset_returns",
        "confirmation",
        "price",
        *_P,
        "optional",
        "cyclical_equity_direction",
    ),
    _concept(
        "asset:tlt",
        "cross_asset",
        "asset_returns",
        "confirmation",
        "price",
        *_P,
        "optional",
        "duration_asset_direction",
    ),
    _concept("asset:hyg", "cross_asset", "asset_returns", "primary", "price", *_P, "critical", "credit_beta_direction"),
    _concept(
        "asset:lqd",
        "cross_asset",
        "asset_returns",
        "confirmation",
        "price",
        *_P,
        "optional",
        "quality_credit_direction",
    ),
    _concept(
        "asset:gld", "cross_asset", "asset_returns", "confirmation", "price", *_P, "optional", "real_asset_direction"
    ),
    _concept("asset:uso", "cross_asset", "asset_returns", "confirmation", "price", *_P, "optional", "energy_direction"),
    _concept("fx:dxy", "cross_asset", "asset_returns", "primary", "price", *_P, "critical", "dollar_direction"),
    _concept(
        "crypto:btc", "cross_asset", "asset_returns", "confirmation", "price", *_P, "optional", "crypto_beta_direction"
    ),
    _concept(
        "crypto:eth", "cross_asset", "asset_returns", "confirmation", "price", *_P, "optional", "crypto_beta_direction"
    ),
    _concept(
        "vol:vix", "cross_asset", "volatility", "primary", "index", *_D, "critical", "equity_volatility_direction"
    ),
    _concept("vol:vix1d", "cross_asset", "volatility", "context", "index", *_D, "optional", "event_volatility_context"),
    _concept(
        "vol:vix9d", "cross_asset", "volatility", "context", "index", *_D, "optional", "near_term_volatility_context"
    ),
    _concept(
        "vol:vix3m", "cross_asset", "volatility", "confirmation", "index", *_D, "optional", "term_volatility_context"
    ),
    _concept(
        "vol:move", "cross_asset", "volatility", "confirmation", "price", *_P, "optional", "rates_volatility_context"
    ),
    # Rates and inflation: tenor axes and economic releases remain separate.
    _concept("rates:dgs1mo", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs3mo", "rates_inflation", "nominal_curve", "primary", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs6mo", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs1", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs2", "rates_inflation", "nominal_curve", "primary", "percent", *_D, "critical", "curve_shape"),
    _concept("rates:dgs3", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs5", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:dgs7", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept(
        "rates:dgs10", "rates_inflation", "nominal_curve", "primary", "percent", *_D, "critical", "long_rate_direction"
    ),
    _concept("rates:dgs20", "rates_inflation", "nominal_curve", "context", "percent", *_D, "optional", "curve_shape"),
    _concept(
        "rates:dgs30", "rates_inflation", "nominal_curve", "confirmation", "percent", *_D, "optional", "curve_shape"
    ),
    _concept("rates:10y2y", "rates_inflation", "curve_slopes", "primary", "percent", *_D, "optional", "curve_shape"),
    _concept("rates:10y3m", "rates_inflation", "curve_slopes", "primary", "percent", *_D, "optional", "curve_shape"),
    _concept(
        "rates:real_5y", "rates_inflation", "real_yields", "context", "percent", *_D, "optional", "real_rate_direction"
    ),
    _concept(
        "rates:real_10y", "rates_inflation", "real_yields", "primary", "percent", *_D, "critical", "real_rate_direction"
    ),
    _concept(
        "rates:real_30y", "rates_inflation", "real_yields", "context", "percent", *_D, "optional", "real_rate_direction"
    ),
    _concept(
        "inflation:5y_breakeven",
        "rates_inflation",
        "breakevens",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "inflation_compensation",
    ),
    _concept(
        "inflation:10y_breakeven",
        "rates_inflation",
        "breakevens",
        "primary",
        "percent",
        *_D,
        "critical",
        "inflation_compensation",
    ),
    _concept(
        "inflation:5y5y_forward",
        "rates_inflation",
        "breakevens",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "inflation_anchor",
    ),
    _concept(
        "fed:target_lower",
        "rates_inflation",
        "policy_funding_corridor",
        "context",
        "percent",
        *_D,
        "optional",
        "policy_corridor",
    ),
    _concept(
        "fed:target_upper",
        "rates_inflation",
        "policy_funding_corridor",
        "context",
        "percent",
        *_D,
        "optional",
        "policy_corridor",
    ),
    _concept(
        "fed:effr",
        "rates_inflation",
        "policy_funding_corridor",
        "primary",
        "percent",
        *_D,
        "critical",
        "policy_corridor",
    ),
    _concept(
        "fed:iorb",
        "rates_inflation",
        "policy_funding_corridor",
        "primary",
        "percent",
        *_D,
        "critical",
        "policy_corridor",
    ),
    _concept(
        "liquidity:sofr",
        "rates_inflation",
        "policy_funding_corridor",
        "confirmation",
        "percent",
        *_D,
        "critical",
        "funding_corridor",
    ),
    _concept(
        "inflation:cpi",
        "rates_inflation",
        "inflation_releases",
        "primary",
        "index",
        *_M,
        "critical",
        "consumer_inflation",
    ),
    _concept(
        "inflation:core_cpi",
        "rates_inflation",
        "inflation_releases",
        "primary",
        "index",
        *_M,
        "critical",
        "consumer_inflation",
    ),
    _concept(
        "inflation:ppi",
        "rates_inflation",
        "inflation_releases",
        "confirmation",
        "index",
        *_M,
        "optional",
        "producer_inflation",
    ),
    _concept(
        "inflation:pce",
        "rates_inflation",
        "inflation_releases",
        "confirmation",
        "index",
        *_M,
        "optional",
        "consumer_inflation",
    ),
    _concept(
        "inflation:core_pce",
        "rates_inflation",
        "inflation_releases",
        "confirmation",
        "index",
        *_M,
        "optional",
        "consumer_inflation",
    ),
    _concept(
        "inflation:gdp_deflator",
        "rates_inflation",
        "inflation_releases",
        "context",
        "index",
        *_Q,
        "optional",
        "broad_inflation",
    ),
    _concept(
        "inflation:mich_1y_expectation",
        "rates_inflation",
        "inflation_releases",
        "context",
        "percent",
        *_M,
        "optional",
        "survey_inflation",
    ),
    # Growth and labor preserve leading/lagging distinctions.
    _concept(
        "economy:gdp_nowcast",
        "growth_labor",
        "growth_leading",
        "context",
        "percent_saar",
        *_I,
        "optional",
        "near_term_growth",
    ),
    _concept(
        "economy:housing_starts",
        "growth_labor",
        "growth_leading",
        "confirmation",
        "thousands_units",
        *_M,
        "optional",
        "growth_leading",
    ),
    _concept(
        "consumer:umich_sentiment",
        "growth_labor",
        "growth_leading",
        "context",
        "index",
        *_M,
        "optional",
        "consumer_leading",
    ),
    _concept(
        "economy:gdp_real",
        "growth_labor",
        "growth_lagging",
        "primary",
        "billions_chained_usd",
        *_Q,
        "critical",
        "real_growth",
    ),
    _concept(
        "economy:gdp_nominal",
        "growth_labor",
        "growth_lagging",
        "context",
        "billions_usd",
        *_Q,
        "optional",
        "nominal_growth",
    ),
    _concept(
        "economy:industrial_production",
        "growth_labor",
        "growth_lagging",
        "confirmation",
        "index",
        *_M,
        "optional",
        "industrial_growth",
    ),
    _concept(
        "consumer:retail_sales",
        "growth_labor",
        "growth_lagging",
        "confirmation",
        "millions_usd",
        *_M,
        "optional",
        "consumer_growth",
    ),
    _concept(
        "consumer:pce_real",
        "growth_labor",
        "growth_lagging",
        "confirmation",
        "billions_chained_usd",
        *_M,
        "optional",
        "consumer_growth",
    ),
    _concept(
        "consumer:saving_rate",
        "growth_labor",
        "growth_lagging",
        "context",
        "percent",
        *_M,
        "optional",
        "consumer_buffer",
    ),
    _concept(
        "labor:initial_claims",
        "growth_labor",
        "labor_leading",
        "primary",
        "number",
        *_W,
        "critical",
        "labor_deterioration",
    ),
    _concept(
        "labor:job_openings",
        "growth_labor",
        "labor_leading",
        "confirmation",
        "thousands",
        *_M,
        "optional",
        "labor_demand",
    ),
    _concept(
        "labor:payrolls",
        "growth_labor",
        "labor_lagging",
        "primary",
        "thousands_persons",
        *_M,
        "critical",
        "labor_growth",
    ),
    _concept(
        "labor:unemployment", "growth_labor", "labor_lagging", "primary", "percent", *_M, "critical", "labor_slack"
    ),
    _concept(
        "labor:avg_hourly_earnings",
        "growth_labor",
        "labor_lagging",
        "confirmation",
        "dollars_per_hour",
        *_M,
        "optional",
        "wage_pressure",
    ),
    _concept(
        "labor:participation", "growth_labor", "labor_lagging", "context", "percent", *_M, "optional", "labor_supply"
    ),
    # Liquidity and funding keep balance sheets, secured funding, and unsecured funding distinct.
    _concept(
        "liquidity:fed_assets",
        "liquidity_funding",
        "central_bank_balance_sheet",
        "primary",
        "millions_usd",
        *_W,
        "critical",
        "central_bank_balance_sheet",
    ),
    _concept(
        "liquidity:tga",
        "liquidity_funding",
        "treasury_cash",
        "primary",
        "millions_usd",
        *_D,
        "critical",
        "treasury_cash",
    ),
    _concept(
        "liquidity:on_rrp",
        "liquidity_funding",
        "reverse_repo",
        "primary",
        "billions_usd",
        *_D,
        "critical",
        "reverse_repo_usage",
    ),
    _concept(
        "liquidity:nyfed_rrp",
        "liquidity_funding",
        "reverse_repo",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "reverse_repo_operation",
    ),
    _concept(
        "liquidity:reserve_balances",
        "liquidity_funding",
        "reserves",
        "primary",
        "millions_usd",
        *_W,
        "critical",
        "reserve_balance",
    ),
    _concept(
        "liquidity:srf",
        "liquidity_funding",
        "secured_funding",
        "confirmation",
        "millions_usd",
        *_D,
        "optional",
        "srf_usage",
    ),
    _concept(
        "liquidity:bgcr",
        "liquidity_funding",
        "secured_funding",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "secured_funding_rate",
    ),
    _concept(
        "liquidity:tgcr",
        "liquidity_funding",
        "secured_funding",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "secured_funding_rate",
    ),
    _concept(
        "liquidity:sofr_volume",
        "liquidity_funding",
        "secured_funding",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "secured_funding_volume",
    ),
    _concept(
        "liquidity:bgcr_volume",
        "liquidity_funding",
        "secured_funding",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "secured_funding_volume",
    ),
    _concept(
        "liquidity:tgcr_volume",
        "liquidity_funding",
        "secured_funding",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "secured_funding_volume",
    ),
    _concept(
        "fed:obfr",
        "liquidity_funding",
        "unsecured_funding",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "unsecured_funding_rate",
    ),
    _concept(
        "fed:effr_volume",
        "liquidity_funding",
        "unsecured_funding",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "unsecured_funding_volume",
    ),
    _concept(
        "fed:obfr_volume",
        "liquidity_funding",
        "unsecured_funding",
        "context",
        "millions_usd",
        *_D,
        "optional",
        "unsecured_funding_volume",
    ),
    # Credit's six evidence layers. DGS10 is reused from Rates for the quadrant rule.
    _concept(
        "credit:ig_oas",
        "credit",
        "aggregate_spreads",
        "primary",
        "basis_points",
        *_D,
        "critical",
        "aggregate_credit_spread",
        source_unit="percent",
    ),
    _concept(
        "credit:hy_oas",
        "credit",
        "aggregate_spreads",
        "primary",
        "basis_points",
        *_D,
        "critical",
        "aggregate_credit_spread",
        source_unit="percent",
    ),
    _concept(
        "credit:aaa_oas",
        "credit",
        "rating_tail",
        "context",
        "basis_points",
        *_D,
        "optional",
        "rating_dispersion",
        source_unit="percent",
    ),
    _concept(
        "credit:aa_oas",
        "credit",
        "rating_tail",
        "context",
        "basis_points",
        *_D,
        "optional",
        "rating_dispersion",
        source_unit="percent",
    ),
    _concept(
        "credit:a_oas",
        "credit",
        "rating_tail",
        "context",
        "basis_points",
        *_D,
        "optional",
        "rating_dispersion",
        source_unit="percent",
    ),
    _concept(
        "credit:bbb_oas",
        "credit",
        "rating_tail",
        "confirmation",
        "basis_points",
        *_D,
        "optional",
        "investment_grade_tail",
        source_unit="percent",
    ),
    _concept(
        "credit:hy_bb_oas",
        "credit",
        "rating_tail",
        "confirmation",
        "basis_points",
        *_D,
        "optional",
        "high_yield_tail",
        source_unit="percent",
    ),
    _concept(
        "credit:hy_b_oas",
        "credit",
        "rating_tail",
        "confirmation",
        "basis_points",
        *_D,
        "optional",
        "high_yield_tail",
        source_unit="percent",
    ),
    _concept(
        "credit:hy_ccc_oas",
        "credit",
        "rating_tail",
        "primary",
        "basis_points",
        *_D,
        "critical",
        "high_yield_tail",
        source_unit="percent",
    ),
    _concept(
        "credit:ig_yield",
        "credit",
        "effective_yields",
        "confirmation",
        "percent",
        *_D,
        "optional",
        "investment_grade_cost",
    ),
    _concept(
        "credit:hy_yield", "credit", "effective_yields", "confirmation", "percent", *_D, "optional", "high_yield_cost"
    ),
    _concept(
        "credit:sloos_ci_large_tightening",
        "credit",
        "credit_supply",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "credit_supply",
    ),
    _concept(
        "credit:sloos_ci_small_tightening",
        "credit",
        "credit_supply",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "credit_supply",
    ),
    _concept(
        "credit:sloos_ci_large_demand",
        "credit",
        "credit_supply",
        "context",
        "percent",
        *_Q,
        "optional",
        "credit_demand",
    ),
    _concept(
        "credit:sloos_ci_small_demand",
        "credit",
        "credit_supply",
        "context",
        "percent",
        *_Q,
        "optional",
        "credit_demand",
    ),
    _concept(
        "credit:business_delinquency",
        "credit",
        "realized_damage",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "realized_damage",
    ),
    _concept(
        "credit:consumer_delinquency",
        "credit",
        "realized_damage",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "realized_damage",
    ),
    _concept(
        "credit:business_charge_off",
        "credit",
        "realized_damage",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "realized_damage",
    ),
    _concept(
        "credit:consumer_charge_off",
        "credit",
        "realized_damage",
        "confirmation",
        "percent",
        *_Q,
        "optional",
        "realized_damage",
    ),
    _concept(
        "credit:nfci",
        "credit",
        "financial_conditions_liquidity",
        "confirmation",
        "index",
        *_W,
        "optional",
        "financial_conditions",
    ),
    _concept(
        "credit:anfci",
        "credit",
        "financial_conditions_liquidity",
        "confirmation",
        "index",
        *_W,
        "optional",
        "financial_conditions",
    ),
    _concept(
        "credit:stl_stress",
        "credit",
        "financial_conditions_liquidity",
        "confirmation",
        "index",
        *_W,
        "optional",
        "financial_stress",
    ),
)


def _build_manifest(concepts: tuple[MacroConceptSpec, ...]) -> MappingProxyType[str, MacroConceptSpec]:
    manifest: dict[str, MacroConceptSpec] = {}
    for concept in concepts:
        if concept.concept_key in manifest:
            raise RuntimeError(f"macro_concept_manifest_duplicate:{concept.concept_key}")
        if concept.change_periods < 0 or concept.stale_after_days <= 0:
            raise RuntimeError(f"macro_concept_manifest_policy_invalid:{concept.concept_key}")
        manifest[concept.concept_key] = concept
    return MappingProxyType(manifest)


MACRO_CONCEPT_MANIFEST = _build_manifest(_CONCEPTS)
MACRO_EVIDENCE_CONCEPTS = tuple(MACRO_CONCEPT_MANIFEST)
MACRO_PAGE_IDS: tuple[MacroPageId, ...] = (
    "overview",
    "cross_asset",
    "rates_inflation",
    "growth_labor",
    "liquidity_funding",
    "credit",
)


def concepts_for_page(page: MacroPageId) -> tuple[str, ...]:
    return tuple(spec.concept_key for spec in MACRO_CONCEPT_MANIFEST.values() if spec.page == page)


__all__ = [
    "MACRO_CONCEPT_MANIFEST",
    "MACRO_EVIDENCE_CONCEPTS",
    "MACRO_PAGE_IDS",
    "MacroConceptSpec",
    "MacroPageId",
    "concepts_for_page",
]
