from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from parallax.domains.macro_intel._constants import MACRO_CORE_CONCEPTS, MACRO_MODULE_VIEW_VERSION
from parallax.domains.macro_intel.services.macro_module_catalog import (
    MACRO_MODULE_IDS,
    UnsupportedMacroModuleError,
    get_macro_module_config,
    list_macro_module_configs,
)

EXPECTED_MODULE_IDS = (
    "overview",
    "assets",
    "assets/equities",
    "assets/bonds",
    "assets/commodities",
    "assets/fx",
    "assets/crypto",
    "rates/fed-funds",
    "rates/yield-curve",
    "rates/real-rates",
    "liquidity/rrp-tga",
    "economy/gdp",
    "economy/employment",
    "economy/inflation",
    "volatility/vix",
    "credit/stress",
)

DELETED_MODULE_IDS = (
    "assets/correlation",
    "assets/crypto-derivatives",
    "rates/auctions",
    "rates/expectations",
    "fed/statements",
    "fed/speeches",
    "liquidity/global-dollar",
    "liquidity/reserves",
    "liquidity/subsurface",
    "liquidity/transmission-chain",
    "liquidity/operations",
    "liquidity/fed-balance-sheet",
    "economy/consumer",
    "volatility/dashboard",
    "credit/cds",
)


def test_macro_module_view_version_is_exported() -> None:
    assert MACRO_MODULE_VIEW_VERSION == "macro_module_view_v3"


def test_catalog_exposes_exact_supported_module_ids() -> None:
    assert MACRO_MODULE_IDS == EXPECTED_MODULE_IDS
    assert tuple(config.module_id for config in list_macro_module_configs()) == EXPECTED_MODULE_IDS


def test_catalog_hard_deletes_proxy_only_modules() -> None:
    deleted_route_paths = {f"/macro/{module_id}" for module_id in DELETED_MODULE_IDS}

    for module_id in DELETED_MODULE_IDS:
        with pytest.raises(UnsupportedMacroModuleError):
            get_macro_module_config(module_id)

    for config in list_macro_module_configs():
        assert config.module_id not in DELETED_MODULE_IDS
        assert config.route_path not in deleted_route_paths
        assert not (set(config.related_routes) & deleted_route_paths)


def test_catalog_configs_have_primary_chart_specs() -> None:
    assert [config.module_id for config in list_macro_module_configs() if not config.chart_specs] == []


def test_catalog_configs_have_stable_contract_fields() -> None:
    assets = get_macro_module_config("assets")
    equities = get_macro_module_config("assets/equities")

    assert assets.module_id == "assets"
    assert assets.route_path == "/macro/assets"
    assert assets.title == "大类资产"
    assert assets.section == "assets"
    assert assets.required_concepts == (
        "asset:spx",
        "rates:dgs10",
        "fx:dxy",
        "commodity:wti_futures",
        "crypto:btc",
    )
    assert assets.chart_specs[0].chart_id == "asset_cross_market_snapshot"
    assert assets.table_specs[0].table_id == "asset_group_snapshot"

    assert equities.module_id == "assets/equities"
    assert equities.route_path == "/macro/assets/equities"
    assert equities.title == "美股风险"
    assert equities.subtitle == "指数与 ETF 风险偏好确认"
    assert equities.question == "美股领导力是在确认加密 beta，还是开始拖累风险资产？"
    assert equities.section == "assets"
    assert equities.required_concepts == ("asset:spx",)
    assert "asset:spy" in equities.optional_concepts
    assert equities.chart_specs
    assert equities.table_specs
    assert "/macro/assets/bonds" in equities.related_routes
    assert "/macro/assets" not in equities.related_routes
    assert equities.chart_specs[0].chart_id == "equity_proxy_performance"
    assert equities.table_specs[0].table_id == "equity_proxy_snapshot"


def test_catalog_has_no_static_source_backlog_gap_codes() -> None:
    for config in list_macro_module_configs():
        assert not hasattr(config, "gap_codes")


