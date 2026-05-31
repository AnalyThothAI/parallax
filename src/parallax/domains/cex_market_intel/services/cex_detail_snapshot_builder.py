from __future__ import annotations

from typing import Any


def build_cex_detail_snapshot(
    *,
    row: dict[str, Any],
    computed_at_ms: int,
    period: str,
) -> dict[str, Any]:
    native_market_id = _symbol(row.get("native_market_id"))
    base_symbol = _symbol(row.get("base_symbol"))
    quote_symbol = _symbol(row.get("quote_symbol")) or "USDT"
    target_id = _target_id(row, base_symbol=base_symbol)
    price_usd = _float_or_none(row.get("price_usd"))
    mark_price = _float_or_none(row.get("mark_price"))
    open_interest_usd = _float_or_none(row.get("open_interest_usd"))
    volume_24h_usd = _float_or_none(row.get("volume_24h_usd"))
    funding_rate = _float_or_none(row.get("funding_rate"))
    coinglass_status = str(row.get("coinglass_status") or "unavailable")
    degraded_reasons = _strings(row.get("degraded_reasons"))
    if coinglass_status != "ready":
        degraded_reasons.append("coinglass_unavailable")

    explicit_oi_1h = _float_or_none(row.get("oi_change_pct_1h"))
    explicit_oi_4h = _float_or_none(row.get("oi_change_pct_4h"))
    explicit_oi_24h = _float_or_none(row.get("oi_change_pct_24h"))
    if explicit_oi_1h is not None or explicit_oi_4h is not None or explicit_oi_24h is not None:
        oi_1h, oi_4h, oi_24h, period_reason = explicit_oi_1h, explicit_oi_4h, explicit_oi_24h, None
    else:
        oi_1h, oi_4h, oi_24h, period_reason = _oi_delta_slots(
            period=period,
            change_pct=_float_or_none(row.get("open_interest_change_pct_1h")),
        )
    if period_reason:
        degraded_reasons.append(period_reason)

    level_bands = _list_of_dicts(row.get("level_bands") or row.get("level_bands_json"))
    observed_at_ms = _int_or_none(row.get("observed_at_ms"))
    baseline_ready = any(
        value is not None for value in (price_usd, mark_price, open_interest_usd, volume_24h_usd, funding_rate)
    )
    status = "ready" if baseline_ready and coinglass_status == "ready" else "partial" if baseline_ready else "missing"
    source_refs = _source_refs(
        native_market_id=native_market_id,
        pricefeed_id=_optional_str(row.get("pricefeed_id")),
        observed_at_ms=observed_at_ms or int(computed_at_ms),
        price_usd=price_usd,
        mark_price=mark_price,
        open_interest_usd=open_interest_usd,
        volume_24h_usd=volume_24h_usd,
        funding_rate=funding_rate,
        oi_change_pct_1h=oi_1h,
        oi_change_pct_4h=oi_4h,
        oi_change_pct_24h=oi_24h,
        cvd_delta_1h=_float_or_none(row.get("cvd_delta_1h")),
        cvd_delta_4h=_float_or_none(row.get("cvd_delta_4h")),
        cvd_delta_24h=_float_or_none(row.get("cvd_delta_24h")),
        level_bands=level_bands,
    )
    return {
        "snapshot_id": f"cex-detail:binance:{native_market_id}",
        "target_type": "CexToken",
        "target_id": target_id,
        "exchange": str(row.get("exchange") or "binance").lower(),
        "native_market_id": native_market_id,
        "base_symbol": base_symbol,
        "quote_symbol": quote_symbol,
        "status": status,
        "baseline_status": "ready" if baseline_ready else "missing",
        "coinglass_status": coinglass_status,
        "price_usd": price_usd or mark_price,
        "mark_price": mark_price,
        "funding_rate": funding_rate,
        "volume_24h_usd": volume_24h_usd,
        "open_interest_usd": open_interest_usd,
        "oi_change_pct_1h": oi_1h,
        "oi_change_pct_4h": oi_4h,
        "oi_change_pct_24h": oi_24h,
        "cvd_delta_1h": _float_or_none(row.get("cvd_delta_1h")),
        "cvd_delta_4h": _float_or_none(row.get("cvd_delta_4h")),
        "cvd_delta_24h": _float_or_none(row.get("cvd_delta_24h")),
        "long_short_ratio": _float_or_none(row.get("long_short_ratio")),
        "top_trader_position_ratio": _float_or_none(row.get("top_trader_position_ratio")),
        "level_bands": level_bands,
        "degraded_reasons": tuple(sorted(set(degraded_reasons))),
        "source_refs": source_refs,
        "observed_at_ms": observed_at_ms,
        "computed_at_ms": int(computed_at_ms),
    }


