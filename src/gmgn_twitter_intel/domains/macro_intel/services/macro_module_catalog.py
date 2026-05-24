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
    subtitle: str
    question: str
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
        title="宏观总览",
        subtitle="跨资产、利率、波动率与信用链条",
        question="宏观链条现在是在支持风险资产，还是提示降风险？",
        section="overview",
        required_concepts=(),
        optional_concepts=("asset:spx", "rates:dgs10", "vol:vix", "credit:hy_oas"),
        chart_specs=(MacroChartSpec("macro_regime", ("asset:spx", "rates:dgs10", "vol:vix", "credit:hy_oas")),),
        table_specs=(MacroTableSpec("panel_scorecard", ("asset:spx", "rates:dgs10", "vol:vix", "credit:hy_oas")),),
        gap_codes=(),
        related_routes=("/macro/assets", "/macro/rates", "/macro/liquidity", "/macro/volatility", "/macro/credit"),
    ),
    "assets": MacroModuleConfig(
        module_id="assets",
        route_path="/macro/assets",
        title="资产联动",
        subtitle="跨资产风险偏好与加密确认",
        question="跨资产信号是在确认 risk-on，还是开始转向防守？",
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
        title="美股风险",
        subtitle="SPX / QQQ / IWM 风险偏好确认",
        question="美股领导力是在确认加密 beta，还是开始拖累风险资产？",
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
        title="债券资产",
        subtitle="久期压力与信用确认",
        question="债券市场是在释放久期压力，还是确认避险需求？",
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
        title="商品冲击",
        subtitle="原油、黄金与通胀脉冲",
        question="商品价格是在制造通胀压力，还是只是局部供需扰动？",
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
        title="美元压力",
        subtitle="DXY 与广义美元流动性",
        question="美元是在收紧离岸流动性，还是给风险资产让路？",
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
        title="加密资产",
        subtitle="BTC / ETH 宏观 beta",
        question="BTC/ETH 是在确认宏观 risk-on，还是只是自身波动？",
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
        title="加密衍生品",
        subtitle="CEX OI、资金费率与杠杆状态",
        question="合约杠杆是在放大趋势，还是制造挤仓风险？",
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
        title="利率定价",
        subtitle="曲线、实际利率与估值压力",
        question="利率曲线是在释放风险偏好，还是继续压制估值？",
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
        title="收益率曲线",
        subtitle="2Y、5Y、10Y、30Y 与期限利差",
        question="曲线形态是在交易衰退压力，还是交易期限溢价？",
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
        title="实际利率",
        subtitle="TIPS 实际收益率与通胀补偿",
        question="实际利率是在压制成长估值，还是通胀预期主导？",
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
        title="美联储走廊",
        subtitle="政策利率、EFFR、IORB 与 SOFR",
        question="政策走廊是否稳定，还是隔夜融资开始出现压力？",
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
        title="美元流动性",
        subtitle="Fed 资产、RRP、TGA、准备金与 SOFR",
        question="美元流动性是在扩张风险承载，还是抽走市场缓冲？",
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
        title="流动性传导链",
        subtitle="资产负债表到融资市场的传导",
        question="流动性压力有没有传导到融资利率和风险资产？",
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
        title="波动率压力",
        subtitle="VIX 与缺失的期限结构确认",
        question="波动率是在容忍风险，还是开始给风险资产定价压力？",
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
        title="信用压力",
        subtitle="IG/HY OAS 与信用 ETF 确认",
        question="信用利差是在确认风险偏好，还是预警去杠杆？",
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
