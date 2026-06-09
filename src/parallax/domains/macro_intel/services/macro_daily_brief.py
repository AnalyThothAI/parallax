from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MACRO_DAILY_BRIEF_KEY = "assets_today"
MACRO_DAILY_BRIEF_PROJECTION_VERSION = "macro_daily_brief_v1"


def build_macro_daily_brief(*, snapshot: Mapping[str, Any] | None, computed_at_ms: int) -> dict[str, Any]:
    if snapshot is None:
        return {
            "brief_key": MACRO_DAILY_BRIEF_KEY,
            "projection_version": MACRO_DAILY_BRIEF_PROJECTION_VERSION,
            "brief_date": None,
            "asof_date": None,
            "status": "missing",
            "headline": "今日判断：宏观快照缺失",
            "blocks": _missing_blocks(),
            "data_quality": {
                "status": "missing",
                "latest_coverage_ratio": 0.0,
                "history_coverage_ratio": 0.0,
                "gap_count": 1,
            },
            "computed_at_ms": int(computed_at_ms),
        }

    asof_date = _string_or_none(snapshot.get("asof_date"))
    features = _mapping(snapshot.get("features_json"))
    quality = _data_quality(snapshot)
    risk = _risk_label(features)
    dollar = _delta(features, "fx:dxy")
    wti = _delta(features, "commodity:wti")
    btc = _delta(features, "crypto:btc")
    spx = _delta(features, "asset:spx")
    ten_year = _delta(features, "rates:dgs10")
    vix = _delta(features, "vol:vix")
    hy_oas = _delta(features, "credit:hy_oas")
    return {
        "brief_key": MACRO_DAILY_BRIEF_KEY,
        "projection_version": MACRO_DAILY_BRIEF_PROJECTION_VERSION,
        "brief_date": asof_date,
        "asof_date": asof_date,
        "status": str(snapshot.get("status") or quality["status"]),
        "headline": f"今日判断：{risk}",
        "blocks": [
            {
                "id": "cross_correlation",
                "title": "跨资产相关性",
                "stance": _cross_stance(spx=spx, btc=btc, ten_year=ten_year, vix=vix),
                "body": _cross_body(spx=spx, btc=btc, ten_year=ten_year, vix=vix),
            },
            {
                "id": "dollar_commodity",
                "title": "美元与商品",
                "stance": _dollar_commodity_stance(dollar=dollar, wti=wti),
                "body": _dollar_commodity_body(dollar=dollar, wti=wti),
            },
            {
                "id": "risk_appetite",
                "title": "风险偏好",
                "stance": _risk_stance(spx=spx, btc=btc, vix=vix, hy_oas=hy_oas),
                "body": _risk_body(spx=spx, btc=btc, vix=vix, hy_oas=hy_oas),
            },
            {
                "id": "outlook",
                "title": "今日展望",
                "stance": (
                    "watch_data_quality"
                    if quality["status"] != "ok"
                    else _risk_stance(spx=spx, btc=btc, vix=vix, hy_oas=hy_oas)
                ),
                "body": _outlook_body(quality=quality, risk=risk),
            },
        ],
        "data_quality": quality,
        "computed_at_ms": int(computed_at_ms),
    }


def _missing_blocks() -> list[dict[str, str]]:
    return [
        {
            "id": "cross_correlation",
            "title": "跨资产相关性",
            "stance": "missing",
            "body": "缺少宏观快照，暂不生成跨资产判断。",
        },
        {
            "id": "dollar_commodity",
            "title": "美元与商品",
            "stance": "missing",
            "body": "缺少美元和商品观测，暂不生成美元商品判断。",
        },
        {
            "id": "risk_appetite",
            "title": "风险偏好",
            "stance": "missing",
            "body": "缺少风险资产观测，暂不生成风险偏好判断。",
        },
        {
            "id": "outlook",
            "title": "今日展望",
            "stance": "missing",
            "body": "先恢复宏观事实同步和投影，再生成今日判断。",
        },
    ]


