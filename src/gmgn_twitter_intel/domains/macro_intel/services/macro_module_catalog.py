from __future__ import annotations

from dataclasses import dataclass


class UnsupportedMacroModuleError(ValueError):
    def __init__(self, module_id: str) -> None:
        super().__init__(f"Unsupported macro module: {module_id}")
        self.code = "unsupported_macro_module"
        self.module_id = module_id


@dataclass(frozen=True)
class MacroChartSpec:
    chart_id: str
    concept_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class MacroTableSpec:
    table_id: str
    concept_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class MacroModuleConfig:
    module_id: str
    route_path: str
    title: str
    section: str
    required_concepts: tuple[str, ...]
    optional_concepts: tuple[str, ...]
    chart_specs: tuple[MacroChartSpec, ...]
    table_specs: tuple[MacroTableSpec, ...]
    gap_codes: tuple[str, ...]
    related_routes: tuple[str, ...]


MACRO_MODULE_IDS = (
    "overview",
    "assets",
    "assets/equities",
    "assets/bonds",
    "assets/commodities",
    "assets/fx",
    "assets/crypto",
    "assets/crypto-derivatives",
    "rates",
    "rates/yield-curve",
    "rates/real-rates",
    "fed",
    "liquidity",
    "liquidity/transmission-chain",
    "volatility",
    "credit",
)