def _target_id(row: dict[str, Any], *, base_symbol: str) -> str:
    cex_token_id = _optional_str(row.get("cex_token_id"))
    if cex_token_id:
        return cex_token_id
    target_id = _optional_str(row.get("target_id"))
    if target_id and not target_id.startswith("binance:"):
        return target_id
    if base_symbol:
        return f"cex_token:{base_symbol}"
    return target_id or "cex_token:unknown"


def _oi_delta_slots(
    *,
    period: str,
    change_pct: float | None,
) -> tuple[float | None, float | None, float | None, str | None]:
    if change_pct is None:
        return None, None, None, None
    normalized = str(period or "").strip().lower()
    if normalized == "1h":
        return change_pct, None, None, None
    if normalized == "4h":
        return None, change_pct, None, None
    if normalized in {"24h", "1d"}:
        return None, None, change_pct, None
    reason_period = normalized.replace(" ", "_") or "unknown"
    return None, None, None, f"oi_change_period_{reason_period}_not_1h"


def _source_refs(
    *,
    native_market_id: str,
    pricefeed_id: str | None,
    observed_at_ms: int,
    price_usd: float | None,
    mark_price: float | None,
    open_interest_usd: float | None,
    volume_24h_usd: float | None,
    funding_rate: float | None,
    oi_change_pct_1h: float | None,
    oi_change_pct_4h: float | None,
    oi_change_pct_24h: float | None,
    cvd_delta_1h: float | None,
    cvd_delta_4h: float | None,
    cvd_delta_24h: float | None,
    level_bands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    market_source = pricefeed_id or native_market_id
    refs.append(
        {
            "ref_id": f"market:cex:binance:{native_market_id}",
            "ref_type": "market",
            "source_table": "cex_detail_snapshots",
            "source_id": market_source,
            "observed_at_ms": observed_at_ms,
            "summary_zh": f"Binance USDT 永续 {native_market_id} 行情快照",
            "quality": "high",
        }
    )
    metrics = {
        "price_usd": price_usd,
        "mark_price": mark_price,
        "open_interest_usd": open_interest_usd,
        "volume_24h_usd": volume_24h_usd,
        "funding_rate": funding_rate,
        "oi_change_pct_1h": oi_change_pct_1h,
        "oi_change_pct_4h": oi_change_pct_4h,
        "oi_change_pct_24h": oi_change_pct_24h,
        "cvd_delta_1h": cvd_delta_1h,
        "cvd_delta_4h": cvd_delta_4h,
        "cvd_delta_24h": cvd_delta_24h,
    }
    for name, value in metrics.items():
        if value is None:
            continue
        refs.append(
            {
                "ref_id": f"metric:cex:{name}:{native_market_id}",
                "ref_type": "metric",
                "source_table": "cex_detail_snapshots",
                "source_id": f"{native_market_id}:{name}",
                "observed_at_ms": observed_at_ms,
                "summary_zh": f"CEX 衍生指标 {name}",
                "quality": "high",
            }
        )
    for band in level_bands:
        kind = str(band.get("kind") or "level").strip().lower()
        price = band.get("price")
        if price is None:
            continue
        refs.append(
            {
                "ref_id": f"level:cex:{native_market_id}:{kind}:{price}",
                "ref_type": "level",
                "source_table": "cex_detail_snapshots",
                "source_id": f"{native_market_id}:{kind}:{price}",
                "observed_at_ms": observed_at_ms,
                "summary_zh": f"CEX 关键价位 {kind} {price}",
                "quality": "high",
            }
        )
    return refs


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _strings(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item or "").strip()]
    if value:
        return [str(value)]
    return []


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