def _risk_label(features: Mapping[str, Any]) -> str:
    spx = _delta(features, "asset:spx")
    btc = _delta(features, "crypto:btc")
    vix = _delta(features, "vol:vix")
    hy_oas = _delta(features, "credit:hy_oas")
    if _positive(spx) and _positive(btc) and _negative(vix) and not _positive(hy_oas):
        return "风险资产偏强"
    if _negative(spx) and _negative(btc):
        return "风险资产承压"
    return "风险资产偏震荡"


def _cross_stance(*, spx: float | None, btc: float | None, ten_year: float | None, vix: float | None) -> str:
    if _positive(spx) and _positive(btc) and _negative(vix):
        return "risk_on_confirmation"
    if _positive(ten_year) and (_negative(spx) or _negative(btc)):
        return "duration_pressure"
    return "mixed"


def _cross_body(*, spx: float | None, btc: float | None, ten_year: float | None, vix: float | None) -> str:
    return (
        f"SPX 20日变化 {_fmt_delta(spx)}，BTC 20日变化 {_fmt_delta(btc)}，"
        f"10Y 20日变化 {_fmt_delta(ten_year)}，VIX 20日变化 {_fmt_delta(vix)}。"
    )


def _dollar_commodity_stance(*, dollar: float | None, wti: float | None) -> str:
    if _positive(dollar) and _positive(wti):
        return "inflation_pressure"
    if _negative(dollar) and _positive(wti):
        return "commodity_supported"
    if _positive(dollar) and _negative(wti):
        return "dollar_tightening"
    return "mixed"


def _dollar_commodity_body(*, dollar: float | None, wti: float | None) -> str:
    return f"DXY 20日变化 {_fmt_delta(dollar)}，WTI 20日变化 {_fmt_delta(wti)}。"


def _risk_stance(*, spx: float | None, btc: float | None, vix: float | None, hy_oas: float | None) -> str:
    if _positive(spx) and _positive(btc) and _negative(vix) and not _positive(hy_oas):
        return "risk_on"
    if _negative(spx) or _positive(vix) or _positive(hy_oas):
        return "risk_off_watch"
    return "neutral"


def _risk_body(*, spx: float | None, btc: float | None, vix: float | None, hy_oas: float | None) -> str:
    return f"SPX {_fmt_delta(spx)}，BTC {_fmt_delta(btc)}，VIX {_fmt_delta(vix)}，HY OAS {_fmt_delta(hy_oas)}。"


def _outlook_body(*, quality: Mapping[str, Any], risk: str) -> str:
    if quality["status"] != "ok":
        return f"{risk}，但数据覆盖仍不完整；当前缺口 {quality['gap_count']} 项。"
    return f"{risk}；优先观察美元、10Y、VIX 与信用利差是否同向确认。"


def _data_quality(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    coverage = _mapping(snapshot.get("source_coverage_json"))
    gaps = snapshot.get("data_gaps_json")
    gap_count = len(gaps) if isinstance(gaps, list) else 0
    latest = _float_or_zero(coverage.get("latest_coverage_ratio"))
    history = _float_or_zero(coverage.get("history_coverage_ratio"))
    return {
        "status": "ok" if gap_count == 0 and latest >= 0.95 else "partial",
        "latest_coverage_ratio": latest,
        "history_coverage_ratio": history,
        "gap_count": gap_count,
    }


def _delta(features: Mapping[str, Any], concept_key: str) -> float | None:
    feature = _mapping(features.get(concept_key))
    delta = _mapping(feature.get("delta"))
    value = delta.get("20d")
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _positive(value: float | None) -> bool:
    return value is not None and value > 0


def _negative(value: float | None) -> bool:
    return value is not None and value < 0


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "不可用"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float_or_zero(value: object) -> float:
    try:
        if isinstance(value, (bytes, float, int, str)):
            return float(value)
    except (TypeError, ValueError):
        pass
    return 0.0


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "MACRO_DAILY_BRIEF_KEY",
    "MACRO_DAILY_BRIEF_PROJECTION_VERSION",
    "build_macro_daily_brief",
]
