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
    "rates/expectations",
    "liquidity/transmission-chain",
    "liquidity/fed-balance-sheet",
    "liquidity/operations",
    "liquidity/rrp-tga",
    "liquidity/reserves",
    "economy/gdp",
    "economy/employment",
    "economy/inflation",
    "volatility/vix",
    "credit/stress",
)

DELETED_MODULE_IDS = (
    "assets/crypto-derivatives",
    "rates/auctions",
    "fed/statements",
    "fed/speeches",
    "liquidity/global-dollar",
    "liquidity/subsurface",
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
    assert equities.subtitle == "SPX / QQQ / IWM 风险偏好确认"
    assert equities.question == "美股领导力是在确认加密 beta，还是开始拖累风险资产？"
    assert equities.section == "assets"
    assert equities.required_concepts == ("asset:spx",)
    assert "asset:spy" in equities.optional_concepts
    assert equities.chart_specs
    assert equities.table_specs
    assert "equity_breadth_missing" in equities.gap_codes
    assert "/macro/assets/bonds" in equities.related_routes
    assert "/macro/assets" not in equities.related_routes
    assert equities.chart_specs[0].chart_id == "equity_proxy_performance"
    assert equities.table_specs[0].table_id == "equity_proxy_snapshot"


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


def test_catalog_rejects_unknown_module_id_with_domain_code() -> None:
    with pytest.raises(UnsupportedMacroModuleError) as exc_info:
        get_macro_module_config("assets/not-real")

    assert exc_info.value.code == "unsupported_macro_module"
