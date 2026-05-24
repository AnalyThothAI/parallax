from __future__ import annotations

MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v4"
MACRO_MODULE_VIEW_VERSION = "macro_module_view_v2"
MACRO_VIEW_HISTORY_LOOKBACK_DAYS = 1095
MACRO_VIEW_HISTORY_LIMIT_PER_SERIES = 800
MACRO_MIN_CHART_POINTS = 2
MACRO_REQUIRED_DELTA_POINTS = {"5d": 6, "20d": 21, "60d": 61}
MACRO_REQUIRED_STAT_POINTS = 126

MACRO_PROVIDER_SERIES_TO_CONCEPT = {
    "fred:WALCL": "liquidity:fed_assets",
    "fred:WRBWFRBL": "liquidity:reserve_balances",
    "fred:RRPONTSYD": "liquidity:on_rrp",
    "nyfed:SOFR": "liquidity:sofr",
    "treasury_fiscal:operating_cash_balance": "liquidity:tga",
    "fred:DGS2": "rates:dgs2",
    "fred:DGS5": "rates:dgs5",
    "fred:DGS10": "rates:dgs10",
    "fred:DGS30": "rates:dgs30",
    "fred:T10Y2Y": "rates:10y2y",
    "fred:T10Y3M": "rates:10y3m",
    "fred:DFII10": "rates:real_10y",
    "fred:T10YIE": "inflation:10y_breakeven",
    "fred:T5YIFR": "inflation:5y5y_forward",
    "fred:DFEDTARU": "fed:target_upper",
    "fred:DFEDTARL": "fed:target_lower",
    "fred:EFFR": "fed:effr",
    "fred:IORB": "fed:iorb",
    "fred:BAMLC0A0CM": "credit:ig_oas",
    "fred:BAMLH0A0HYM2": "credit:hy_oas",
    "fred:VIXCLS": "vol:vix",
    "fred:SP500": "asset:spx",
    "fred:DCOILWTICO": "commodity:wti",
    "fred:DTWEXBGS": "fx:broad_dollar",
    "yahoo:SPY": "asset:spy",
    "yahoo:QQQ": "asset:qqq",
    "yahoo:IWM": "asset:iwm",
    "yahoo:TLT": "asset:tlt",
    "yahoo:HYG": "asset:hyg",
    "yahoo:LQD": "asset:lqd",
    "yahoo:GLD": "asset:gld",
    "yahoo:USO": "asset:uso",
    "yahoo:DX-Y.NYB": "fx:dxy",
    "yahoo:BTC-USD": "crypto:btc",
    "yahoo:ETH-USD": "crypto:eth",
    "cftc:financial_futures:sp500_net_noncommercial": "positioning:sp500_net_noncommercial",
}

MACRO_PROVIDER_SERIES_SOURCE_PRIORITY = {series_key: 100 for series_key in MACRO_PROVIDER_SERIES_TO_CONCEPT}

MACRO_CORE_CONCEPTS = tuple(MACRO_PROVIDER_SERIES_TO_CONCEPT.values())