_MODULE_CONFIGS = {
    "overview": MacroModuleConfig(
        module_id="overview",
        route_path="/macro",
        title="Overview",
        section="overview",
        required_concepts=(),
        optional_concepts=("asset:spx", "rates:dgs10", "vol:vix", "credit:hy_oas"),
        chart_specs=(MacroChartSpec("macro_regime", ()),),
        table_specs=(MacroTableSpec("panel_scorecard", ()),),
        gap_codes=(),
        related_routes=("/macro/assets", "/macro/rates", "/macro/liquidity", "/macro/volatility", "/macro/credit"),
    ),
    "assets": MacroModuleConfig(
        module_id="assets",
        route_path="/macro/assets",
        title="Assets",
        section="assets",
        required_concepts=(),
        optional_concepts=("asset:spx", "asset:spy", "asset:qqq", "asset:iwm", "asset:tlt", "crypto:btc"),
        chart_specs=(MacroChartSpec("asset_proxy_performance", ("asset:spy", "asset:qqq", "asset:tlt")),),
        table_specs=(MacroTableSpec("asset_proxy_snapshot", ("asset:spy", "asset:qqq", "asset:tlt")),),
        gap_codes=(),
        related_routes=(
            "/macro/assets/equities",
            "/macro/assets/bonds",
            "/macro/assets/commodities",
            "/macro/assets/fx",
            "/macro/assets/crypto",
        ),
    ),
    "assets/equities": MacroModuleConfig(
        module_id="assets/equities",
        route_path="/macro/assets/equities",
        title="Equities",
        section="assets",
        required_concepts=("asset:spx",),
        optional_concepts=("asset:spy", "asset:qqq", "asset:iwm"),
        chart_specs=(MacroChartSpec("equity_proxy_performance", ("asset:spx", "asset:spy", "asset:qqq", "asset:iwm")),),
        table_specs=(MacroTableSpec("equity_proxy_snapshot", ("asset:spx", "asset:spy", "asset:qqq", "asset:iwm")),),
        gap_codes=("equity_breadth_missing", "equity_options_gex_missing"),
        related_routes=("/macro/assets", "/macro/assets/bonds", "/macro/volatility"),
    ),
    "assets/bonds": MacroModuleConfig(
        module_id="assets/bonds",
        route_path="/macro/assets/bonds",
        title="Bonds",
        section="assets",
        required_concepts=("asset:tlt",),
        optional_concepts=("asset:hyg", "asset:lqd", "credit:hy_oas", "credit:ig_oas"),
        chart_specs=(MacroChartSpec("bond_proxy_performance", ("asset:tlt", "asset:hyg", "asset:lqd")),),
        table_specs=(MacroTableSpec("bond_proxy_snapshot", ("asset:tlt", "asset:hyg", "asset:lqd")),),
        gap_codes=("move_index_missing",),
        related_routes=("/macro/assets", "/macro/rates", "/macro/credit"),
    ),
    "assets/commodities": MacroModuleConfig(
        module_id="assets/commodities",
        route_path="/macro/assets/commodities",
        title="Commodities",
        section="assets",
        required_concepts=("commodity:wti",),
        optional_concepts=("asset:gld", "asset:uso"),
        chart_specs=(MacroChartSpec("commodity_proxy_performance", ("commodity:wti", "asset:gld", "asset:uso")),),
        table_specs=(MacroTableSpec("commodity_proxy_snapshot", ("commodity:wti", "asset:gld", "asset:uso")),),
        gap_codes=(),
        related_routes=("/macro/assets", "/macro/assets/fx"),
    ),
    "assets/fx": MacroModuleConfig(
        module_id="assets/fx",
        route_path="/macro/assets/fx",
        title="FX",
        section="assets",
        required_concepts=("fx:dxy",),
        optional_concepts=("fx:broad_dollar",),
        chart_specs=(MacroChartSpec("fx_proxy_performance", ("fx:dxy", "fx:broad_dollar")),),
        table_specs=(MacroTableSpec("fx_proxy_snapshot", ("fx:dxy", "fx:broad_dollar")),),
        gap_codes=(),
        related_routes=("/macro/assets", "/macro/liquidity"),
    ),
    "assets/crypto": MacroModuleConfig(
        module_id="assets/crypto",
        route_path="/macro/assets/crypto",
        title="Crypto",
        section="assets",
        required_concepts=("crypto:btc",),
        optional_concepts=("crypto:eth",),
        chart_specs=(MacroChartSpec("crypto_proxy_performance", ("crypto:btc", "crypto:eth")),),
        table_specs=(MacroTableSpec("crypto_proxy_snapshot", ("crypto:btc", "crypto:eth")),),
        gap_codes=("crypto_options_missing",),
        related_routes=("/macro/assets", "/macro/assets/crypto-derivatives"),
    ),
    "assets/crypto-derivatives": MacroModuleConfig(
        module_id="assets/crypto-derivatives",
        route_path="/macro/assets/crypto-derivatives",
        title="Crypto Derivatives",
        section="assets",
        required_concepts=(),
        optional_concepts=("crypto:btc", "crypto:eth"),
        chart_specs=(MacroChartSpec("crypto_derivative_context", ("crypto:btc", "crypto:eth")),),
        table_specs=(MacroTableSpec("cex_perp_board", ()),),
        gap_codes=("crypto_options_missing", "basis_missing", "etf_flows_missing"),
        related_routes=("/macro/assets/crypto", "/macro/assets"),
    ),
    "rates": MacroModuleConfig(
        module_id="rates",
        route_path="/macro/rates",
        title="Rates",
        section="rates",
        required_concepts=("rates:dgs2", "rates:dgs10"),
        optional_concepts=("rates:dgs5", "rates:dgs30", "rates:10y2y", "rates:10y3m"),
        chart_specs=(MacroChartSpec("rates_curve", ("rates:dgs2", "rates:dgs5", "rates:dgs10", "rates:dgs30")),),
        table_specs=(MacroTableSpec("rates_snapshot", ("rates:dgs2", "rates:dgs10", "rates:10y2y")),),
        gap_codes=("move_index_missing",),
        related_routes=("/macro/rates/yield-curve", "/macro/rates/real-rates", "/macro/fed"),
    ),
    "rates/yield-curve": MacroModuleConfig(
        module_id="rates/yield-curve",
        route_path="/macro/rates/yield-curve",
        title="Yield Curve",
        section="rates",
        required_concepts=("rates:dgs2", "rates:dgs10"),
        optional_concepts=("rates:dgs5", "rates:dgs30", "rates:10y2y", "rates:10y3m"),
        chart_specs=(MacroChartSpec("yield_curve", ("rates:dgs2", "rates:dgs5", "rates:dgs10", "rates:dgs30")),),
        table_specs=(MacroTableSpec("curve_spreads", ("rates:10y2y", "rates:10y3m")),),
        gap_codes=(),
        related_routes=("/macro/rates", "/macro/rates/real-rates"),
    ),
    "rates/real-rates": MacroModuleConfig(
        module_id="rates/real-rates",
        route_path="/macro/rates/real-rates",
        title="Real Rates",
        section="rates",
        required_concepts=("rates:real_10y",),
        optional_concepts=("inflation:10y_breakeven", "inflation:5y5y_forward"),
        chart_specs=(MacroChartSpec("real_rates", ("rates:real_10y", "inflation:10y_breakeven")),),
        table_specs=(MacroTableSpec("real_rates_snapshot", ("rates:real_10y", "inflation:10y_breakeven")),),
        gap_codes=(),
        related_routes=("/macro/rates", "/macro/fed"),
    ),
    "fed": MacroModuleConfig(
        module_id="fed",
        route_path="/macro/fed",
        title="Fed",
        section="fed",
        required_concepts=("fed:target_upper", "fed:target_lower", "fed:effr", "fed:iorb"),
        optional_concepts=("liquidity:sofr",),
        chart_specs=(
            MacroChartSpec(
                "fed_corridor", ("fed:target_upper", "fed:target_lower", "fed:effr", "fed:iorb", "liquidity:sofr")
            ),
        ),
        table_specs=(
            MacroTableSpec("fed_corridor_snapshot", ("fed:target_upper", "fed:target_lower", "fed:effr", "fed:iorb")),
        ),
        gap_codes=("fed_calendar_missing", "fed_speeches_missing", "fed_statement_text_missing"),
        related_routes=("/macro/rates", "/macro/liquidity"),
    ),
    "liquidity": MacroModuleConfig(
        module_id="liquidity",
        route_path="/macro/liquidity",
        title="Liquidity",
        section="liquidity",
        required_concepts=("liquidity:fed_assets", "liquidity:on_rrp", "liquidity:tga"),
        optional_concepts=("liquidity:reserve_balances", "liquidity:sofr"),
        chart_specs=(MacroChartSpec("liquidity_stack", ("liquidity:fed_assets", "liquidity:on_rrp", "liquidity:tga")),),
        table_specs=(
            MacroTableSpec("liquidity_snapshot", ("liquidity:fed_assets", "liquidity:on_rrp", "liquidity:tga")),
        ),
        gap_codes=(),
        related_routes=("/macro/liquidity/transmission-chain", "/macro/fed"),
    ),
    "liquidity/transmission-chain": MacroModuleConfig(
        module_id="liquidity/transmission-chain",
        route_path="/macro/liquidity/transmission-chain",
        title="Transmission Chain",
        section="liquidity",
        required_concepts=("liquidity:fed_assets", "liquidity:sofr"),
        optional_concepts=("liquidity:reserve_balances", "liquidity:on_rrp", "liquidity:tga"),
        chart_specs=(MacroChartSpec("transmission_chain", ("liquidity:fed_assets", "liquidity:sofr")),),
        table_specs=(MacroTableSpec("transmission_nodes", ()),),
        gap_codes=(),
        related_routes=("/macro/liquidity", "/macro/fed", "/macro/rates"),
    ),
    "volatility": MacroModuleConfig(
        module_id="volatility",
        route_path="/macro/volatility",
        title="Volatility",
        section="volatility",
        required_concepts=("vol:vix",),
        optional_concepts=(),
        chart_specs=(MacroChartSpec("volatility_context", ("vol:vix",)),),
        table_specs=(MacroTableSpec("volatility_snapshot", ("vol:vix",)),),
        gap_codes=("vix_term_structure_missing", "options_iv_rv_missing"),
        related_routes=("/macro/assets/equities", "/macro/credit"),
    ),
    "credit": MacroModuleConfig(
        module_id="credit",
        route_path="/macro/credit",
        title="Credit",
        section="credit",
        required_concepts=("credit:hy_oas", "credit:ig_oas"),
        optional_concepts=("asset:hyg", "asset:lqd"),
        chart_specs=(MacroChartSpec("credit_spreads", ("credit:hy_oas", "credit:ig_oas")),),
        table_specs=(MacroTableSpec("credit_snapshot", ("credit:hy_oas", "credit:ig_oas", "asset:hyg", "asset:lqd")),),
        gap_codes=(),
        related_routes=("/macro/volatility", "/macro/assets/bonds"),
    ),
}


def list_macro_module_configs() -> tuple[MacroModuleConfig, ...]:
    return tuple(_MODULE_CONFIGS[module_id] for module_id in MACRO_MODULE_IDS)


def get_macro_module_config(module_id: str) -> MacroModuleConfig:
    config = _MODULE_CONFIGS.get(module_id)
    if config is None:
        raise UnsupportedMacroModuleError(module_id)
    return config


__all__ = [
    "MACRO_MODULE_IDS",
    "MacroChartSpec",
    "MacroModuleConfig",
    "MacroTableSpec",
    "UnsupportedMacroModuleError",
    "get_macro_module_config",
    "list_macro_module_configs",
]
