from __future__ import annotations

import hashlib
import json
from typing import Any

from ..market.okx_chains import OKX_CHAIN_TO_CHAIN_INDEX

DEX_PRICE_BATCH_SIZE = 20


def sync_okx_cex_universe(
    *,
    assets,
    client,
    inst_types: tuple[str, ...] | list[str],
    observed_at_ms: int,
) -> dict[str, Any]:
    normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
    venues_written = 0
    snapshots_written = 0
    for inst_type in normalized_inst_types:
        for ticker in client.tickers(inst_type=inst_type):
            base_symbol, quote_symbol = _base_quote_from_inst_id(ticker.inst_id)
            if not base_symbol or not quote_symbol:
                continue
            result = assets.upsert_cex_instrument(
                exchange="okx",
                inst_type=ticker.inst_type,
                inst_id=ticker.inst_id,
                base_symbol=base_symbol,
                quote_symbol=quote_symbol,
                observed_at_ms=observed_at_ms,
                source_payload_hash=_payload_hash(ticker.raw),
                commit=False,
            )
            venues_written += 1
            venue = result.venue or assets.venue_for_cex_instrument(
                exchange="okx",
                inst_type=ticker.inst_type,
                inst_id=ticker.inst_id,
            )
            if not venue:
                continue
            assets.insert_market_snapshot(
                asset_id=str(venue["asset_id"]),
                venue_id=str(venue["venue_id"]),
                provider="okx_cex",
                observed_at_ms=observed_at_ms,
                price_usd=ticker.last_price,
                volume_24h_usd=ticker.volume_24h,
                open_interest_usd=ticker.open_interest,
                source_payload_hash=_payload_hash(ticker.raw),
                commit=False,
            )
            snapshots_written += 1
    assets.conn.commit()
    return {
        "inst_types": normalized_inst_types,
        "venues_written": venues_written,
        "market_snapshots_written": snapshots_written,
    }


def sync_okx_dex_prices(
    *,
    assets,
    client,
    observed_at_ms: int,
    stale_after_ms: int,
    limit: int,
) -> dict[str, Any]:
    rows = assets.dex_venues_needing_market_refresh(
        stale_before_ms=int(observed_at_ms) - int(stale_after_ms),
        limit=max(0, int(limit)),
    )
    venue_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    request_items: list[dict[str, str]] = []
    for row in rows:
        chain_index = OKX_CHAIN_TO_CHAIN_INDEX.get(str(row.get("chain") or "").strip().lower())
        address = str(row.get("address") or "").strip()
        if not chain_index or not address:
            continue
        request_item = {
            "chainIndex": chain_index,
            "tokenContractAddress": address.lower() if address.lower().startswith("0x") else address,
        }
        request_items.append(request_item)
        venue_by_key[(chain_index, request_item["tokenContractAddress"])] = row

    snapshots_written = 0
    price_requests = 0
    for chunk in _chunks(request_items, DEX_PRICE_BATCH_SIZE):
        if not chunk:
            continue
        price_requests += 1
        for price in client.token_prices(chunk):
            price_address = price.address.lower() if price.address.lower().startswith("0x") else price.address
            key = (price.chain_index, price_address)
            venue = venue_by_key.get(key)
            if not venue:
                continue
            assets.insert_market_snapshot(
                asset_id=str(venue["asset_id"]),
                venue_id=str(venue["venue_id"]),
                provider="okx_dex_price",
                observed_at_ms=price.observed_at_ms or observed_at_ms,
                price_usd=price.price_usd,
                market_cap_usd=venue.get("market_cap_usd"),
                liquidity_usd=venue.get("liquidity_usd"),
                volume_24h_usd=venue.get("volume_24h_usd"),
                open_interest_usd=venue.get("open_interest_usd"),
                holders=venue.get("holders"),
                source_payload_hash=_payload_hash(price.raw),
                commit=False,
            )
            snapshots_written += 1
    assets.conn.commit()
    return {
        "venues_scanned": len(rows),
        "price_requests": price_requests,
        "market_snapshots_written": snapshots_written,
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _base_quote_from_inst_id(inst_id: str) -> tuple[str | None, str | None]:
    parts = [part.strip().upper() for part in str(inst_id).split("-") if part.strip()]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _chunks(items: list[dict[str, str]], size: int):
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + size]
