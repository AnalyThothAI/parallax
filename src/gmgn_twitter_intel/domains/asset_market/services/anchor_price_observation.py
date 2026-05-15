from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    CexTicker,
    DexTokenQuote,
    DexTokenQuoteRequest,
)
from gmgn_twitter_intel.domains.asset_market.queries.pending_anchor_price_query import (
    PendingAnchorPriceQuery,
)
from gmgn_twitter_intel.domains.asset_market.types import MarketObservation, MarketTargetRef

ANCHOR_PRICE_DEX_BATCH_SIZE = 20

ANCHOR_PRICE_HOT_LOOKBACK_MS = 60 * 60 * 1000


def observe_anchor_prices(
    *,
    repos: Any,
    cex_market: Any = None,
    dex_quote_market: Any = None,
    now_ms: int,
    limit: int = 100,
) -> dict[str, Any]:
    rows = _select_pending_rows(repos.conn, now_ms=now_ms, limit=limit)
    result: dict[str, Any] = {
        "rows_selected": len(rows),
        "cex_ticker_requests": 0,
        "dex_price_requests": 0,
        "anchor_observations_written": 0,
        "skipped_missing_pricefeed": 0,
        "skipped_missing_provider": 0,
        "skipped_missing_market": 0,
        "provider_errors": 0,
        "errors": [],
        "written_targets": [],
    }
    cex_quotes = _fetch_cex_quotes(rows, cex_market=cex_market, result=result)
    dex_quotes = _fetch_dex_quotes(rows, dex_quote_market=dex_quote_market, result=result)
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
            result["anchor_observations_written"] += 1
            result["written_targets"].append({"target_type": target_type, "target_id": str(row.get("target_id"))})
    if result["anchor_observations_written"]:
        repos.conn.commit()
    return result


def anchor_price_empty_result(*, rows_selected: int = 0) -> dict[str, Any]:
    return {
        "rows_selected": int(rows_selected),
        "cex_ticker_requests": 0,
        "dex_price_requests": 0,
        "anchor_observations_written": 0,
        "skipped_missing_pricefeed": 0,
        "skipped_missing_provider": 0,
        "skipped_missing_market": 0,
        "provider_errors": 0,
        "errors": [],
        "written_targets": [],
    }


def select_pending_anchor_price_rows(*, repos: Any, now_ms: int, limit: int = 100) -> list[dict[str, Any]]:
    return _select_pending_rows(repos.conn, now_ms=now_ms, limit=limit)


def fetch_anchor_price_quotes(
    *,
    rows: list[dict[str, Any]],
    cex_market: Any = None,
    dex_quote_market: Any = None,
    result: dict[str, Any],
) -> tuple[dict[str, CexTicker | None], dict[tuple[str, str], DexTokenQuote]]:
    return (
        _fetch_cex_quotes(rows, cex_market=cex_market, result=result),
        _fetch_dex_quotes(rows, dex_quote_market=dex_quote_market, result=result),
    )


def write_anchor_price_observations(
    *,
    repos: Any,
    rows: list[dict[str, Any]],
    cex_quotes: dict[str, CexTicker | None],
    dex_quotes: dict[tuple[str, str], DexTokenQuote],
    now_ms: int,
    result: dict[str, Any],
) -> dict[str, Any]:
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
            result["anchor_observations_written"] += 1
            result["written_targets"].append({"target_type": target_type, "target_id": str(row.get("target_id"))})
    if result["anchor_observations_written"]:
        repos.conn.commit()
    return result


