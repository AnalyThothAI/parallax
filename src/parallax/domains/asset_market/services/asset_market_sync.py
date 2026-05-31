from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class _BinanceRoute:
    native_market_id: str
    base_symbol: str
    quote_symbol: str
    multiplier: Any


def sync_binance_usdt_perp_routes(
    *,
    registry: Any,
    client: Any,
    observed_at_ms: int,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    if dry_run == execute:
        raise ValueError("exactly one of dry_run or execute must be true")

    started = time.monotonic()
    routes = _normalized_routes(client.usdt_perpetual_routes())
    base_symbols = [route.base_symbol for route in routes]
    native_market_ids = [route.native_market_id for route in routes]
    plan = _sync_plan_counts(registry, base_symbols=base_symbols, native_market_ids=native_market_ids)

    cex_tokens_written = 0
    pricefeeds_written = 0
    affected_lookup_keys: set[str] = set()
    if execute:
        for route in routes:
            cex_token = registry.upsert_cex_token(
                base_symbol=route.base_symbol,
                project_id=None,
                source="binance_cex",
                observed_at_ms=observed_at_ms,
                commit=False,
            )
            cex_tokens_written += 1
            registry.upsert_pricefeed(
                feed_type="cex_swap",
                provider="binance",
                subject_type="CexToken",
                subject_id=str(cex_token["cex_token_id"]),
                native_market_id=route.native_market_id,
                base_cex_token_id=str(cex_token["cex_token_id"]),
                base_symbol=route.base_symbol,
                quote_symbol=route.quote_symbol,
                multiplier=route.multiplier,
                observed_at_ms=observed_at_ms,
                commit=False,
            )
            pricefeeds_written += 1
            affected_lookup_keys.update(_symbol_lookup_keys(route.base_symbol))
        registry.conn.commit()

    return {
        "mode": "execute" if execute else "dry_run",
        "provider": "binance",
        "feed_type": "cex_swap",
        "quote_symbol": "USDT",
        "contract_type": "PERPETUAL",
        "binance_usdt_perp_seen": len(routes),
        "cex_tokens_to_insert": int(plan.get("cex_tokens_to_insert", len(routes))),
        "cex_tokens_to_delete": int(plan.get("cex_tokens_to_delete", 0)),
        "pricefeeds_to_insert": int(plan.get("pricefeeds_to_insert", len(routes))),
        "old_okx_cex_rows_to_delete": int(plan.get("old_okx_cex_rows_to_delete", 0)),
        "cex_tokens_written": cex_tokens_written,
        "pricefeeds_written": pricefeeds_written,
        "affected_lookup_keys": sorted(affected_lookup_keys),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _normalized_routes(routes: Any) -> list[_BinanceRoute]:
    by_market_id: dict[str, _BinanceRoute] = {}
    for route in routes:
        native_market_id = _symbol(getattr(route, "native_market_id", ""))
        base_symbol = _symbol(getattr(route, "base_symbol", ""))
        quote_symbol = _symbol(getattr(route, "quote_symbol", ""))
        if not native_market_id or not base_symbol or quote_symbol != "USDT":
            continue
        by_market_id[native_market_id] = _BinanceRoute(
            native_market_id=native_market_id,
            base_symbol=base_symbol,
            quote_symbol=quote_symbol,
            multiplier=getattr(route, "multiplier", None),
        )
    return [by_market_id[key] for key in sorted(by_market_id)]


def _sync_plan_counts(registry: Any, *, base_symbols: list[str], native_market_ids: list[str]) -> dict[str, int]:
    method = getattr(registry, "binance_usdt_perp_sync_plan_counts", None)
    if method is None:
        return {
            "cex_tokens_to_insert": len(set(base_symbols)),
            "cex_tokens_to_delete": 0,
            "pricefeeds_to_insert": len(set(native_market_ids)),
            "old_okx_cex_rows_to_delete": 0,
        }
    return dict(method(base_symbols=base_symbols, native_market_ids=native_market_ids))


def _symbol(value: Any) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}", f"cex_token:{normalized}"}
