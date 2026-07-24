from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from tracefold.macro.observations.constants import (
    MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_PROVIDER_SERIES_SOURCE_PRIORITY,
)

MacroLiveViewId = Literal[
    "overview",
    "rates-inflation",
    "growth-labor",
    "liquidity-funding",
    "credit",
    "cross-asset",
]
MacroLiveChangeKind = Literal["difference", "return_pct", "none"]

MACRO_LIVE_VIEW_IDS: tuple[MacroLiveViewId, ...] = (
    "overview",
    "rates-inflation",
    "growth-labor",
    "liquidity-funding",
    "credit",
    "cross-asset",
)

MACRO_LIVE_VIEW_META = MappingProxyType(
    {
        "overview": ("总览与官方催化", "已知官方发布、政策会议与国债拍卖日历。"),
        "rates-inflation": ("利率与通胀", "名义曲线、实际利率、通胀补偿、政策走廊与官方通胀数据。"),
        "growth-labor": ("增长与就业", "领先与滞后的增长、消费和劳动力市场事实。"),
        "liquidity-funding": ("流动性与资金", "央行资产负债表、财政现金、准备金及有担保与无担保融资。"),
        "credit": ("信用", "总量与评级利差、有效收益率、信贷供需、已实现损伤和金融条件。"),
        "cross-asset": ("跨资产", "股票、久期、信用、黄金、原油、美元、加密资产和波动率。"),
    }
)

MACRO_LIVE_SECTION_LABELS = MappingProxyType(
    {
        "official_catalysts": "官方催化",
        "nominal_curve": "名义收益率曲线",
        "curve_slopes": "曲线利差",
        "real_yields": "实际利率",
        "breakevens": "通胀补偿",
        "policy_funding_corridor": "政策与资金走廊",
        "inflation_releases": "通胀发布",
        "growth_leading": "增长领先指标",
        "growth_lagging": "增长滞后指标",
        "labor_leading": "就业领先指标",
        "labor_lagging": "就业滞后指标",
        "central_bank_balance_sheet": "央行资产负债表",
        "treasury_cash": "财政现金",
        "reverse_repo": "逆回购",
        "reserves": "准备金",
        "secured_funding": "有担保资金",
        "unsecured_funding": "无担保资金",
        "aggregate_spreads": "总量利差",
        "rating_tail": "评级分层",
        "effective_yields": "有效收益率",
        "credit_supply": "信贷供需",
        "realized_damage": "已实现信贷损伤",
        "financial_conditions_liquidity": "金融条件",
        "asset_returns": "资产价格与收益",
        "volatility": "波动率",
        "derived": "透明计算",
        "unclassified": "未分类事实",
    }
)


@dataclass(frozen=True, slots=True)
class MacroLiveConceptSpec:
    concept_key: str
    view_id: MacroLiveViewId
    section_id: str
    section_label: str
    display_label: str
    display_order: int
    unit: str
    frequency: str
    preferred_series_key: str | None
    summary: bool
    change_kind: MacroLiveChangeKind


