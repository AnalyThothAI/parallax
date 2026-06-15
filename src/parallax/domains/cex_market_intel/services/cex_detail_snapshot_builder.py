from __future__ import annotations

from typing import Any

_COINGLASS_STATUS_VALUES = frozenset({"ready", "partial", "unavailable"})
_LEGACY_JSON_ALIAS_FIELDS = frozenset({"level_bands_json"})
_OBSERVED_AT_SOURCE_VALUES = frozenset({"provider", "computed"})


def build_cex_detail_snapshot(
    *,
    row: dict[str, Any],
    computed_at_ms: int,
    period: str,
    exchange: str,
) -> dict[str, Any]:
    snapshot_exchange = _required_text(exchange, "exchange").lower()
    snapshot_period = _required_period(period)
    _reject_legacy_json_aliases(row)
    native_market_id = _required_symbol(row, "native_market_id")
    target_base_symbol = _symbol(row.get("base_symbol"))
    quote_symbol = _required_symbol(row, "quote_symbol")
    target_id = _target_id(row, base_symbol=target_base_symbol)
    base_symbol = _required_symbol(row, "base_symbol")
    price_usd = _float_or_none(row.get("price_usd"))
    mark_price = _float_or_none(row.get("mark_price"))
    open_interest_usd = _float_or_none(row.get("open_interest_usd"))
    volume_24h_usd = _float_or_none(row.get("volume_24h_usd"))
    funding_rate = _float_or_none(row.get("funding_rate"))
    coinglass_status = _required_status(row, "coinglass_status")
    degraded_reasons = _required_degraded_reasons(row)
    if coinglass_status != "ready":
        degraded_reasons.append("coinglass_unavailable")

    explicit_oi_1h = _float_or_none(row.get("oi_change_pct_1h"))
    explicit_oi_4h = _float_or_none(row.get("oi_change_pct_4h"))
    explicit_oi_24h = _float_or_none(row.get("oi_change_pct_24h"))
    if explicit_oi_1h is not None or explicit_oi_4h is not None or explicit_oi_24h is not None:
        oi_1h, oi_4h, oi_24h, period_reason = explicit_oi_1h, explicit_oi_4h, explicit_oi_24h, None
    else:
        oi_1h, oi_4h, oi_24h, period_reason = _oi_delta_slots(
            period=snapshot_period,
            change_pct=_float_or_none(row.get("open_interest_change_pct_1h")),
        )
    if period_reason:
        degraded_reasons.append(period_reason)

    level_bands = _required_level_bands(row)
    observed_at_ms = _required_observed_at_ms(row)
    observed_at_source = _required_observed_at_source(row)
    baseline_ready = any(
        value is not None for value in (price_usd, mark_price, open_interest_usd, volume_24h_usd, funding_rate)
    )
    status = "ready" if baseline_ready and coinglass_status == "ready" else "partial" if baseline_ready else "missing"
    source_refs = _source_refs(
        exchange=snapshot_exchange,
        native_market_id=native_market_id,
        pricefeed_id=_optional_str(row.get("pricefeed_id")),
        observed_at_ms=observed_at_ms,
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
        "snapshot_id": f"cex-detail:{snapshot_exchange}:{native_market_id}",
        "target_type": "CexToken",
        "target_id": target_id,
        "exchange": snapshot_exchange,
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
        "observed_at_source": observed_at_source,
        "computed_at_ms": int(computed_at_ms),
    }


def _target_id(row: dict[str, Any], *, base_symbol: str) -> str:
    cex_token_id = _optional_str(row.get("cex_token_id"))
    if cex_token_id and cex_token_id != _UNKNOWN_CEX_TOKEN_ID:
        return cex_token_id
    target_id = _optional_str(row.get("target_id"))
    if target_id and not target_id.startswith("binance:") and target_id != _UNKNOWN_CEX_TOKEN_ID:
        return target_id
    if base_symbol:
        return f"cex_token:{base_symbol}"
    raise ValueError("cex_detail_snapshot_identity_required:target_id")


