from __future__ import annotations

MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v3"
MACRO_VIEW_HISTORY_LOOKBACK_DAYS = 1095
MACRO_VIEW_HISTORY_LIMIT_PER_SERIES = 800

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

__all__ = [
    "MACRO_CORE_CONCEPTS",
    "MACRO_PROVIDER_SERIES_SOURCE_PRIORITY",
    "MACRO_PROVIDER_SERIES_TO_CONCEPT",
    "MACRO_VIEW_HISTORY_LIMIT_PER_SERIES",
    "MACRO_VIEW_HISTORY_LOOKBACK_DAYS",
    "MACRO_VIEW_PROJECTION_VERSION",
]