_RAW_CONCEPTS: tuple[tuple[str, MacroLiveViewId, str, str, str, str, str], ...] = (
    (
        "event:fomc_decision_next",
        "overview",
        "official_catalysts",
        "下一次 FOMC 利率决议",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:bea_gdp_next",
        "overview",
        "official_catalysts",
        "下一次 BEA 国内生产总值发布",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:bea_pce_next",
        "overview",
        "official_catalysts",
        "下一次 BEA 个人消费支出发布",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:bls_cpi_next",
        "overview",
        "official_catalysts",
        "下一次 BLS 消费者价格指数发布",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:bls_employment_next",
        "overview",
        "official_catalysts",
        "下一次 BLS 就业报告发布",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:bls_ppi_next",
        "overview",
        "official_catalysts",
        "下一次 BLS 生产者价格指数发布",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:treasury_auction_2y_next",
        "overview",
        "official_catalysts",
        "下一次 2 年期美国国债拍卖",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:treasury_auction_10y_next",
        "overview",
        "official_catalysts",
        "下一次 10 年期美国国债拍卖",
        "days_until",
        "event",
        "catalyst",
    ),
    (
        "event:treasury_auction_30y_next",
        "overview",
        "official_catalysts",
        "下一次 30 年期美国国债拍卖",
        "days_until",
        "event",
        "catalyst",
    ),
    ("asset:spx", "cross-asset", "asset_returns", "标普 500 指数（SPX）", "index", "daily", "confirmation"),
    ("asset:spy", "cross-asset", "asset_returns", "标普 500 ETF（SPY）", "price", "daily", "primary"),
    ("asset:qqq", "cross-asset", "asset_returns", "纳斯达克 100 ETF（QQQ）", "price", "daily", "confirmation"),
    ("asset:iwm", "cross-asset", "asset_returns", "罗素 2000 ETF（IWM）", "price", "daily", "confirmation"),
    ("asset:tlt", "cross-asset", "asset_returns", "长期美国国债 ETF（TLT）", "price", "daily", "confirmation"),
    ("asset:hyg", "cross-asset", "asset_returns", "高收益公司债 ETF（HYG）", "price", "daily", "primary"),
    ("asset:lqd", "cross-asset", "asset_returns", "投资级公司债 ETF（LQD）", "price", "daily", "confirmation"),
    ("asset:gld", "cross-asset", "asset_returns", "黄金 ETF（GLD）", "price", "daily", "confirmation"),
    ("asset:uso", "cross-asset", "asset_returns", "美国原油基金（USO）", "price", "daily", "confirmation"),
    ("fx:dxy", "cross-asset", "asset_returns", "美元指数（DXY）", "price", "daily", "primary"),
    ("crypto:btc", "cross-asset", "asset_returns", "比特币（BTC）", "price", "daily", "confirmation"),
    ("crypto:eth", "cross-asset", "asset_returns", "以太坊（ETH）", "price", "daily", "confirmation"),
    ("vol:vix", "cross-asset", "volatility", "标普 500 隐含波动率指数（VIX）", "index", "daily", "primary"),
    ("vol:vix1d", "cross-asset", "volatility", "标普 500 一日隐含波动率指数（VIX1D）", "index", "daily", "context"),
    ("vol:vix9d", "cross-asset", "volatility", "标普 500 九日隐含波动率指数（VIX9D）", "index", "daily", "context"),
    (
        "vol:vix3m",
        "cross-asset",
        "volatility",
        "标普 500 三个月隐含波动率指数（VIX3M）",
        "index",
        "daily",
        "confirmation",
    ),
    ("vol:move", "cross-asset", "volatility", "美国国债波动率指数（MOVE）", "price", "daily", "confirmation"),
    ("rates:dgs1mo", "rates-inflation", "nominal_curve", "美国 1 个月期国债收益率", "percent", "daily", "context"),
    ("rates:dgs3mo", "rates-inflation", "nominal_curve", "美国 3 个月期国债收益率", "percent", "daily", "primary"),
    ("rates:dgs6mo", "rates-inflation", "nominal_curve", "美国 6 个月期国债收益率", "percent", "daily", "context"),
    ("rates:dgs1", "rates-inflation", "nominal_curve", "美国 1 年期国债收益率", "percent", "daily", "context"),
    ("rates:dgs2", "rates-inflation", "nominal_curve", "美国 2 年期国债收益率", "percent", "daily", "primary"),
    ("rates:dgs3", "rates-inflation", "nominal_curve", "美国 3 年期国债收益率", "percent", "daily", "context"),
    ("rates:dgs5", "rates-inflation", "nominal_curve", "美国 5 年期国债收益率", "percent", "daily", "context"),
    ("rates:dgs7", "rates-inflation", "nominal_curve", "美国 7 年期国债收益率", "percent", "daily", "context"),
    ("rates:dgs10", "rates-inflation", "nominal_curve", "美国 10 年期国债收益率", "percent", "daily", "primary"),
    ("rates:dgs20", "rates-inflation", "nominal_curve", "美国 20 年期国债收益率", "percent", "daily", "context"),
    ("rates:dgs30", "rates-inflation", "nominal_curve", "美国 30 年期国债收益率", "percent", "daily", "confirmation"),
    ("rates:10y2y", "rates-inflation", "curve_slopes", "10 年期减 2 年期国债期限利差", "percent", "daily", "primary"),
    ("rates:10y3m", "rates-inflation", "curve_slopes", "10 年期减 3 个月国债期限利差", "percent", "daily", "primary"),
    ("rates:real_5y", "rates-inflation", "real_yields", "美国 5 年期实际利率", "percent", "daily", "context"),
    ("rates:real_10y", "rates-inflation", "real_yields", "美国 10 年期实际利率", "percent", "daily", "primary"),
    ("rates:real_30y", "rates-inflation", "real_yields", "美国 30 年期实际利率", "percent", "daily", "context"),
    (
        "inflation:5y_breakeven",
        "rates-inflation",
        "breakevens",
        "5 年期通胀盈亏平衡率",
        "percent",
        "daily",
        "confirmation",
    ),
    (
        "inflation:10y_breakeven",
        "rates-inflation",
        "breakevens",
        "10 年期通胀盈亏平衡率",
        "percent",
        "daily",
        "primary",
    ),
    (
        "inflation:5y5y_forward",
        "rates-inflation",
        "breakevens",
        "5 年后 5 年远期通胀补偿",
        "percent",
        "daily",
        "confirmation",
    ),
    (
        "fed:target_lower",
        "rates-inflation",
        "policy_funding_corridor",
        "联邦基金目标区间下限",
        "percent",
        "daily",
        "context",
    ),
    (
        "fed:target_upper",
        "rates-inflation",
        "policy_funding_corridor",
        "联邦基金目标区间上限",
        "percent",
        "daily",
        "context",
    ),
    (
        "fed:effr",
        "rates-inflation",
        "policy_funding_corridor",
        "有效联邦基金利率（EFFR）",
        "percent",
        "daily",
        "primary",
    ),
    ("fed:iorb", "rates-inflation", "policy_funding_corridor", "准备金余额利率（IORB）", "percent", "daily", "primary"),
    (
        "liquidity:sofr",
        "rates-inflation",
        "policy_funding_corridor",
        "担保隔夜融资利率（SOFR）",
        "percent",
        "daily",
        "confirmation",
    ),
    ("inflation:cpi", "rates-inflation", "inflation_releases", "消费者价格指数", "index", "monthly", "primary"),
    (
        "inflation:core_cpi",
        "rates-inflation",
        "inflation_releases",
        "核心消费者价格指数",
        "index",
        "monthly",
        "primary",
    ),
    ("inflation:ppi", "rates-inflation", "inflation_releases", "生产者价格指数", "index", "monthly", "confirmation"),
    (
        "inflation:pce",
        "rates-inflation",
        "inflation_releases",
        "个人消费支出价格指数",
        "index",
        "monthly",
        "confirmation",
    ),
    (
        "inflation:core_pce",
        "rates-inflation",
        "inflation_releases",
        "核心个人消费支出价格指数",
        "index",
        "monthly",
        "confirmation",
    ),
    (
        "inflation:gdp_deflator",
        "rates-inflation",
        "inflation_releases",
        "国内生产总值平减指数",
        "index",
        "quarterly",
        "context",
    ),
    (
        "inflation:mich_1y_expectation",
        "rates-inflation",
        "inflation_releases",
        "密歇根大学一年期通胀预期",
        "percent",
        "monthly",
        "context",
    ),
    (
        "economy:gdp_nowcast",
        "growth-labor",
        "growth_leading",
        "国内生产总值即时预测",
        "percent_saar",
        "irregular",
        "context",
    ),
    (
        "economy:housing_starts",
        "growth-labor",
        "growth_leading",
        "新屋开工",
        "thousands_units",
        "monthly",
        "confirmation",
    ),
    (
        "consumer:umich_sentiment",
        "growth-labor",
        "growth_leading",
        "密歇根大学消费者信心指数",
        "index",
        "monthly",
        "context",
    ),
    (
        "economy:gdp_real",
        "growth-labor",
        "growth_lagging",
        "实际国内生产总值",
        "billions_chained_usd",
        "quarterly",
        "primary",
    ),
    (
        "economy:gdp_nominal",
        "growth-labor",
        "growth_lagging",
        "名义国内生产总值",
        "billions_usd",
        "quarterly",
        "context",
    ),
    (
        "economy:industrial_production",
        "growth-labor",
        "growth_lagging",
        "工业生产指数",
        "index",
        "monthly",
        "confirmation",
    ),
    (
        "consumer:retail_sales",
        "growth-labor",
        "growth_lagging",
        "零售销售额",
        "millions_usd",
        "monthly",
        "confirmation",
    ),
    (
        "consumer:pce_real",
        "growth-labor",
        "growth_lagging",
        "实际个人消费支出",
        "billions_chained_usd",
        "monthly",
        "confirmation",
    ),
    ("consumer:saving_rate", "growth-labor", "growth_lagging", "个人储蓄率", "percent", "monthly", "context"),
    ("labor:initial_claims", "growth-labor", "labor_leading", "首次申请失业救济人数", "number", "weekly", "primary"),
    ("labor:job_openings", "growth-labor", "labor_leading", "职位空缺数", "thousands", "monthly", "confirmation"),
    ("labor:payrolls", "growth-labor", "labor_lagging", "非农就业新增", "thousands_persons", "monthly", "primary"),
    ("labor:unemployment", "growth-labor", "labor_lagging", "失业率", "percent", "monthly", "primary"),
    (
        "labor:avg_hourly_earnings",
        "growth-labor",
        "labor_lagging",
        "平均时薪",
        "dollars_per_hour",
        "monthly",
        "confirmation",
    ),
    ("labor:participation", "growth-labor", "labor_lagging", "劳动参与率", "percent", "monthly", "context"),
    (
        "liquidity:fed_assets",
        "liquidity-funding",
        "central_bank_balance_sheet",
        "美联储总资产",
        "millions_usd",
        "weekly",
        "primary",
    ),
    (
        "liquidity:tga",
        "liquidity-funding",
        "treasury_cash",
        "美国财政部一般账户（TGA）",
        "millions_usd",
        "daily",
        "primary",
    ),
    (
        "liquidity:on_rrp",
        "liquidity-funding",
        "reverse_repo",
        "隔夜逆回购余额（ON RRP）",
        "billions_usd",
        "daily",
        "primary",
    ),
    (
        "liquidity:nyfed_rrp",
        "liquidity-funding",
        "reverse_repo",
        "纽约联储逆回购操作量",
        "millions_usd",
        "daily",
        "context",
    ),
    (
        "liquidity:reserve_balances",
        "liquidity-funding",
        "reserves",
        "银行准备金余额",
        "millions_usd",
        "weekly",
        "primary",
    ),
    (
        "liquidity:srf",
        "liquidity-funding",
        "secured_funding",
        "常备回购便利使用量（SRF）",
        "millions_usd",
        "daily",
        "confirmation",
    ),
    (
        "liquidity:bgcr",
        "liquidity-funding",
        "secured_funding",
        "广义一般抵押品利率（BGCR）",
        "percent",
        "daily",
        "confirmation",
    ),
    (
        "liquidity:tgcr",
        "liquidity-funding",
        "secured_funding",
        "三方一般抵押品利率（TGCR）",
        "percent",
        "daily",
        "confirmation",
    ),
    (
        "liquidity:sofr_volume",
        "liquidity-funding",
        "secured_funding",
        "SOFR 成交量",
        "millions_usd",
        "daily",
        "context",
    ),
    (
        "liquidity:bgcr_volume",
        "liquidity-funding",
        "secured_funding",
        "BGCR 成交量",
        "millions_usd",
        "daily",
        "context",
    ),
    (
        "liquidity:tgcr_volume",
        "liquidity-funding",
        "secured_funding",
        "TGCR 成交量",
        "millions_usd",
        "daily",
        "context",
    ),
    (
        "fed:obfr",
        "liquidity-funding",
        "unsecured_funding",
        "隔夜银行融资利率（OBFR）",
        "percent",
        "daily",
        "confirmation",
    ),
    (
        "fed:effr_volume",
        "liquidity-funding",
        "unsecured_funding",
        "有效联邦基金成交量",
        "millions_usd",
        "daily",
        "context",
    ),
    (
        "fed:obfr_volume",
        "liquidity-funding",
        "unsecured_funding",
        "隔夜银行融资成交量",
        "millions_usd",
        "daily",
        "context",
    ),
    ("credit:ig_oas", "credit", "aggregate_spreads", "投资级公司债 OAS", "basis_points", "daily", "primary"),
    ("credit:hy_oas", "credit", "aggregate_spreads", "高收益公司债 OAS", "basis_points", "daily", "primary"),
    ("credit:aaa_oas", "credit", "rating_tail", "AAA 级公司债 OAS", "basis_points", "daily", "context"),
    ("credit:aa_oas", "credit", "rating_tail", "AA 级公司债 OAS", "basis_points", "daily", "context"),
    ("credit:a_oas", "credit", "rating_tail", "A 级公司债 OAS", "basis_points", "daily", "context"),
    ("credit:bbb_oas", "credit", "rating_tail", "BBB 级公司债 OAS", "basis_points", "daily", "confirmation"),
    ("credit:hy_bb_oas", "credit", "rating_tail", "高收益 BB 级公司债 OAS", "basis_points", "daily", "confirmation"),
    ("credit:hy_b_oas", "credit", "rating_tail", "高收益 B 级公司债 OAS", "basis_points", "daily", "confirmation"),
    ("credit:hy_ccc_oas", "credit", "rating_tail", "高收益 CCC 级公司债 OAS", "basis_points", "daily", "primary"),
    ("credit:ig_yield", "credit", "effective_yields", "投资级公司债有效收益率", "percent", "daily", "confirmation"),
    ("credit:hy_yield", "credit", "effective_yields", "高收益公司债有效收益率", "percent", "daily", "confirmation"),
    (
        "credit:sloos_ci_large_tightening",
        "credit",
        "credit_supply",
        "SLOOS 大中型企业贷款标准收紧",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:sloos_ci_small_tightening",
        "credit",
        "credit_supply",
        "SLOOS 小型企业贷款标准收紧",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:sloos_ci_large_demand",
        "credit",
        "credit_supply",
        "SLOOS 大中型企业贷款需求",
        "percent",
        "quarterly",
        "context",
    ),
    (
        "credit:sloos_ci_small_demand",
        "credit",
        "credit_supply",
        "SLOOS 小型企业贷款需求",
        "percent",
        "quarterly",
        "context",
    ),
    (
        "credit:business_delinquency",
        "credit",
        "realized_damage",
        "商业贷款逾期率",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:consumer_delinquency",
        "credit",
        "realized_damage",
        "消费贷款逾期率",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:business_charge_off",
        "credit",
        "realized_damage",
        "商业贷款核销率",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:consumer_charge_off",
        "credit",
        "realized_damage",
        "消费贷款核销率",
        "percent",
        "quarterly",
        "confirmation",
    ),
    (
        "credit:nfci",
        "credit",
        "financial_conditions_liquidity",
        "芝加哥联储全国金融状况指数（NFCI）",
        "index",
        "weekly",
        "confirmation",
    ),
    (
        "credit:anfci",
        "credit",
        "financial_conditions_liquidity",
        "调整后全国金融状况指数（ANFCI）",
        "index",
        "weekly",
        "confirmation",
    ),
    (
        "credit:stl_stress",
        "credit",
        "financial_conditions_liquidity",
        "圣路易斯联储金融压力指数",
        "index",
        "weekly",
        "confirmation",
    ),
)