@pytest.mark.parametrize(
    "module_id",
    ("rates", "fed", "liquidity", "economy", "volatility", "credit"),
)
def test_parent_macro_categories_are_not_backend_modules(module_id: str) -> None:
    with pytest.raises(UnsupportedMacroModuleError):
        get_macro_module_config(module_id)


def test_catalog_specs_are_frozen_and_use_supported_concepts() -> None:
    supported = set(MACRO_CORE_CONCEPTS)
    equities = get_macro_module_config("assets/equities")

    with pytest.raises(FrozenInstanceError):
        equities.chart_specs[0].chart_id = "mutated"  # type: ignore[misc]

    for config in list_macro_module_configs():
        for spec in (*config.chart_specs, *config.table_specs):
            assert set(spec.concept_keys) <= supported
        assert not hasattr(config, "section_board_specs")


def test_real_rates_page_includes_full_tips_and_breakeven_curve_evidence() -> None:
    real_rates = get_macro_module_config("rates/real-rates")

    real_rate_curve = {"rates:real_5y", "rates:real_10y", "rates:real_30y"}
    inflation_compensation = {"inflation:5y_breakeven", "inflation:10y_breakeven", "inflation:5y5y_forward"}
    evidence_concepts = real_rate_curve | inflation_compensation

    assert real_rates.required_concepts == ("rates:real_10y",)
    assert evidence_concepts - {"rates:real_10y"} <= set(real_rates.optional_concepts)
    assert evidence_concepts.issubset(set(real_rates.chart_specs[0].concept_keys))
    assert evidence_concepts.issubset(set(real_rates.table_specs[0].concept_keys))


def test_inflation_page_includes_pce_deflator_and_survey_expectation_evidence() -> None:
    inflation = get_macro_module_config("economy/inflation")

    inflation_breadth = {
        "inflation:gdp_deflator",
        "inflation:pce",
        "inflation:core_pce",
        "inflation:5y_breakeven",
        "inflation:10y_breakeven",
        "inflation:5y5y_forward",
        "inflation:mich_1y_expectation",
    }

    assert inflation_breadth.issubset(set(inflation.optional_concepts))
    assert inflation_breadth.issubset(set(inflation.table_specs[0].concept_keys))
    assert {"inflation:pce", "inflation:core_pce", "inflation:10y_breakeven"}.issubset(
        set(inflation.chart_specs[0].concept_keys)
    )


def test_fed_funds_page_includes_daily_effective_fed_funds_evidence() -> None:
    fed_funds = get_macro_module_config("rates/fed-funds")

    assert "fed:dff" in fed_funds.optional_concepts
    assert "fed:dff" in fed_funds.chart_specs[0].concept_keys
    assert "fed:dff" in fed_funds.table_specs[0].concept_keys


def test_fed_funds_page_absorbs_nyfed_unsecured_funding_depth() -> None:
    fed_funds = get_macro_module_config("rates/fed-funds")
    unsecured_depth = {"fed:obfr", "fed:effr_volume", "fed:obfr_volume"}

    assert unsecured_depth.issubset(set(fed_funds.optional_concepts))
    assert "fed:obfr" in fed_funds.chart_specs[0].concept_keys
    assert unsecured_depth.issubset(set(fed_funds.table_specs[0].concept_keys))


def test_volatility_vix_page_absorbs_cboe_tail_risk_depth() -> None:
    volatility = get_macro_module_config("volatility/vix")
    cboe_volatility_depth = {"vol:vix1d", "vol:vix9d", "vol:vvix", "vol:skew"}

    assert cboe_volatility_depth.issubset(set(volatility.optional_concepts))
    assert "vol:vix1d" in volatility.chart_specs[0].concept_keys
    assert "vol:vix9d" in volatility.chart_specs[0].concept_keys
    assert cboe_volatility_depth.issubset(set(volatility.table_specs[0].concept_keys))
    assert "VIX1D" in volatility.subtitle
    assert "VIX9D" in volatility.subtitle
    assert "VVIX" in volatility.subtitle
    assert "SKEW" in volatility.subtitle


