from __future__ import annotations

from typing import Any


def sync_cex_routes(
    *,
    registry: Any,
    cex_market: Any,
    inst_types: tuple[str, ...] | list[str],
    observed_at_ms: int,
) -> dict[str, Any]:
    normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
    cex_tokens_written = 0
    pricefeeds_written = 0
    affected_lookup_keys: set[str] = set()
    for inst_type in normalized_inst_types:
        for ticker in cex_market.tickers(inst_type=inst_type):
            base_symbol, quote_symbol = _base_quote_from_inst_id(ticker.inst_id)
            if not base_symbol or not quote_symbol:
                continue
            cex_token = registry.upsert_cex_token(
                base_symbol=base_symbol,
                project_id=None,
                source="okx_cex",
                observed_at_ms=observed_at_ms,
                commit=False,
            )
            cex_tokens_written += 1
            registry.upsert_pricefeed(
                feed_type=f"cex_{ticker.inst_type.lower()}",
                provider="okx",
                subject_type="CexToken",
                subject_id=str(cex_token["cex_token_id"]),
                native_market_id=ticker.inst_id,
                base_cex_token_id=str(cex_token["cex_token_id"]),
                base_symbol=base_symbol,
                quote_symbol=quote_symbol,
                observed_at_ms=observed_at_ms,
                commit=False,
            )
            pricefeeds_written += 1
            affected_lookup_keys.update(_symbol_lookup_keys(base_symbol))
    registry.conn.commit()
    return {
        "inst_types": normalized_inst_types,
        "cex_tokens_written": cex_tokens_written,
        "pricefeeds_written": pricefeeds_written,
        "affected_lookup_keys": sorted(affected_lookup_keys),
    }


def _base_quote_from_inst_id(inst_id: str) -> tuple[str | None, str | None]:
    parts = [part.strip().upper() for part in str(inst_id).split("-") if part.strip()]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}", f"cex_token:{normalized}"}