def _preferred_series_key(concept_key: str) -> str | None:
    candidates = [
        (MACRO_PROVIDER_SERIES_SOURCE_PRIORITY[series_key], series_key)
        for series_key, mapped_concept in MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT.items()
        if mapped_concept == concept_key
    ]
    return max(candidates)[1] if candidates else None


def _change_kind(section_id: str, frequency: str) -> MacroLiveChangeKind:
    if frequency == "event":
        return "none"
    if section_id == "asset_returns":
        return "return_pct"
    return "difference"


def _build_catalog() -> MappingProxyType[str, MacroLiveConceptSpec]:
    catalog: dict[str, MacroLiveConceptSpec] = {}
    for display_order, row in enumerate(_RAW_CONCEPTS, start=1):
        concept_key, view_id, section_id, label, unit, frequency, role = row
        if concept_key in catalog:
            raise RuntimeError(f"macro_live_catalog_duplicate:{concept_key}")
        catalog[concept_key] = MacroLiveConceptSpec(
            concept_key=concept_key,
            view_id=view_id,
            section_id=section_id,
            section_label=MACRO_LIVE_SECTION_LABELS[section_id],
            display_label=label,
            display_order=display_order,
            unit=unit,
            frequency=frequency,
            preferred_series_key=_preferred_series_key(concept_key),
            summary=role in {"primary", "catalyst"},
            change_kind=_change_kind(section_id, frequency),
        )
    if len(catalog) != 108:
        raise RuntimeError(f"macro_live_catalog_expected_108:{len(catalog)}")
    return MappingProxyType(catalog)


MACRO_LIVE_CATALOG = _build_catalog()


def concepts_for_live_view(view_id: MacroLiveViewId) -> tuple[str, ...]:
    return tuple(spec.concept_key for spec in MACRO_LIVE_CATALOG.values() if spec.view_id == view_id)


def query_concepts_for_live_view(view_id: MacroLiveViewId | Literal["dashboard"]) -> tuple[str, ...]:
    if view_id == "dashboard":
        return tuple(MACRO_LIVE_CATALOG)
    concepts = list(concepts_for_live_view(view_id))
    if view_id == "liquidity-funding":
        concepts.extend(("fed:iorb", "fed:effr"))
    return tuple(dict.fromkeys(concepts))


__all__ = [
    "MACRO_LIVE_CATALOG",
    "MACRO_LIVE_SECTION_LABELS",
    "MACRO_LIVE_VIEW_IDS",
    "MACRO_LIVE_VIEW_META",
    "MacroLiveConceptSpec",
    "MacroLiveViewId",
    "concepts_for_live_view",
    "query_concepts_for_live_view",
]