def test_rrp_tga_page_absorbs_public_market_operations_evidence() -> None:
    rrp_tga = get_macro_module_config("liquidity/rrp-tga")

    absorbed_balance_sheet = {
        "liquidity:fed_assets",
        "liquidity:reserve_balances",
    }
    absorbed_operations = {
        "liquidity:nyfed_rrp",
        "liquidity:srf",
        "liquidity:bgcr",
        "liquidity:tgcr",
        "liquidity:sofr_volume",
        "liquidity:bgcr_volume",
        "liquidity:tgcr_volume",
    }
    absorbed_volume_operations = {
        "liquidity:nyfed_rrp",
        "liquidity:srf",
        "liquidity:sofr_volume",
        "liquidity:bgcr_volume",
        "liquidity:tgcr_volume",
    }

    assert absorbed_balance_sheet.issubset(set(rrp_tga.optional_concepts))
    assert absorbed_balance_sheet.issubset(set(rrp_tga.chart_specs[0].concept_keys))
    assert absorbed_balance_sheet.issubset(set(rrp_tga.table_specs[0].concept_keys))
    assert absorbed_operations.issubset(set(rrp_tga.optional_concepts))
    assert absorbed_volume_operations.issubset(set(rrp_tga.chart_specs[0].concept_keys))
    assert absorbed_operations.issubset(set(rrp_tga.table_specs[0].concept_keys))


def test_gdp_and_employment_pages_include_remaining_growth_and_labor_evidence() -> None:
    gdp = get_macro_module_config("economy/gdp")
    employment = get_macro_module_config("economy/employment")

    growth_concepts = {
        "economy:gdp_nominal",
        "economy:gdp_nowcast",
        "economy:industrial_production",
        "economy:housing_starts",
    }
    assert growth_concepts.issubset(set(gdp.optional_concepts))
    assert growth_concepts.issubset(set(gdp.table_specs[0].concept_keys))
    assert {"economy:gdp_real", "economy:gdp_nominal", "economy:industrial_production"}.issubset(
        set(gdp.chart_specs[0].concept_keys)
    )
    assert "labor:participation" in employment.optional_concepts
    assert "labor:participation" in employment.chart_specs[0].concept_keys
    assert "labor:participation" in employment.table_specs[0].concept_keys


def test_equities_page_includes_public_index_and_etf_risk_proxies() -> None:
    equities = get_macro_module_config("assets/equities")

    public_equity_indexes = {"asset:gspc", "asset:nasdaq", "asset:ndx", "asset:dji", "asset:rut"}

    assert public_equity_indexes.issubset(set(equities.optional_concepts))
    assert {"asset:spx", "asset:gspc", "asset:nasdaq", "asset:spy", "asset:qqq", "asset:iwm"}.issubset(
        set(equities.chart_specs[0].concept_keys)
    )
    assert public_equity_indexes.issubset(set(equities.table_specs[0].concept_keys))


def test_equities_page_includes_global_sector_and_positioning_proxies() -> None:
    equities = get_macro_module_config("assets/equities")

    equity_etfs = {"asset:dia", "asset:efa", "asset:eem", "asset:smh", "asset:soxx"}
    positioning = {"positioning:sp500_net_noncommercial"}
    evidence_concepts = equity_etfs | positioning

    assert evidence_concepts.issubset(set(equities.optional_concepts))
    assert {"asset:spy", "asset:qqq", "asset:iwm", "asset:dia", "asset:eem", "asset:smh"}.issubset(
        set(equities.chart_specs[0].concept_keys)
    )
    assert evidence_concepts.issubset(set(equities.table_specs[0].concept_keys))


def test_bonds_page_includes_duration_inflation_and_credit_etf_proxies() -> None:
    bonds = get_macro_module_config("assets/bonds")

    bond_etfs = {"asset:shy", "asset:ief", "asset:tip", "asset:bnd", "asset:jnk"}

    assert bond_etfs.issubset(set(bonds.optional_concepts))
    assert {"asset:shy", "asset:ief", "asset:tlt", "asset:tip", "asset:bnd"}.issubset(
        set(bonds.chart_specs[0].concept_keys)
    )
    assert bond_etfs.issubset(set(bonds.table_specs[0].concept_keys))


