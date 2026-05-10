from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.asset_market.queries.pending_market_observation_query import (
    PendingMarketObservationQuery,
)

from .asset_market_sync import DEX_PRICE_BATCH_SIZE, _okx_chain_index

MESSAGE_MARKET_HOT_LOOKBACK_MS = 60 * 60 * 1000


def observe_message_market(
    *,
    repos,
    cex_client=None,
    dex_client=None,
    now_ms: int,
    limit: int = 100,
) -> dict[str, Any]:
    rows = _select_pending_rows(repos.conn, now_ms=now_ms, limit=limit)
    result = {
        "rows_selected": len(rows),
        "cex_ticker_requests": 0,
        "dex_price_requests": 0,
        "observations_written": 0,
        "skipped_missing_pricefeed": 0,
        "skipped_missing_provider": 0,
        "skipped_missing_market": 0,
    }
    cex_quotes = _fetch_cex_quotes(rows, cex_client=cex_client, result=result)
    dex_quotes = _fetch_dex_quotes(rows, dex_client=dex_client, result=result)
    for row in rows:
        target_type = str(row.get("target_type") or "")
        if target_type == "CexToken":
            written = _write_cex_observation(
                repos=repos,
                row=row,
                ticker=cex_quotes.get(str(row.get("pricefeed_id") or "")),
                now_ms=now_ms,
                result=result,
            )
        elif target_type == "Asset":
            written = _write_dex_observation(
                repos=repos,
                row=row,
                price=dex_quotes.get(_dex_key(row)),
                now_ms=now_ms,
                result=result,
            )
        else:
            written = False
        if written:
            result["observations_written"] += 1
    if result["observations_written"]:
        repos.conn.commit()
    return result


def _select_pending_rows(conn, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
    return PendingMarketObservationQuery(conn).pending_rows(now_ms=now_ms, limit=limit)


def _fetch_cex_quotes(rows: list[dict[str, Any]], *, cex_client, result: dict[str, Any]) -> dict[str, Any]:
    quotes: dict[str, Any] = {}
    if cex_client is None:
        if any(row.get("target_type") == "CexToken" for row in rows):
            result["skipped_missing_provider"] += 1
        return quotes
    request_by_feed: dict[str, str] = {}
    for row in rows:
        if row.get("target_type") != "CexToken":
            continue
        pricefeed_id = str(row.get("pricefeed_id") or "")
        native_market_id = str(row.get("native_market_id") or "").strip().upper()
        if not pricefeed_id or not native_market_id:
            result["skipped_missing_pricefeed"] += 1
            continue
        request_by_feed.setdefault(pricefeed_id, native_market_id)
    for pricefeed_id, inst_id in request_by_feed.items():
        result["cex_ticker_requests"] += 1
        quotes[pricefeed_id] = cex_client.ticker(inst_id=inst_id)
    return quotes


def _fetch_dex_quotes(rows: list[dict[str, Any]], *, dex_client, result: dict[str, Any]) -> dict[tuple[str, str], Any]:
    quotes: dict[tuple[str, str], Any] = {}
    if dex_client is None:
        if any(row.get("target_type") == "Asset" for row in rows):
            result["skipped_missing_provider"] += 1
        return quotes
    request_items: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if row.get("target_type") != "Asset":
            continue
        chain_index = _okx_chain_index(row.get("asset_chain_id"))
        address = str(row.get("asset_address") or "").strip()
        if not chain_index or not address:
            result["skipped_missing_pricefeed"] += 1
            continue
        normalized = _normalize_address(address)
        request_items.setdefault(
            (chain_index, normalized),
            {"chainIndex": chain_index, "tokenContractAddress": normalized},
        )
    items = list(request_items.values())
    for chunk in _chunks(items, DEX_PRICE_BATCH_SIZE):
        if not chunk:
            continue
        result["dex_price_requests"] += 1
        for price in dex_client.token_prices(chunk):
            quotes[(str(price.chain_index), _normalize_address(price.address))] = price
    return quotes


def _write_cex_observation(*, repos, row: dict[str, Any], ticker, now_ms: int, result: dict[str, Any]) -> bool:
    if ticker is None:
        result["skipped_missing_market"] += 1
        return False
    pricefeed_id = str(row.get("pricefeed_id") or "")
    quote_symbol = str(row.get("pricefeed_quote_symbol") or "").strip().upper() or None
    if not pricefeed_id:
        result["skipped_missing_pricefeed"] += 1
        return False
    price_basis = _cex_price_basis(quote_symbol)
    repos.price_observations.insert_observation(
        provider="okx_cex",
        pricefeed_id=pricefeed_id,
        observed_at_ms=now_ms,
        subject_type="CexToken",
        subject_id=str(row["target_id"]),
        price_usd=ticker.last_price if price_basis == "quote_as_usd" else None,
        price_quote=ticker.last_price,
        quote_symbol=quote_symbol,
        price_basis=price_basis,
        volume_24h_usd=ticker.volume_24h,
        open_interest_usd=ticker.open_interest,
        source_event_id=str(row["event_id"]),
        source_intent_id=str(row["intent_id"]),
        source_resolution_id=str(row["resolution_id"]),
        observation_kind="message_quote",
        event_received_at_ms=int(row["event_received_at_ms"]),
        raw_payload={**ticker.raw, "payload_hash": _payload_hash(ticker.raw)},
        commit=False,
    )
    return True


def _write_dex_observation(*, repos, row: dict[str, Any], price, now_ms: int, result: dict[str, Any]) -> bool:
    if price is None:
        result["skipped_missing_market"] += 1
        return False
    pricefeed = repos.registry.upsert_pricefeed(
        feed_type="dex_token",
        provider="okx_dex_price",
        subject_type="Asset",
        subject_id=str(row["target_id"]),
        observed_at_ms=price.observed_at_ms or now_ms,
        chain_id=str(row["asset_chain_id"]),
        address=str(row["asset_address"]),
        base_asset_id=str(row["target_id"]),
        base_symbol=str(row["asset_symbol"]) if row.get("asset_symbol") else None,
        commit=False,
    )
    repos.price_observations.insert_observation(
        provider="okx_dex_price",
        pricefeed_id=str(pricefeed["pricefeed_id"]),
        observed_at_ms=price.observed_at_ms or now_ms,
        subject_type="Asset",
        subject_id=str(row["target_id"]),
        price_usd=price.price_usd,
        price_basis="usd",
        market_cap_usd=row.get("asset_market_cap_usd"),
        liquidity_usd=row.get("asset_liquidity_usd"),
        holders=row.get("asset_holders"),
        source_event_id=str(row["event_id"]),
        source_intent_id=str(row["intent_id"]),
        source_resolution_id=str(row["resolution_id"]),
        observation_kind="message_quote",
        event_received_at_ms=int(row["event_received_at_ms"]),
        raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
        commit=False,
    )
    return True


def _dex_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_okx_chain_index(row.get("asset_chain_id")) or "", _normalize_address(str(row.get("asset_address") or "")))


def _normalize_address(address: str) -> str:
    stripped = str(address).strip()
    return stripped.lower() if stripped.lower().startswith("0x") else stripped


def _cex_price_basis(quote_symbol: str | None) -> str:
    return "quote_as_usd" if str(quote_symbol or "").upper() in {"USD", "USDT", "USDC"} else "quote"


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _chunks(items: list[dict[str, str]], size: int):
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + size]
