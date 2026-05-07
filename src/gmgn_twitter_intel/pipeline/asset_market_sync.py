from __future__ import annotations

import hashlib
import json
from typing import Any

from ..market.okx_chains import OKX_CHAIN_TO_CHAIN_INDEX

DEX_PRICE_BATCH_SIZE = 20


def sync_okx_cex_universe(
    *,
    registry,
    price_observations,
    client,
    inst_types: tuple[str, ...] | list[str],
    observed_at_ms: int,
) -> dict[str, Any]:
    normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
    cex_tokens_written = 0
    pricefeeds_written = 0
    observations_written = 0
    affected_lookup_keys: set[str] = set()
    for inst_type in normalized_inst_types:
        for ticker in client.tickers(inst_type=inst_type):
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
            pricefeed = registry.upsert_pricefeed(
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
            price_basis = _cex_price_basis(quote_symbol)
            price_observations.insert_observation(
                provider="okx_cex",
                pricefeed_id=str(pricefeed["pricefeed_id"]),
                observed_at_ms=observed_at_ms,
                subject_type="CexToken",
                subject_id=str(cex_token["cex_token_id"]),
                price_usd=ticker.last_price if price_basis == "quote_as_usd" else None,
                price_quote=ticker.last_price,
                quote_symbol=quote_symbol,
                price_basis=price_basis,
                volume_24h_usd=ticker.volume_24h,
                open_interest_usd=ticker.open_interest,
                raw_payload={**ticker.raw, "payload_hash": _payload_hash(ticker.raw)},
                commit=False,
            )
            observations_written += 1
            affected_lookup_keys.update(_symbol_lookup_keys(base_symbol))
    registry.conn.commit()
    return {
        "inst_types": normalized_inst_types,
        "cex_tokens_written": cex_tokens_written,
        "pricefeeds_written": pricefeeds_written,
        "price_observations_written": observations_written,
        "affected_lookup_keys": sorted(affected_lookup_keys),
    }


def sync_okx_dex_prices(
    *,
    registry,
    price_observations,
    client,
    observed_at_ms: int,
    stale_after_ms: int,
    limit: int,
) -> dict[str, Any]:
    rows = registry.chain_assets_needing_price_refresh(
        stale_before_ms=int(observed_at_ms) - int(stale_after_ms),
        limit=max(0, int(limit)),
    )
    pricefeeds_written = 0
    observations_written = 0
    address_search_requests = 0
    address_search_hits = 0
    address_search_errors = 0
    affected_lookup_keys: set[str] = set()
    for index, row in enumerate(rows):
        chain_index = _okx_chain_index(row.get("chain_id"))
        address = str(row.get("address") or "").strip()
        if not chain_index or not address or not _needs_address_search(row):
            continue
        address_search_requests += 1
        candidate, search_error = _search_exact_token(client=client, chain_index=chain_index, address=address)
        if search_error:
            address_search_errors += 1
        if candidate is None:
            continue
        address_search_hits += 1
        asset = registry.upsert_chain_asset(
            chain_id=str(row["chain_id"]),
            address=address,
            symbol=candidate.symbol,
            name=candidate.name,
            decimals=None,
            source="okx_dex_search",
            observed_at_ms=observed_at_ms,
            commit=False,
        )
        rows[index] = {
            **row,
            **asset,
            "market_cap_usd": candidate.market_cap_usd,
            "liquidity_usd": candidate.liquidity_usd,
            "holders": candidate.holders,
        }
        affected_lookup_keys.update(_asset_lookup_keys(rows[index]))
        pricefeed = registry.upsert_pricefeed(
            feed_type="dex_token",
            provider="okx_dex_search",
            subject_type="Asset",
            subject_id=str(asset["asset_id"]),
            observed_at_ms=observed_at_ms,
            chain_id=str(asset["chain_id"]),
            address=str(asset["address"]),
            base_asset_id=str(asset["asset_id"]),
            base_symbol=str(asset["symbol"]) if asset.get("symbol") else candidate.symbol,
            commit=False,
        )
        pricefeeds_written += 1
        price_observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id=str(pricefeed["pricefeed_id"]),
            observed_at_ms=observed_at_ms,
            subject_type="Asset",
            subject_id=str(asset["asset_id"]),
            price_usd=candidate.price_usd,
            price_basis="usd" if candidate.price_usd is not None else "unavailable",
            market_cap_usd=candidate.market_cap_usd,
            liquidity_usd=candidate.liquidity_usd,
            holders=candidate.holders,
            raw_payload={**candidate.raw, "payload_hash": _payload_hash(candidate.raw)},
            commit=False,
        )
        observations_written += 1
    asset_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    request_items: list[dict[str, str]] = []
    for row in rows:
        chain_index = _okx_chain_index(row.get("chain_id"))
        address = str(row.get("address") or "").strip()
        if not chain_index or not address:
            continue
        request_item = {
            "chainIndex": chain_index,
            "tokenContractAddress": address.lower() if address.lower().startswith("0x") else address,
        }
        request_items.append(request_item)
        asset_by_key[(chain_index, request_item["tokenContractAddress"])] = row

    price_requests = 0
    for chunk in _chunks(request_items, DEX_PRICE_BATCH_SIZE):
        if not chunk:
            continue
        price_requests += 1
        for price in client.token_prices(chunk):
            price_address = price.address.lower() if price.address.lower().startswith("0x") else price.address
            key = (price.chain_index, price_address)
            asset = asset_by_key.get(key)
            if not asset:
                continue
            pricefeed = registry.upsert_pricefeed(
                feed_type="dex_token",
                provider="okx_dex_price",
                subject_type="Asset",
                subject_id=str(asset["asset_id"]),
                observed_at_ms=price.observed_at_ms or observed_at_ms,
                chain_id=str(asset["chain_id"]),
                address=str(asset["address"]),
                base_asset_id=str(asset["asset_id"]),
                base_symbol=str(asset["symbol"]) if asset.get("symbol") else None,
                commit=False,
            )
            pricefeeds_written += 1
            price_observations.insert_observation(
                provider="okx_dex_price",
                pricefeed_id=str(pricefeed["pricefeed_id"]),
                observed_at_ms=price.observed_at_ms or observed_at_ms,
                subject_type="Asset",
                subject_id=str(asset["asset_id"]),
                price_usd=price.price_usd,
                price_basis="usd",
                market_cap_usd=asset.get("market_cap_usd"),
                liquidity_usd=asset.get("liquidity_usd"),
                volume_24h_usd=asset.get("volume_24h_usd"),
                open_interest_usd=asset.get("open_interest_usd"),
                holders=asset.get("holders"),
                raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
                commit=False,
            )
            observations_written += 1
            affected_lookup_keys.update(_asset_lookup_keys(asset))
    registry.conn.commit()
    return {
        "assets_scanned": len(rows),
        "address_search_requests": address_search_requests,
        "address_search_hits": address_search_hits,
        "address_search_errors": address_search_errors,
        "price_requests": price_requests,
        "pricefeeds_written": pricefeeds_written,
        "price_observations_written": observations_written,
        "affected_lookup_keys": sorted(affected_lookup_keys),
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _base_quote_from_inst_id(inst_id: str) -> tuple[str | None, str | None]:
    parts = [part.strip().upper() for part in str(inst_id).split("-") if part.strip()]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _cex_price_basis(quote_symbol: str) -> str:
    return "quote_as_usd" if quote_symbol.upper() in {"USD", "USDT", "USDC"} else "quote"


def _symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}", f"cex_token:{normalized}"}


