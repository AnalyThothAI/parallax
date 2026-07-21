from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from parallax.domains.cex_market_intel.providers import (
    CexFundingPremium,
    CexOiMarketProvider,
    CexOiTicker24h,
    CexOpenInterestPoint,
)
from parallax.domains.cex_market_intel.scoring.oi_radar_scoring import score_oi_radar_row


def build_binance_oi_radar_rows(
    *,
    universe: list[dict[str, Any]],
    client: CexOiMarketProvider,
    now_ms: int,
    period: str,
    limit: int,
) -> dict[str, Any]:
    selected = universe[: _required_positive_int(limit, "cex_oi_radar_limit_required")]
    route_markets = [
        (route, _required_symbol(route, "native_market_id"), _required_symbol(route, "base_symbol"))
        for route in selected
    ]
    if not route_markets:
        return {
            "rows": [],
            "processed": 0,
            "failed": 0,
            "failed_symbols": [],
            "universe_count": len(universe),
        }
    tickers = _tickers_by_symbol(client.list_24h_tickers())
    premiums = _premiums_by_symbol(client.list_funding_premium())
    rows: list[dict[str, Any]] = []
    failed_symbols: list[str] = []

    for route, symbol, base_symbol in route_markets:
        try:
            history = list(client.list_open_interest_history(symbol, period, 2))
        except Exception:
            failed_symbols.append(symbol)
            continue
        latest_oi = history[-1] if history else None
        previous_oi = history[-2] if len(history) >= 2 else None
        ticker = tickers.get(symbol)
        premium = premiums.get(symbol)
        open_interest_usd = _open_interest_value(latest_oi)
        latest_observed_at_ms = _open_interest_observed_at_ms(latest_oi)
        change_pct = _change_pct(_open_interest_value(previous_oi), open_interest_usd)
        funding_rate = _funding_rate(premium)
        volume_24h_usd = _quote_volume_24h(ticker)
        premium_mark_price = _premium_mark_price(premium)
        ticker_last_price = _ticker_last_price(ticker)
        mark_price = premium_mark_price if premium_mark_price is not None else ticker_last_price
        score_payload = score_oi_radar_row(
            open_interest_usd=open_interest_usd,
            open_interest_change_pct_1h=change_pct,
            volume_24h_usd=volume_24h_usd,
            funding_rate=funding_rate,
        )
        rows.append(
            {
                "target_id": f"binance:{symbol}",
                "cex_token_id": route.get("cex_token_id"),
                "pricefeed_id": route.get("pricefeed_id"),
                "native_market_id": symbol,
                "base_symbol": base_symbol,
                "quote_symbol": "USDT",
                "open_interest_usd": open_interest_usd,
                "open_interest_change_pct_1h": change_pct,
                "volume_24h_usd": volume_24h_usd,
                "funding_rate": funding_rate,
                "mark_price": mark_price,
                "score": score_payload["score"],
                "score_components": score_payload["components"],
                "observed_at_ms": latest_observed_at_ms if latest_observed_at_ms is not None else now_ms,
                "observed_at_source": "provider" if latest_observed_at_ms is not None else "computed",
            }
        )

    rows.sort(key=lambda row: (-float(row["score"] or 0), str(row["native_market_id"])))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "rows": rows,
        "processed": len(rows),
        "failed": len(failed_symbols),
        "failed_symbols": failed_symbols,
        "universe_count": len(universe),
    }


def _tickers_by_symbol(rows: Sequence[CexOiTicker24h]) -> dict[str, CexOiTicker24h]:
    return {symbol: row for row in rows if (symbol := _ticker_symbol(row))}


def _premiums_by_symbol(rows: Sequence[CexFundingPremium]) -> dict[str, CexFundingPremium]:
    return {symbol: row for row in rows if (symbol := _premium_symbol(row))}


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _required_positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)


def _required_symbol(route: dict[str, Any], field: str) -> str:
    value = _symbol(route.get(field))
    if not value:
        raise ValueError(f"cex_oi_radar_identity_required:{field}")
    return value


def _change_pct(previous: Any, current: Any) -> float | None:
    previous_float = _float(previous)
    current_float = _float(current)
    if previous_float is None or current_float is None or previous_float == 0:
        return None
    return round(((current_float - previous_float) / previous_float) * 100.0, 6)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ticker_symbol(row: CexOiTicker24h) -> str:
    try:
        value = row.symbol
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:symbol") from exc
    if not isinstance(value, str):
        raise ValueError("cex_oi_radar_provider_contract_required:symbol")
    symbol = _symbol(value)
    if not symbol:
        raise ValueError("cex_oi_radar_provider_contract_required:symbol")
    return symbol


def _premium_symbol(row: CexFundingPremium) -> str:
    try:
        value = row.symbol
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:symbol") from exc
    if not isinstance(value, str):
        raise ValueError("cex_oi_radar_provider_contract_required:symbol")
    symbol = _symbol(value)
    if not symbol:
        raise ValueError("cex_oi_radar_provider_contract_required:symbol")
    return symbol


def _open_interest_value(point: CexOpenInterestPoint | None) -> float | None:
    if point is None:
        return None
    try:
        value = point.open_interest_value
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:open_interest_value") from exc
    return _optional_provider_float(value, field="open_interest_value")


def _open_interest_observed_at_ms(point: CexOpenInterestPoint | None) -> int | None:
    if point is None:
        return None
    try:
        value = point.observed_at_ms
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:observed_at_ms") from exc
    return _optional_provider_positive_int(value, field="observed_at_ms")


def _funding_rate(premium: CexFundingPremium | None) -> float | None:
    if premium is None:
        return None
    try:
        value = premium.last_funding_rate
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:last_funding_rate") from exc
    return _optional_provider_float(value, field="last_funding_rate")


def _premium_mark_price(premium: CexFundingPremium | None) -> float | None:
    if premium is None:
        return None
    try:
        value = premium.mark_price
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:mark_price") from exc
    return _optional_provider_float(value, field="mark_price")


def _quote_volume_24h(ticker: CexOiTicker24h | None) -> float | None:
    if ticker is None:
        return None
    try:
        value = ticker.quote_volume_24h
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:quote_volume_24h") from exc
    return _optional_provider_float(value, field="quote_volume_24h")


def _ticker_last_price(ticker: CexOiTicker24h | None) -> float | None:
    if ticker is None:
        return None
    try:
        value = ticker.last_price
    except AttributeError as exc:
        raise ValueError("cex_oi_radar_provider_contract_required:last_price") from exc
    return _optional_provider_float(value, field="last_price")


def _optional_provider_float(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"cex_oi_radar_provider_contract_required:{field}")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"cex_oi_radar_provider_contract_required:{field}")
    return parsed


def _optional_provider_positive_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"cex_oi_radar_provider_contract_required:{field}")
    return int(value)
