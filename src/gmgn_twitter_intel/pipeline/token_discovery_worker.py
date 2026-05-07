from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from ..market.okx_chains import OKX_CHAIN_INDEX_TO_CHAIN
from ..storage.discovery_repository import DISCOVERY_PROVIDER
from .asset_market_sync import _okx_chain_index, _payload_hash
from .token_radar_projection import WINDOW_MS
from .token_radar_projection_worker import DEFAULT_SCOPES, DEFAULT_WINDOWS
from .token_resolution_refresh import (
    DEFAULT_REPROCESS_LIMIT,
    DEFAULT_REPROCESS_WINDOW,
    rebuild_token_radar_windows,
    reprocess_recent_token_intents,
)

DEFAULT_DISCOVERY_LIMIT = 50
DEFAULT_RETRY_DELAY_MS = 15 * 60 * 1000
FOUND_SYMBOL_REFRESH_MS = 15 * 60 * 1000
NOT_FOUND_SYMBOL_REFRESH_MS = 5 * 60 * 1000
FOUND_ADDRESS_REFRESH_MS = 24 * 60 * 60 * 1000
NOT_FOUND_ADDRESS_REFRESH_MS = 5 * 60 * 1000


class TokenDiscoveryWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        dex_client=None,
        chain_indexes: tuple[str, ...] | list[str] = ("501", "1", "56", "8453"),
        interval_seconds: float = 30.0,
        lookup_limit: int = DEFAULT_DISCOVERY_LIMIT,
        reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
        projection_limit: int = 100,
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
    ) -> None:
        self.repository_session = repository_session
        self.dex_client = dex_client
        self.chain_indexes = tuple(str(item).strip() for item in chain_indexes if str(item).strip())
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.lookup_limit = max(1, int(lookup_limit))
        self.reprocess_limit = max(1, int(reprocess_limit))
        self.projection_limit = max(1, int(projection_limit))
        self.windows = tuple(windows)
        self.scopes = tuple(scopes)
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"token discovery worker failed: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = observed_at_ms
        self.last_error = None
        try:
            with self.repository_session() as repos:
                result = run_token_discovery_once(
                    repos=repos,
                    dex_client=self.dex_client,
                    chain_indexes=self.chain_indexes,
                    now_ms=observed_at_ms,
                    lookup_limit=self.lookup_limit,
                    reprocess_limit=self.reprocess_limit,
                    projection_limit=self.projection_limit,
                    windows=self.windows,
                    scopes=self.scopes,
                )
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        close = getattr(self.dex_client, "close", None)
        if close:
            close()


def run_token_discovery_once(
    *,
    repos,
    dex_client,
    chain_indexes: tuple[str, ...] | list[str],
    now_ms: int,
    lookup_limit: int = DEFAULT_DISCOVERY_LIMIT,
    reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
    projection_limit: int = 100,
    windows: tuple[str, ...] = DEFAULT_WINDOWS,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict[str, Any]:
    result = _empty_result(now_ms)
    since_ms = int(now_ms) - WINDOW_MS.get(DEFAULT_REPROCESS_WINDOW, WINDOW_MS["24h"])
    lookups = repos.discovery.due_lookup_keys(since_ms=since_ms, now_ms=now_ms, limit=lookup_limit)
    result["lookups_selected"] = len(lookups)
    affected_lookup_keys: set[str] = set()
    for lookup in lookups:
        lookup_key = str(lookup.get("lookup_key") or "")
        lookup_type = str(lookup.get("lookup_type") or "")
        try:
            repos.discovery.start_lookup(
                provider=DISCOVERY_PROVIDER,
                lookup_key=lookup_key,
                lookup_type=lookup_type,
                now_ms=now_ms,
                commit=False,
            )
            repos.conn.commit()
            lookup_result = _process_lookup(
                repos=repos,
                lookup_key=lookup_key,
                lookup_type=lookup_type,
                dex_client=dex_client,
                chain_indexes=tuple(chain_indexes),
                now_ms=now_ms,
            )
            _merge_lookup_result(result, lookup_result)
            candidate_ids = sorted(set(lookup_result["candidate_ids"]))
            status = "found" if candidate_ids else "not_found"
            changed = repos.discovery.finish_lookup(
                provider=DISCOVERY_PROVIDER,
                lookup_key=lookup_key,
                lookup_type=lookup_type,
                status=status,
                candidate_ids=candidate_ids,
                result_hash=_result_hash(candidate_ids),
                next_refresh_at_ms=now_ms + _refresh_ms(lookup_key=lookup_key, status=status),
                now_ms=now_ms,
                commit=False,
            )
            repos.conn.commit()
            result["lookups_done"] += 1
            if changed and lookup_result["affected_lookup_keys"]:
                affected_lookup_keys.update(lookup_result["affected_lookup_keys"])
        except Exception as exc:
            repos.conn.rollback()
            repos.discovery.fail_lookup(
                provider=DISCOVERY_PROVIDER,
                lookup_key=lookup_key,
                lookup_type=lookup_type or _lookup_type(lookup_key),
                last_error=str(exc),
                next_refresh_at_ms=now_ms + DEFAULT_RETRY_DELAY_MS,
                now_ms=now_ms,
            )
            result["lookups_failed"] += 1
            result["provider_errors"] += 1
            result["errors"].append({"lookup_key": lookup_key, "error": str(exc)})
    if affected_lookup_keys:
        reprocess_result = reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=sorted(affected_lookup_keys),
            now_ms=now_ms,
            window=DEFAULT_REPROCESS_WINDOW,
            limit=reprocess_limit,
        )
        result["reprocess"] = reprocess_result
        result["reprocessed_intents"] = reprocess_result["reprocessed_intents"]
    if result["reprocessed_intents"]:
        result["projection"] = rebuild_token_radar_windows(
            repos=repos,
            now_ms=now_ms,
            windows=windows,
            scopes=scopes,
            limit=projection_limit,
        )
    result["discovery_result_counts"] = repos.discovery.counts()
    return result


