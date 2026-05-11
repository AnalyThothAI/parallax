from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import DexTokenCandidate, DexTokenPriceRequest

from ..identity_evidence_policy import (
    CONFIDENCE_MANUAL,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)
from .market_freshness_demand import prioritize_market_refresh_candidates

DEX_PRICE_BATCH_SIZE = 20
RADAR_PRICE_CANDIDATE_LOOKBACK_MS = 24 * 60 * 60 * 1000
RADAR_PRICE_HOT_LOOKBACK_MS = 60 * 60 * 1000
RADAR_PRICE_REFRESH_SCAN_MULTIPLIER = 5
EXACT_IDENTITY_CONFIDENCES = frozenset({CONFIDENCE_MANUAL, CONFIDENCE_PROVIDER_EXACT})


def sync_cex_universe(
    *,
    registry: Any,
    price_observations: Any,
    cex_market: Any,
    inst_types: tuple[str, ...] | list[str],
    observed_at_ms: int,
) -> dict[str, Any]:
    normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
    cex_tokens_written = 0
    pricefeeds_written = 0
    observations_written = 0
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


def sync_dex_prices(
    *,
    registry: Any,
    identity_evidence: Any,
    price_observations: Any,
    dex_market: Any,
    observed_at_ms: int,
    stale_after_ms: int,
    limit: int,
    radar_since_ms: int | None = None,
    hot_since_ms: int | None = None,
    hot_stale_after_ms: int | None = None,
    warm_stale_after_ms: int | None = None,
    refresh_universe: str = "radar_candidates",
) -> dict[str, Any]:
    resolved_limit = max(0, int(limit))
    resolved_radar_since_ms = (
        int(radar_since_ms) if radar_since_ms is not None else int(observed_at_ms) - RADAR_PRICE_CANDIDATE_LOOKBACK_MS
    )
    resolved_hot_since_ms = (
        int(hot_since_ms) if hot_since_ms is not None else int(observed_at_ms) - RADAR_PRICE_HOT_LOOKBACK_MS
    )
    resolved_hot_stale_after_ms = max(
        0,
        int(hot_stale_after_ms) if hot_stale_after_ms is not None else int(stale_after_ms),
    )
    resolved_warm_stale_after_ms = max(
        0,
        int(warm_stale_after_ms) if warm_stale_after_ms is not None else int(stale_after_ms),
    )
    query_stale_after_ms = min(
        max(0, int(stale_after_ms)),
        resolved_hot_stale_after_ms,
        resolved_warm_stale_after_ms,
    )
    candidate_rows = registry.chain_assets_needing_radar_price_refresh(
        stale_before_ms=int(observed_at_ms) - query_stale_after_ms,
        radar_since_ms=resolved_radar_since_ms,
        hot_since_ms=resolved_hot_since_ms,
        limit=_candidate_scan_limit(resolved_limit),
    )
    rows = prioritize_market_refresh_candidates(
        candidate_rows,
        now_ms=int(observed_at_ms),
        hot_since_ms=resolved_hot_since_ms,
        hot_stale_after_ms=resolved_hot_stale_after_ms,
        warm_stale_after_ms=resolved_warm_stale_after_ms,
    )[:resolved_limit]
    pricefeeds_written = 0
    observations_written = 0
    identity_verification_requests = 0
    identity_verification_hits = 0
    identity_verification_errors = 0
    affected_lookup_keys: set[str] = set()
    for index, row in enumerate(rows):
        chain_id = str(row.get("chain_id") or "").strip()
        address = str(row.get("address") or "").strip()
        if not chain_id or not address or not _needs_address_search(row):
            continue
        identity_verification_requests += 1
        candidate, search_error = _search_exact_token(dex_market=dex_market, chain_id=chain_id, address=address)
        if search_error:
            identity_verification_errors += 1
        if candidate is None:
            continue
        identity_verification_hits += 1
        asset = registry.upsert_chain_asset(
            chain_id=str(row["chain_id"]),
            address=address,
            observed_at_ms=observed_at_ms,
            commit=False,
        )
        identity_evidence.upsert_identity_evidence(
            asset_id=str(asset["asset_id"]),
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            provider="okx",
            lookup_mode="exact_address",
            chain_id=str(asset["chain_id"]),
            address=str(asset["address"]),
            symbol=candidate.symbol,
            name=candidate.name,
            decimals=None,
            confidence=CONFIDENCE_PROVIDER_EXACT,
            raw_payload={**candidate.raw, "payload_hash": _payload_hash(candidate.raw)},
            observed_at_ms=observed_at_ms,
            commit=False,
        )
        current_identity = identity_evidence.recompute_current_identity(
            str(asset["asset_id"]),
            now_ms=observed_at_ms,
            commit=False,
        )
        rows[index] = {
            **row,
            **asset,
            "symbol": current_identity.get("canonical_symbol") or candidate.symbol,
            "name": current_identity.get("canonical_name") or candidate.name,
            "decimals": current_identity.get("decimals"),
            "identity_confidence": current_identity.get("identity_confidence"),
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
    request_items: list[DexTokenPriceRequest] = []
    for row in rows:
        chain_id = str(row.get("chain_id") or "").strip()
        address = str(row.get("address") or "").strip()
        if not chain_id or not address:
            continue
        request_item = DexTokenPriceRequest(chain_id=chain_id, address=_normalize_address(address))
        request_items.append(request_item)
        asset_by_key[(chain_id, request_item.address)] = row

    price_requests = 0
    for chunk in _chunks(request_items, DEX_PRICE_BATCH_SIZE):
        if not chunk:
            continue
        price_requests += 1
        for price in dex_market.token_prices(chunk):
            key = (str(price.chain_id), _normalize_address(price.address))
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
                market_cap_usd=None,
                liquidity_usd=None,
                volume_24h_usd=None,
                open_interest_usd=None,
                holders=None,
                raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
                commit=False,
            )
            observations_written += 1
            affected_lookup_keys.update(_asset_lookup_keys(asset))
    registry.conn.commit()
    return {
        "assets_scanned": len(rows),
        "refresh_universe": refresh_universe,
        "refresh_candidates_selected": len(rows),
        "refresh_candidates_hot": sum(1 for row in rows if row.get("market_freshness_class") == "hot"),
        "refresh_candidates_stale": sum(1 for row in rows if row.get("market_freshness_status") == "stale"),
        "refresh_candidates_missing": sum(1 for row in rows if row.get("market_freshness_status") == "missing"),
        "identity_verification_requests": identity_verification_requests,
        "identity_verification_hits": identity_verification_hits,
        "identity_verification_errors": identity_verification_errors,
        "price_requests": price_requests,
        "pricefeeds_written": pricefeeds_written,
        "price_observations_written": observations_written,
        "affected_lookup_keys": sorted(affected_lookup_keys),
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate_scan_limit(limit: int) -> int:
    return max(0, int(limit)) * RADAR_PRICE_REFRESH_SCAN_MULTIPLIER


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


def _needs_address_search(row: dict[str, Any]) -> bool:
    return str(row.get("identity_confidence") or "").strip().lower() not in EXACT_IDENTITY_CONFIDENCES


def _search_exact_token(*, dex_market: Any, chain_id: str, address: str) -> tuple[DexTokenCandidate | None, str | None]:
    try:
        candidates = dex_market.search_tokens(query=address, chain_ids=(chain_id,))
    except Exception as exc:
        return None, str(exc)
    normalized_address = _normalize_address(address)
    for candidate in candidates:
        candidate_address = _normalize_address(candidate.address)
        if str(candidate.chain_id) == str(chain_id) and candidate_address == normalized_address:
            return candidate, None
    return None, None


def _normalize_address(address: Any) -> str:
    stripped = str(address or "").strip()
    return stripped.lower() if stripped.lower().startswith("0x") else stripped


def _chunks(items: list[DexTokenPriceRequest], size: int) -> Iterator[list[DexTokenPriceRequest]]:
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + size]
