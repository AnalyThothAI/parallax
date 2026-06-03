from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from parallax.domains.cex_market_intel.providers import CexFundingPremium, CexOiMarketProvider, CexOiTicker24h
from parallax.domains.cex_market_intel.scoring.oi_radar_scoring import score_oi_radar_row


def build_binance_oi_radar_rows(
    *,
    universe: list[dict[str, Any]],
    client: CexOiMarketProvider,
    now_ms: int,
    period: str = "5m",
    limit: int = 500,
) -> dict[str, Any]:
    selected = universe[: max(1, int(limit))]
    tickers = _tickers_by_symbol(client.list_24h_tickers())
    premiums = _premiums_by_symbol(client.list_funding_premium())
    rows: list[dict[str, Any]] = []
    failed_symbols: list[str] = []

    for route in selected:
        symbol = str(route.get("native_market_id") or "").strip().upper()
        if not symbol:
            continue
        try:
            history = list(client.list_open_interest_history(symbol, period, 2))
        except Exception:
            failed_symbols.append(symbol)
            continue
        latest_oi = history[-1] if history else None
        previous_oi = history[-2] if len(history) >= 2 else None
        ticker = tickers.get(symbol)
        premium = premiums.get(symbol)
        open_interest_usd = _attr(latest_oi, "open_interest_value")
        latest_observed_at_ms = _attr(latest_oi, "observed_at_ms")
        change_pct = _change_pct(_attr(previous_oi, "open_interest_value"), open_interest_usd)
        funding_rate = _attr(premium, "last_funding_rate")
        volume_24h_usd = _attr(ticker, "quote_volume_24h")
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
                "base_symbol": str(route.get("base_symbol") or "").strip().upper(),
                "quote_symbol": "USDT",
                "open_interest_usd": open_interest_usd,
                "open_interest_change_pct_1h": change_pct,
                "volume_24h_usd": volume_24h_usd,
                "funding_rate": funding_rate,
                "mark_price": _attr(premium, "mark_price") or _attr(ticker, "last_price"),
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
    return {symbol: row for row in rows if (symbol := _symbol(row.symbol))}


def _premiums_by_symbol(rows: Sequence[CexFundingPremium]) -> dict[str, CexFundingPremium]:
    return {symbol: row for row in rows if (symbol := _symbol(row.symbol))}


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _attr(value: Any, name: str) -> Any:
    if value is None:
        return None
    return getattr(value, name, None)


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