def test_commodities_page_includes_public_spot_futures_and_etf_proxies() -> None:
    commodities = get_macro_module_config("assets/commodities")

    commodity_spots = {"commodity:wti", "commodity:brent", "commodity:natgas"}
    commodity_futures = {
        "commodity:gold_futures",
        "commodity:silver_futures",
        "commodity:natgas_futures",
        "commodity:copper_futures",
    }
    commodity_etfs = {"asset:slv", "asset:ung", "asset:cper"}
    evidence_concepts = commodity_spots | commodity_futures | commodity_etfs | {"asset:gld", "asset:uso"}

    assert evidence_concepts.issubset(set(commodities.optional_concepts))
    assert {"commodity:wti_futures", "commodity:brent", "commodity:natgas_futures", "asset:gld"}.issubset(
        set(commodities.chart_specs[0].concept_keys)
    )
    assert evidence_concepts.issubset(set(commodities.table_specs[0].concept_keys))


def test_fx_page_includes_public_fred_yahoo_and_currency_etf_proxies() -> None:
    fx = get_macro_module_config("assets/fx")

    fred_fx = {"fx:fred_eurusd", "fx:fred_usdjpy", "fx:fred_usdcny", "fx:fred_gbpusd"}
    yahoo_fx = {"fx:eurusd", "fx:gbpusd", "fx:usdjpy", "fx:usdcny", "fx:usdkrw"}
    currency_etfs = {"asset:uup", "asset:fxe", "asset:fxy"}
    evidence_concepts = fred_fx | yahoo_fx | currency_etfs | {"fx:broad_dollar"}

    assert evidence_concepts.issubset(set(fx.optional_concepts))
    assert {"fx:dxy", "fx:broad_dollar", "asset:uup", "fx:eurusd", "fx:usdcny"}.issubset(
        set(fx.chart_specs[0].concept_keys)
    )
    assert evidence_concepts.issubset(set(fx.table_specs[0].concept_keys))


def test_crypto_page_absorbs_okx_deribit_derivatives_after_derivatives_page_deletion() -> None:
    crypto = get_macro_module_config("assets/crypto")

    derivatives = {
        "crypto_derivatives:okx_btc_oi_usd",
        "crypto_derivatives:okx_btc_funding",
        "crypto_derivatives:okx_btc_basis",
        "crypto_derivatives:okx_eth_oi_usd",
        "crypto_derivatives:okx_eth_funding",
        "crypto_derivatives:okx_eth_basis",
        "crypto_derivatives:deribit_btc_oi_usd",
        "crypto_derivatives:deribit_btc_funding_8h",
        "crypto_derivatives:deribit_btc_basis",
        "crypto_derivatives:deribit_btc_vol_index",
        "crypto_derivatives:deribit_eth_oi_usd",
        "crypto_derivatives:deribit_eth_funding_8h",
        "crypto_derivatives:deribit_eth_basis",
        "crypto_derivatives:deribit_eth_vol_index",
    }

    assert "assets/crypto-derivatives" in DELETED_MODULE_IDS
    assert derivatives.issubset(set(crypto.optional_concepts))
    assert derivatives.issubset(set(crypto.table_specs[0].concept_keys))
    assert crypto.chart_specs[0].concept_keys == ("crypto:btc", "crypto:eth")


def test_credit_stress_page_includes_sloos_supply_and_demand_evidence() -> None:
    credit = get_macro_module_config("credit/stress")

    assert "credit:sloos_ci_large_tightening" in credit.optional_concepts
    assert "credit:sloos_ci_small_tightening" in credit.optional_concepts
    assert "credit:sloos_ci_large_demand" in credit.optional_concepts
    assert "credit:sloos_ci_small_demand" in credit.optional_concepts
    assert {
        "credit:sloos_ci_large_tightening",
        "credit:sloos_ci_small_tightening",
        "credit:sloos_ci_large_demand",
        "credit:sloos_ci_small_demand",
    }.issubset(set(credit.table_specs[0].concept_keys))