def _select_pending_rows(conn: Any, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
    return PendingAnchorPriceQuery(conn).pending_rows(now_ms=now_ms, limit=limit)


def _fetch_cex_quotes(
    rows: list[dict[str, Any]], *, cex_market: Any, result: dict[str, Any]
) -> dict[str, CexTicker | None]:
    quotes: dict[str, CexTicker | None] = {}
    if cex_market is None:
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
        quotes[pricefeed_id] = cex_market.ticker(inst_id=inst_id)
    return quotes


def _fetch_dex_quotes(
    rows: list[dict[str, Any]], *, dex_quote_market: Any, result: dict[str, Any]
) -> dict[tuple[str, str], DexTokenQuote]:
    quotes: dict[tuple[str, str], DexTokenQuote] = {}
    if dex_quote_market is None:
        if any(row.get("target_type") == "Asset" for row in rows):
            result["skipped_missing_provider"] += 1
        return quotes
    request_items: dict[tuple[str, str], DexTokenQuoteRequest] = {}
    for row in rows:
        if row.get("target_type") != "Asset":
            continue
        chain_id = str(row.get("asset_chain_id") or "").strip()
        address = str(row.get("asset_address") or "").strip()
        if not chain_id or not address:
            result["skipped_missing_pricefeed"] += 1
            continue
        normalized = _normalize_address(address)
        request_items.setdefault(
            (chain_id, normalized),
            DexTokenQuoteRequest(chain_id=chain_id, address=normalized),
        )
    items = list(request_items.values())
    for chunk in _chunks(items, ANCHOR_PRICE_DEX_BATCH_SIZE):
        if not chunk:
            continue
        result["dex_price_requests"] += 1
        try:
            chunk_quotes = dex_quote_market.token_quotes(chunk)
        except Exception as exc:
            if _is_provider_cooldown_error(exc):
                _record_dex_provider_error(result, exc=exc, tokens=len(chunk))
                break
            chunk_quotes, should_stop = _fetch_dex_quotes_individually(
                chunk,
                dex_quote_market=dex_quote_market,
                result=result,
            )
            if should_stop:
                break
        for price in chunk_quotes:
            quotes[(str(price.chain_id), _normalize_address(price.address))] = price
    return quotes


def _fetch_dex_quotes_individually(
    items: list[DexTokenQuoteRequest], *, dex_quote_market: Any, result: dict[str, Any]
) -> tuple[list[DexTokenQuote], bool]:
    quotes: list[DexTokenQuote] = []
    for item in items:
        result["dex_price_requests"] += 1
        try:
            quotes.extend(dex_quote_market.token_quotes([item]))
        except Exception as exc:
            _record_dex_provider_error(result, exc=exc, tokens=1)
            if _is_provider_cooldown_error(exc):
                return quotes, True
    return quotes, False


def _record_dex_provider_error(result: dict[str, Any], *, exc: Exception, tokens: int) -> None:
    result["provider_errors"] += 1
    result["errors"].append(
        {
            "provider": "gmgn_dex_quote",
            "error": str(exc),
            "tokens": tokens,
        }
    )


def _write_cex_observation(
    *, repos: Any, row: dict[str, Any], ticker: CexTicker | None, now_ms: int, result: dict[str, Any]
) -> bool:
    if ticker is None:
        result["skipped_missing_market"] += 1
        return False
    pricefeed_id = str(row.get("pricefeed_id") or "")
    quote_symbol = str(row.get("pricefeed_quote_symbol") or "").strip().upper() or None
    if not pricefeed_id:
        result["skipped_missing_pricefeed"] += 1
        return False
    price_basis = _cex_price_basis(quote_symbol)
    repos.price_observations.insert_market_observation(
        MarketObservation(
            target=MarketTargetRef(target_type="CexToken", target_id=str(row["target_id"])),
            observed_at_ms=int(now_ms),
            received_at_ms=int(now_ms),
            source="event_anchor",
            provider="okx",
            pricefeed_id=pricefeed_id,
            price_usd=ticker.last_price if price_basis == "quote_as_usd" else None,
            price_quote=ticker.last_price,
            quote_symbol=quote_symbol,
            price_basis=price_basis,
            market_cap_usd=None,
            liquidity_usd=None,
            holders=None,
            volume_24h_usd=ticker.volume_24h,
            open_interest_usd=ticker.open_interest,
            raw_payload_hash=_payload_hash(ticker.raw),
        ),
        observation_kind="event_anchor",
        source_event_id=str(row["event_id"]),
        source_intent_id=str(row["intent_id"]),
        source_resolution_id=str(row["resolution_id"]),
        event_received_at_ms=int(row["event_received_at_ms"]),
        commit=False,
    )
    return True


def _write_dex_observation(
    *, repos: Any, row: dict[str, Any], price: DexTokenQuote | None, now_ms: int, result: dict[str, Any]
) -> bool:
    if price is None:
        result["skipped_missing_market"] += 1
        return False
    pricefeed = repos.registry.upsert_pricefeed(
        feed_type="dex_token",
        provider="gmgn_dex_quote",
        subject_type="Asset",
        subject_id=str(row["target_id"]),
        observed_at_ms=price.observed_at_ms or now_ms,
        chain_id=str(row["asset_chain_id"]),
        address=str(row["asset_address"]),
        base_asset_id=str(row["target_id"]),
        base_symbol=str(row["asset_symbol"]) if row.get("asset_symbol") else None,
        commit=False,
    )
    repos.price_observations.insert_market_observation(
        MarketObservation(
            target=MarketTargetRef(target_type="Asset", target_id=str(row["target_id"])),
            observed_at_ms=int(price.observed_at_ms or now_ms),
            received_at_ms=int(now_ms),
            source="event_anchor",
            provider="gmgn_dex_quote",
            pricefeed_id=str(pricefeed["pricefeed_id"]),
            price_usd=price.price_usd,
            price_quote=None,
            quote_symbol="USD",
            price_basis="usd" if price.price_usd is not None else "unavailable",
            market_cap_usd=price.market_cap_usd,
            liquidity_usd=price.liquidity_usd,
            holders=price.holders,
            volume_24h_usd=price.volume_24h_usd,
            open_interest_usd=None,
            raw_payload_hash=_payload_hash(price.raw),
        ),
        observation_kind="event_anchor",
        source_event_id=str(row["event_id"]),
        source_intent_id=str(row["intent_id"]),
        source_resolution_id=str(row["resolution_id"]),
        event_received_at_ms=int(row["event_received_at_ms"]),
        commit=False,
    )
    return True


def _dex_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("asset_chain_id") or ""), _normalize_address(str(row.get("asset_address") or "")))


def _normalize_address(address: str) -> str:
    stripped = str(address).strip()
    return stripped.lower() if stripped.lower().startswith("0x") else stripped


def _cex_price_basis(quote_symbol: str | None) -> str:
    return "quote_as_usd" if str(quote_symbol or "").upper() in {"USD", "USDT", "USDC"} else "quote"


def _is_provider_cooldown_error(exc: Exception) -> bool:
    message = str(exc)
    return "HTTP 403" in message or "HTTP 429" in message or "RATE_LIMIT_BANNED" in message


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _chunks(items: list[DexTokenQuoteRequest], size: int) -> Iterator[list[DexTokenQuoteRequest]]:
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + size]