def _chain_symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}"}


def _asset_lookup_keys(row: dict[str, Any]) -> set[str]:
    keys = _chain_symbol_lookup_keys(row.get("symbol"))
    chain_id = str(row.get("chain_id") or "").strip()
    address = str(row.get("address") or "").strip()
    if address:
        normalized_address = address.lower() if address.lower().startswith("0x") else address
        keys.add(f"address:{chain_id or 'unknown'}:{normalized_address}")
    return keys


def _okx_chain_index(chain_id: Any) -> str | None:
    normalized = str(chain_id or "").strip().lower()
    if normalized.startswith("eip155:"):
        return normalized.split(":", 1)[1]
    return OKX_CHAIN_TO_CHAIN_INDEX.get(normalized)


def _needs_address_search(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) is None
        for key in ("symbol", "market_cap_usd", "liquidity_usd", "holders")
    )


def _search_exact_token(*, client, chain_index: str, address: str):
    try:
        candidates = client.search_tokens(query=address, chain_indexes=(chain_index,))
    except Exception as exc:
        return None, str(exc)
    normalized_address = address.lower() if address.lower().startswith("0x") else address
    for candidate in candidates:
        candidate_address = (
            candidate.address.lower()
            if candidate.address.lower().startswith("0x")
            else candidate.address
        )
        if str(candidate.chain_index) == str(chain_index) and candidate_address == normalized_address:
            return candidate, None
    return None, None


def _chunks(items: list[dict[str, str]], size: int):
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + size]
