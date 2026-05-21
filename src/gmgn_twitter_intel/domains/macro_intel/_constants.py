from __future__ import annotations

MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v2"
MACRO_VIEW_HISTORY_LOOKBACK_DAYS = 1095
MACRO_VIEW_HISTORY_LIMIT_PER_SERIES = 800

MACRO_CORE_SERIES = (
    "fred:WALCL",
    "fred:RRPONTSYD",
    "treasury_fiscal:operating_cash_balance",
    "nyfed:SOFR",
    "fred:IORB",
    "fred:DGS2",
    "fred:DGS5",
    "fred:DGS10",
    "fred:DGS30",
    "fred:T10Y2Y",
    "fred:T10Y3M",
    "fred:DFII10",
    "fred:T10YIE",
    "fred:T5YIFR",
    "fred:DFEDTARU",
    "fred:DFEDTARL",
    "fred:EFFR",
    "fred:BAMLC0A0CM",
    "fred:BAMLH0A0HYM2",
    "fred:VIXCLS",
    "fred:SP500",
    "fred:DCOILWTICO",
    "fred:DTWEXBGS",
    "stooq:spy.us",
    "stooq:qqq.us",
    "stooq:iwm.us",
    "stooq:tlt.us",
    "stooq:hyg.us",
    "stooq:lqd.us",
    "stooq:gld.us",
    "stooq:uso.us",
    "cftc:financial_futures:sp500_net_noncommercial",
    "coingecko:bitcoin:usd",
)

__all__ = [
    "MACRO_CORE_SERIES",
    "MACRO_VIEW_HISTORY_LIMIT_PER_SERIES",
    "MACRO_VIEW_HISTORY_LOOKBACK_DAYS",
    "MACRO_VIEW_PROJECTION_VERSION",
]