MACRO_CONCEPT_METADATA = {
    "asset:gld": {
        "label": "黄金 ETF",
        "short_label": "GLD",
        "description": "黄金避险与实际利率敏感资产",
        "unit_label": "美元",
    },
    "asset:hyg": {
        "label": "高收益债 ETF",
        "short_label": "HYG",
        "description": "信用风险偏好的可交易确认",
        "unit_label": "美元",
    },
    "asset:iwm": {
        "label": "罗素2000 ETF",
        "short_label": "IWM",
        "description": "美国小盘股风险偏好代理",
        "unit_label": "美元",
    },
    "asset:lqd": {
        "label": "投资级债 ETF",
        "short_label": "LQD",
        "description": "投资级信用与久期组合代理",
        "unit_label": "美元",
    },
    "asset:qqq": {
        "label": "纳指100 ETF",
        "short_label": "QQQ",
        "description": "美国成长股风险偏好代理",
        "unit_label": "美元",
    },
    "asset:spx": {
        "label": "标普500",
        "short_label": "SPX",
        "description": "美国大盘股风险偏好基准",
        "unit_label": "点",
    },
    "asset:spy": {
        "label": "标普500 ETF",
        "short_label": "SPY",
        "description": "美国大盘股可交易风险偏好代理",
        "unit_label": "美元",
    },
    "asset:tlt": {
        "label": "长期美债 ETF",
        "short_label": "TLT",
        "description": "长久期利率敏感资产代理",
        "unit_label": "美元",
    },
    "asset:uso": {
        "label": "原油 ETF",
        "short_label": "USO",
        "description": "原油价格冲击的可交易代理",
        "unit_label": "美元",
    },
    "commodity:wti": {
        "label": "WTI 原油",
        "short_label": "WTI",
        "description": "美元计价原油现货基准",
        "unit_label": "美元/桶",
    },
    "credit:hy_oas": {
        "label": "高收益债 OAS",
        "short_label": "HY OAS",
        "description": "美国高收益债信用利差压力",
        "unit_label": "%",
    },
    "credit:ig_oas": {
        "label": "投资级债 OAS",
        "short_label": "IG OAS",
        "description": "美国投资级债信用利差压力",
        "unit_label": "%",
    },
    "crypto:btc": {
        "label": "比特币",
        "short_label": "BTC",
        "description": "加密资产宏观风险偏好代理",
        "unit_label": "美元",
    },
    "crypto:eth": {
        "label": "以太坊",
        "short_label": "ETH",
        "description": "智能合约资产宏观风险偏好代理",
        "unit_label": "美元",
    },
    "fed:effr": {
        "label": "有效联邦基金利率",
        "short_label": "EFFR",
        "description": "隔夜政策利率成交基准",
        "unit_label": "%",
    },
    "fed:iorb": {
        "label": "准备金余额利率",
        "short_label": "IORB",
        "description": "美联储管理利率走廊上沿锚",
        "unit_label": "%",
    },
    "fed:target_lower": {
        "label": "联邦基金目标下限",
        "short_label": "FF 下限",
        "description": "FOMC 目标区间下限",
        "unit_label": "%",
    },
    "fed:target_upper": {
        "label": "联邦基金目标上限",
        "short_label": "FF 上限",
        "description": "FOMC 目标区间上限",
        "unit_label": "%",
    },
    "fx:broad_dollar": {
        "label": "广义美元指数",
        "short_label": "Broad USD",
        "description": "贸易加权美元压力基准",
        "unit_label": "点",
    },
    "fx:dxy": {
        "label": "美元指数",
        "short_label": "DXY",
        "description": "美元兑主要货币强弱代理",
        "unit_label": "点",
    },
    "inflation:10y_breakeven": {
        "label": "10年通胀盈亏平衡",
        "short_label": "10Y BEI",
        "description": "市场隐含长期通胀预期",
        "unit_label": "%",
    },
    "inflation:5y5y_forward": {
        "label": "5年5年远期通胀",
        "short_label": "5Y5Y",
        "description": "远期通胀预期锚定程度",
        "unit_label": "%",
    },
    "liquidity:fed_assets": {
        "label": "美联储总资产",
        "short_label": "Fed 资产",
        "description": "美联储资产负债表规模",
        "unit_label": "百万美元",
    },
    "liquidity:on_rrp": {
        "label": "隔夜逆回购",
        "short_label": "ON RRP",
        "description": "隔夜逆回购工具使用量",
        "unit_label": "百万美元",
    },
    "liquidity:reserve_balances": {
        "label": "银行准备金余额",
        "short_label": "准备金",
        "description": "银行体系准备金流动性缓冲",
        "unit_label": "百万美元",
    },
    "liquidity:sofr": {
        "label": "SOFR",
        "short_label": "SOFR",
        "description": "有担保隔夜融资利率",
        "unit_label": "%",
    },
    "liquidity:tga": {
        "label": "财政部现金账户",
        "short_label": "TGA",
        "description": "美国财政部在美联储现金余额",
        "unit_label": "百万美元",
    },
    "positioning:sp500_net_noncommercial": {
        "label": "标普500 非商业净持仓",
        "short_label": "SPX 持仓",
        "description": "CFTC 标普500 非商业净持仓",
        "unit_label": "张",
    },
    "rates:10y2y": {
        "label": "10年-2年美债利差",
        "short_label": "10Y-2Y",
        "description": "美国收益率曲线斜率",
        "unit_label": "%",
    },
    "rates:10y3m": {
        "label": "10年-3个月美债利差",
        "short_label": "10Y-3M",
        "description": "美国期限利差与衰退压力代理",
        "unit_label": "%",
    },
    "rates:dgs10": {
        "label": "10年期美债收益率",
        "short_label": "10Y",
        "description": "美国长期无风险利率基准",
        "unit_label": "%",
    },
    "rates:dgs2": {
        "label": "2年期美债收益率",
        "short_label": "2Y",
        "description": "政策预期敏感的短端美债收益率",
        "unit_label": "%",
    },
    "rates:dgs30": {
        "label": "30年期美债收益率",
        "short_label": "30Y",
        "description": "美国超长端无风险利率基准",
        "unit_label": "%",
    },
    "rates:dgs5": {
        "label": "5年期美债收益率",
        "short_label": "5Y",
        "description": "美国中端美债收益率",
        "unit_label": "%",
    },
    "rates:real_10y": {
        "label": "10年期实际利率",
        "short_label": "10Y Real",
        "description": "美国10年期 TIPS 实际收益率",
        "unit_label": "%",
    },
    "vol:vix": {
        "label": "VIX",
        "short_label": "VIX",
        "description": "标普500 隐含波动率压力",
        "unit_label": "点",
    },
}

__all__ = [
    "MACRO_CONCEPT_METADATA",
    "MACRO_CORE_CONCEPTS",
    "MACRO_MIN_CHART_POINTS",
    "MACRO_MODULE_VIEW_VERSION",
    "MACRO_PROVIDER_SERIES_SOURCE_PRIORITY",
    "MACRO_PROVIDER_SERIES_TO_CONCEPT",
    "MACRO_REQUIRED_DELTA_POINTS",
    "MACRO_REQUIRED_STAT_POINTS",
    "MACRO_VIEW_HISTORY_LIMIT_PER_SERIES",
    "MACRO_VIEW_HISTORY_LOOKBACK_DAYS",
    "MACRO_VIEW_PROJECTION_VERSION",
]