def _oi_delta_slots(
    *,
    period: str,
    change_pct: float | None,
) -> tuple[float | None, float | None, float | None, str | None]:
    if change_pct is None:
        return None, None, None, None
    if period == "1h":
        return change_pct, None, None, None
    if period == "4h":
        return None, change_pct, None, None
    if period in {"24h", "1d"}:
        return None, None, change_pct, None
    reason_period = period.replace(" ", "_")
    return None, None, None, f"oi_change_period_{reason_period}_not_1h"


def _source_refs(
    *,
    exchange: str,
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
            "ref_id": f"market:cex:{exchange}:{native_market_id}",
            "ref_type": "market",
            "source_table": "cex_detail_snapshots",
            "source_id": market_source,
            "observed_at_ms": observed_at_ms,
            "summary_zh": f"{exchange.capitalize()} USDT 永续 {native_market_id} 行情快照",
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
        kind = str(band["kind"]).strip().lower()
        price = band["price"]
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


_UNKNOWN_CEX_TOKEN_ID = "cex_token:" + "unknown"


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"cex_detail_snapshot_identity_required:{field}")
    return text


def _required_period(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError("cex_detail_snapshot_identity_required:period")
    return text


def _reject_legacy_json_aliases(row: dict[str, Any]) -> None:
    for field in _LEGACY_JSON_ALIAS_FIELDS:
        if field in row:
            raise ValueError(f"cex_detail_snapshot_legacy_json_alias:{field}")


def _required_symbol(row: dict[str, Any], field: str) -> str:
    value = _symbol(row.get(field))
    if not value:
        raise ValueError(f"cex_detail_snapshot_identity_required:{field}")
    return value


def _required_status(row: dict[str, Any], field: str) -> str:
    value = str(row.get(field) or "").strip().lower()
    if not value:
        raise ValueError(f"cex_detail_snapshot_status_required:{field}")
    if value not in _COINGLASS_STATUS_VALUES:
        raise ValueError(f"cex_detail_snapshot_status_invalid:{field}")
    return value


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


def _required_observed_at_ms(row: dict[str, Any]) -> int:
    value = row.get("observed_at_ms")
    if value is None:
        raise ValueError("cex_detail_snapshot_observation_required:observed_at_ms")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("cex_detail_snapshot_observation_invalid:observed_at_ms") from exc


def _required_observed_at_source(row: dict[str, Any]) -> str:
    value = row.get("observed_at_source")
    if value is None:
        raise ValueError("cex_detail_snapshot_observation_required:observed_at_source")
    source = str(value).strip().lower()
    if not source:
        raise ValueError("cex_detail_snapshot_observation_required:observed_at_source")
    if source not in _OBSERVED_AT_SOURCE_VALUES:
        raise ValueError("cex_detail_snapshot_observation_invalid:observed_at_source")
    return source


def _required_degraded_reasons(row: dict[str, Any]) -> list[str]:
    if "degraded_reasons" not in row or row.get("degraded_reasons") is None:
        return []
    value = row.get("degraded_reasons")
    if not isinstance(value, list | tuple):
        raise ValueError("cex_detail_snapshot_degraded_reasons_invalid")
    reasons: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("cex_detail_snapshot_degraded_reason_invalid:item")
        reasons.append(item.strip())
    return reasons


def _required_level_bands(row: dict[str, Any]) -> list[dict[str, Any]]:
    if "level_bands" not in row or row.get("level_bands") is None:
        return []
    value = row.get("level_bands")
    if not isinstance(value, list | tuple):
        raise ValueError("cex_detail_snapshot_level_bands_invalid")
    bands: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("cex_detail_snapshot_level_band_invalid:item")
        band = dict(item)
        kind = str(band.get("kind") or "").strip().lower()
        if not kind:
            raise ValueError("cex_detail_snapshot_level_band_required:kind")
        price = _float_or_none(band.get("price"))
        if price is None:
            raise ValueError("cex_detail_snapshot_level_band_required:price")
        band["kind"] = kind
        band["price"] = price
        bands.append(band)
    return bands