def test_credit_stress_page_includes_loan_quality_evidence() -> None:
    credit = get_macro_module_config("credit/stress")

    loan_quality_concepts = {
        "credit:business_delinquency",
        "credit:consumer_delinquency",
        "credit:business_charge_off",
        "credit:consumer_charge_off",
    }
    assert loan_quality_concepts.issubset(set(credit.optional_concepts))
    assert loan_quality_concepts.issubset(set(credit.table_specs[0].concept_keys))


def test_credit_stress_page_includes_rating_ladder_and_financial_conditions_evidence() -> None:
    credit = get_macro_module_config("credit/stress")

    rating_ladder = {
        "credit:aaa_oas",
        "credit:aa_oas",
        "credit:a_oas",
        "credit:bbb_oas",
        "credit:hy_bb_oas",
        "credit:hy_b_oas",
    }
    stress_indexes = {"credit:stl_stress", "credit:nfci", "credit:anfci"}
    evidence_concepts = rating_ladder | stress_indexes

    assert evidence_concepts.issubset(set(credit.optional_concepts))
    assert evidence_concepts.issubset(set(credit.table_specs[0].concept_keys))
    assert {"credit:bbb_oas", "credit:hy_bb_oas", "credit:hy_b_oas"}.issubset(set(credit.chart_specs[0].concept_keys))


def test_volatility_vix_page_includes_short_and_mid_term_futures_proxies() -> None:
    volatility = get_macro_module_config("volatility/vix")

    vix_futures_proxies = {"asset:vixy", "asset:vixm"}
    assert vix_futures_proxies.issubset(set(volatility.optional_concepts))
    assert vix_futures_proxies.issubset(set(volatility.chart_specs[0].concept_keys))
    assert vix_futures_proxies.issubset(set(volatility.table_specs[0].concept_keys))


def test_volatility_vix_page_includes_cross_asset_volatility_indexes() -> None:
    volatility = get_macro_module_config("volatility/vix")

    cross_asset_vol = {"vol:vxn", "vol:rvx", "vol:gvz", "vol:ovx", "vol:evz"}
    assert cross_asset_vol.issubset(set(volatility.optional_concepts))
    assert cross_asset_vol.issubset(set(volatility.table_specs[0].concept_keys))
    assert {"vol:vxn", "vol:rvx", "vol:ovx"}.issubset(set(volatility.chart_specs[0].concept_keys))


def test_volatility_vix_page_includes_move_rates_volatility_proxy() -> None:
    volatility = get_macro_module_config("volatility/vix")

    assert "vol:move" in volatility.optional_concepts
    assert "vol:move" in volatility.table_specs[0].concept_keys
    assert "vol:move" in volatility.chart_specs[0].concept_keys


def test_employment_page_includes_labor_demand_and_wage_pressure_evidence() -> None:
    employment = get_macro_module_config("economy/employment")

    labor_pressure_concepts = {"labor:job_openings", "labor:avg_hourly_earnings"}
    assert labor_pressure_concepts.issubset(set(employment.optional_concepts))
    assert labor_pressure_concepts.issubset(set(employment.chart_specs[0].concept_keys))
    assert labor_pressure_concepts.issubset(set(employment.table_specs[0].concept_keys))


def test_gdp_page_absorbs_consumer_spending_evidence_after_consumer_page_deletion() -> None:
    gdp = get_macro_module_config("economy/gdp")

    consumer_concepts = {
        "consumer:pce_nominal",
        "consumer:pce_real",
        "consumer:saving_rate",
        "consumer:umich_sentiment",
    }
    assert consumer_concepts.issubset(set(gdp.optional_concepts))
    assert consumer_concepts.issubset(set(gdp.table_specs[0].concept_keys))
    assert "consumer:pce_real" in gdp.chart_specs[0].concept_keys


def test_catalog_rejects_unknown_module_id_with_domain_code() -> None:
    with pytest.raises(UnsupportedMacroModuleError) as exc_info:
        get_macro_module_config("assets/not-real")

    assert exc_info.value.code == "unsupported_macro_module"