def _process_lookup(
    *,
    repos,
    lookup_key: str,
    lookup_type: str,
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if lookup_type == "dex_symbol_lookup":
        return _process_dex_symbol_lookup(
            repos=repos,
            lookup_key=lookup_key,
            dex_client=dex_client,
            chain_indexes=chain_indexes,
            now_ms=now_ms,
        )
    if lookup_type == "address_lookup":
        return _process_address_lookup(
            repos=repos,
            lookup_key=lookup_key,
            dex_client=dex_client,
            chain_indexes=chain_indexes,
            now_ms=now_ms,
        )
    return _lookup_result()


def _process_dex_symbol_lookup(
    *,
    repos,
    lookup_key: str,
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_client is None:
        raise RuntimeError("dex discovery client is not configured")
    symbol = _normalize_symbol(lookup_key.removeprefix("symbol:"))
    if not symbol:
        return _lookup_result()
    candidates = dex_client.search_tokens(query=symbol, chain_indexes=chain_indexes)
    result = _lookup_result(search_requests=1)
    for candidate in candidates:
        if _normalize_symbol(getattr(candidate, "symbol", None)) != symbol:
            continue
        asset_id = _write_dex_candidate(repos=repos, candidate=candidate, now_ms=now_ms)
        if not asset_id:
            continue
        result["candidate_ids"].append(asset_id)
        result["search_hits"] += 1
        result["assets_written"] += 1
        result["pricefeeds_written"] += 1
        result["price_observations_written"] += 1
    if result["search_hits"]:
        result["affected_lookup_keys"].extend([f"symbol:{symbol}", f"project_symbol:{symbol}", f"cex_token:{symbol}"])
    return result


def _process_address_lookup(
    *,
    repos,
    lookup_key: str,
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_client is None:
        raise RuntimeError("dex discovery client is not configured")
    parsed = _parse_address_lookup_key(lookup_key)
    address = parsed["address"]
    if not address:
        return _lookup_result()
    chain_id = _chain_id(parsed["chain_id"])
    requested_chains = (_okx_chain_index(chain_id),) if chain_id else chain_indexes
    requested_chains = tuple(chain for chain in requested_chains if chain)
    if not requested_chains:
        return _lookup_result()
    candidates = dex_client.search_tokens(query=address, chain_indexes=requested_chains)
    result = _lookup_result(search_requests=1)
    for candidate in candidates:
        candidate_address = _normalize_address(getattr(candidate, "address", None))
        candidate_chain = _chain_id_from_okx_index(getattr(candidate, "chain_index", None))
        if candidate_address != address:
            continue
        if chain_id and candidate_chain != chain_id:
            continue
        asset_id = _write_dex_candidate(repos=repos, candidate=candidate, now_ms=now_ms)
        if not asset_id:
            continue
        result["candidate_ids"].append(asset_id)
        result["search_hits"] += 1
        result["assets_written"] += 1
        result["pricefeeds_written"] += 1
        result["price_observations_written"] += 1
        if candidate_chain:
            result["affected_lookup_keys"].append(f"address:{candidate_chain}:{address}")
    if result["search_hits"]:
        result["affected_lookup_keys"].append(f"address:{chain_id or 'unknown'}:{address}")
    return result


def _write_dex_candidate(*, repos, candidate, now_ms: int) -> str | None:
    chain_id = _chain_id_from_okx_index(getattr(candidate, "chain_index", None))
    address = _normalize_address(getattr(candidate, "address", None))
    symbol = _normalize_symbol(getattr(candidate, "symbol", None))
    if not chain_id or not address or not symbol:
        return None
    asset = repos.registry.upsert_chain_asset(
        chain_id=chain_id,
        address=address,
        symbol=symbol,
        name=getattr(candidate, "name", None),
        decimals=None,
        source="okx_dex_search",
        observed_at_ms=now_ms,
        commit=False,
    )
    pricefeed = repos.registry.upsert_pricefeed(
        feed_type="dex_token",
        provider="okx_dex_search",
        subject_type="Asset",
        subject_id=str(asset["asset_id"]),
        observed_at_ms=now_ms,
        chain_id=str(asset["chain_id"]),
        address=str(asset["address"]),
        base_asset_id=str(asset["asset_id"]),
        base_symbol=symbol,
        commit=False,
    )
    repos.price_observations.insert_observation(
        provider="okx_dex_search",
        pricefeed_id=str(pricefeed["pricefeed_id"]),
        observed_at_ms=now_ms,
        subject_type="Asset",
        subject_id=str(asset["asset_id"]),
        price_usd=getattr(candidate, "price_usd", None),
        price_basis="usd" if getattr(candidate, "price_usd", None) is not None else "unavailable",
        market_cap_usd=getattr(candidate, "market_cap_usd", None),
        liquidity_usd=getattr(candidate, "liquidity_usd", None),
        holders=getattr(candidate, "holders", None),
        raw_payload={**getattr(candidate, "raw", {}), "payload_hash": _payload_hash(getattr(candidate, "raw", {}))},
        commit=False,
    )
    return str(asset["asset_id"])


def _merge_lookup_result(result: dict[str, Any], lookup_result: dict[str, Any]) -> None:
    for key in (
        "search_requests",
        "search_hits",
        "assets_written",
        "pricefeeds_written",
        "price_observations_written",
    ):
        result[key] += int(lookup_result.get(key) or 0)


def _empty_result(now_ms: int) -> dict[str, Any]:
    return {
        "now_ms": int(now_ms),
        "lookups_selected": 0,
        "lookups_done": 0,
        "lookups_failed": 0,
        "provider_errors": 0,
        "search_requests": 0,
        "search_hits": 0,
        "assets_written": 0,
        "pricefeeds_written": 0,
        "price_observations_written": 0,
        "reprocessed_intents": 0,
        "reprocess": None,
        "projection": {"rows_written": 0, "source_rows": 0, "windows": {}},
        "discovery_result_counts": {},
        "errors": [],
    }


def _lookup_result(
    *,
    search_requests: int = 0,
    search_hits: int = 0,
) -> dict[str, Any]:
    return {
        "search_requests": int(search_requests),
        "search_hits": int(search_hits),
        "assets_written": 0,
        "pricefeeds_written": 0,
        "price_observations_written": 0,
        "candidate_ids": [],
        "affected_lookup_keys": [],
    }


def _lookup_type(lookup_key: str) -> str:
    if lookup_key.startswith("symbol:"):
        return "dex_symbol_lookup"
    if lookup_key.startswith("address:"):
        return "address_lookup"
    return "unsupported"


def _parse_address_lookup_key(lookup_key: str) -> dict[str, str | None]:
    value = lookup_key.removeprefix("address:")
    chain_id, separator, address = value.rpartition(":")
    if not separator:
        return {"chain_id": None, "address": _normalize_address(value)}
    if chain_id == "unknown":
        chain_id = ""
    return {"chain_id": chain_id or None, "address": _normalize_address(address)}


def _refresh_ms(*, lookup_key: str, status: str) -> int:
    if lookup_key.startswith("address:"):
        return FOUND_ADDRESS_REFRESH_MS if status == "found" else NOT_FOUND_ADDRESS_REFRESH_MS
    return FOUND_SYMBOL_REFRESH_MS if status == "found" else NOT_FOUND_SYMBOL_REFRESH_MS


def _result_hash(candidate_ids: list[str]) -> str:
    payload = json.dumps(sorted(set(candidate_ids)), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chain_id_from_okx_index(value: Any) -> str | None:
    chain = OKX_CHAIN_INDEX_TO_CHAIN.get(str(value or "").strip())
    return _chain_id(chain)


def _chain_id(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("eip155:"):
        return normalized
    if normalized in {"eth", "ethereum"}:
        return "eip155:1"
    if normalized in {"bsc", "bnb", "bnb_chain"}:
        return "eip155:56"
    if normalized == "base":
        return "eip155:8453"
    if normalized in {"sol", "solana"}:
        return "solana"
    return normalized


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _normalize_address(value: Any) -> str:
    text = str(value or "").strip()
    return text.lower() if text.lower().startswith("0x") else text


def _now_ms() -> int:
    return int(time.time() * 1000)
