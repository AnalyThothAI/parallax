from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from ..market.okx_chains import OKX_CHAIN_INDEX_TO_CHAIN
from .asset_market_sync import _okx_chain_index, _payload_hash
from .token_intent_resolver import TokenIntentResolver
from .token_radar_projection import WINDOW_MS, TokenRadarProjection
from .token_radar_projection_worker import DEFAULT_SCOPES, DEFAULT_WINDOWS

DEFAULT_DISCOVERY_LIMIT = 50
DEFAULT_REPROCESS_LIMIT = 500
DEFAULT_REPROCESS_WINDOW = "24h"
DEFAULT_RETRY_DELAY_MS = 15 * 60 * 1000


class TokenDiscoveryWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        dex_client=None,
        chain_indexes: tuple[str, ...] | list[str] = ("501", "1", "56", "8453"),
        interval_seconds: float = 30.0,
        task_limit: int = DEFAULT_DISCOVERY_LIMIT,
        reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
        projection_limit: int = 100,
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
    ) -> None:
        self.repository_session = repository_session
        self.dex_client = dex_client
        self.chain_indexes = tuple(str(item).strip() for item in chain_indexes if str(item).strip())
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.task_limit = max(1, int(task_limit))
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
                    task_limit=self.task_limit,
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
    task_limit: int = DEFAULT_DISCOVERY_LIMIT,
    reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
    projection_limit: int = 100,
    windows: tuple[str, ...] = DEFAULT_WINDOWS,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict[str, Any]:
    result = _empty_result(now_ms)
    tasks = repos.discovery.claim_due(now_ms=now_ms, limit=task_limit)
    result["tasks_claimed"] = len(tasks)
    affected_lookup_keys: set[str] = set()
    for task in tasks:
        try:
            task_result = _process_task(
                repos=repos,
                task=task,
                dex_client=dex_client,
                chain_indexes=tuple(chain_indexes),
                now_ms=now_ms,
            )
            _merge_task_result(result, task_result)
            affected_lookup_keys.update(task_result["affected_lookup_keys"])
            repos.discovery.complete(task_id=str(task["task_id"]), updated_at_ms=now_ms, commit=False)
            repos.conn.commit()
            result["tasks_done"] += 1
        except Exception as exc:
            repos.conn.rollback()
            repos.discovery.fail(
                task_id=str(task["task_id"]),
                last_error=str(exc),
                next_run_at_ms=now_ms + DEFAULT_RETRY_DELAY_MS,
                updated_at_ms=now_ms,
            )
            result["tasks_failed"] += 1
            result["provider_errors"] += 1
            result["errors"].append({"task_id": str(task["task_id"]), "error": str(exc)})
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
    result["discovery_task_counts"] = repos.discovery.counts()
    return result


def reprocess_recent_token_intents(
    *,
    repos,
    now_ms: int,
    window: str = DEFAULT_REPROCESS_WINDOW,
    limit: int = DEFAULT_REPROCESS_LIMIT,
    lookup_keys: list[str] | None = None,
) -> dict[str, Any]:
    since_ms = int(now_ms) - WINDOW_MS.get(window, WINDOW_MS[DEFAULT_REPROCESS_WINDOW])
    if lookup_keys:
        intents = repos.token_intent_lookup.recent_unresolved_intents_for_lookup_keys(
            lookup_keys,
            since_ms=since_ms,
            limit=limit,
        )
    else:
        intents = repos.token_intents.recent_unresolved(since_ms=since_ms, limit=limit)
    resolver = TokenIntentResolver(
        registry=repos.registry,
        resolutions=repos.intent_resolutions,
        discovery=repos.discovery,
    )
    reprocessed = 0
    resolved = 0
    for intent in intents:
        evidence = repos.token_evidence.evidence_for_intent(str(intent["intent_id"]))
        decision = resolver.resolve(
            intent,
            evidence,
            decision_time_ms=now_ms,
            persist=True,
            commit=False,
        )
        repos.token_intent_lookup.replace_lookup_keys(
            intent_id=decision.intent_id,
            event_id=decision.event_id,
            keys=decision.lookup_keys,
            source_evidence_id=intent.get("primary_evidence_id"),
            created_at_ms=now_ms,
            commit=False,
        )
        reprocessed += 1
        if decision.target_type and decision.target_id:
            resolved += 1
    repos.conn.commit()
    return {
        "window": window,
        "lookup_keys": lookup_keys or [],
        "reprocessed_intents": reprocessed,
        "resolved_intents": resolved,
        "since_ms": since_ms,
    }


def rebuild_token_radar_windows(
    *,
    repos,
    now_ms: int,
    windows: tuple[str, ...] = DEFAULT_WINDOWS,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
    limit: int = 100,
) -> dict[str, Any]:
    projection = TokenRadarProjection(repos=repos)
    result: dict[str, Any] = {"rows_written": 0, "source_rows": 0, "windows": {}}
    for window in windows:
        for scope in scopes:
            key = f"{window}:{scope}"
            window_result = projection.rebuild(window=window, scope=scope, now_ms=now_ms, limit=limit)
            result["windows"][key] = window_result
            result["rows_written"] += int(window_result.get("rows_written") or 0)
            result["source_rows"] += int(window_result.get("source_rows") or 0)
    return result


def _process_task(
    *,
    repos,
    task: dict[str, Any],
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    task_type = str(task.get("task_type") or "")
    payload = task.get("payload_json") or {}
    if task_type == "dex_symbol_lookup":
        return _process_dex_symbol_lookup(
            repos=repos,
            payload=payload,
            query_key=str(task.get("query_key") or ""),
            dex_client=dex_client,
            chain_indexes=chain_indexes,
            now_ms=now_ms,
        )
    if task_type == "address_lookup":
        return _process_address_lookup(
            repos=repos,
            payload=payload,
            dex_client=dex_client,
            chain_indexes=chain_indexes,
            now_ms=now_ms,
        )
    if task_type == "cex_pricefeed_lookup":
        return _process_cex_pricefeed_lookup(repos=repos, payload=payload)
    return {"affected_lookup_keys": [], "search_requests": 0, "search_hits": 0}


def _process_dex_symbol_lookup(
    *,
    repos,
    payload: dict[str, Any],
    query_key: str,
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_client is None:
        raise RuntimeError("dex discovery client is not configured")
    symbol = _normalize_symbol(payload.get("symbol") or query_key.removeprefix("symbol:"))
    if not symbol:
        return _task_result()
    candidates = dex_client.search_tokens(query=symbol, chain_indexes=chain_indexes)
    result = _task_result(search_requests=1)
    for candidate in candidates:
        if _normalize_symbol(getattr(candidate, "symbol", None)) != symbol:
            continue
        written = _write_dex_candidate(repos=repos, candidate=candidate, now_ms=now_ms)
        if not written:
            continue
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
    payload: dict[str, Any],
    dex_client,
    chain_indexes: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_client is None:
        raise RuntimeError("dex discovery client is not configured")
    address = _normalize_address(payload.get("address"))
    if not address:
        return _task_result()
    chain_id = _chain_id(payload.get("chain_id"))
    requested_chains = (_okx_chain_index(chain_id),) if chain_id else chain_indexes
    requested_chains = tuple(chain for chain in requested_chains if chain)
    if not requested_chains:
        return _task_result()
    candidates = dex_client.search_tokens(query=address, chain_indexes=requested_chains)
    result = _task_result(search_requests=1)
    for candidate in candidates:
        candidate_address = _normalize_address(getattr(candidate, "address", None))
        candidate_chain = _chain_id_from_okx_index(getattr(candidate, "chain_index", None))
        if candidate_address != address:
            continue
        if chain_id and candidate_chain != chain_id:
            continue
        written = _write_dex_candidate(repos=repos, candidate=candidate, now_ms=now_ms)
        if not written:
            continue
        result["search_hits"] += 1
        result["assets_written"] += 1
        result["pricefeeds_written"] += 1
        result["price_observations_written"] += 1
        if candidate_chain:
            result["affected_lookup_keys"].append(f"address:{candidate_chain}:{address}")
    if result["search_hits"]:
        result["affected_lookup_keys"].append(f"address:{chain_id or 'unknown'}:{address}")
    return result


def _process_cex_pricefeed_lookup(*, repos, payload: dict[str, Any]) -> dict[str, Any]:
    exchange = str(payload.get("exchange") or "").strip().lower()
    native_market_id = str(payload.get("native_market_id") or "").strip().upper()
    if not exchange or not native_market_id:
        return _task_result()
    pricefeed = repos.registry.find_cex_pricefeed(exchange=exchange, native_market_id=native_market_id)
    result = _task_result()
    if pricefeed:
        result["search_hits"] = 1
        result["affected_lookup_keys"].append(f"cex_pricefeed:{exchange}:{native_market_id}")
    return result


def _write_dex_candidate(*, repos, candidate, now_ms: int) -> bool:
    chain_id = _chain_id_from_okx_index(getattr(candidate, "chain_index", None))
    address = _normalize_address(getattr(candidate, "address", None))
    symbol = _normalize_symbol(getattr(candidate, "symbol", None))
    if not chain_id or not address or not symbol:
        return False
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
    return True


def _merge_task_result(result: dict[str, Any], task_result: dict[str, Any]) -> None:
    for key in (
        "search_requests",
        "search_hits",
        "assets_written",
        "pricefeeds_written",
        "price_observations_written",
    ):
        result[key] += int(task_result.get(key) or 0)


def _empty_result(now_ms: int) -> dict[str, Any]:
    return {
        "now_ms": int(now_ms),
        "tasks_claimed": 0,
        "tasks_done": 0,
        "tasks_failed": 0,
        "provider_errors": 0,
        "search_requests": 0,
        "search_hits": 0,
        "assets_written": 0,
        "pricefeeds_written": 0,
        "price_observations_written": 0,
        "reprocessed_intents": 0,
        "reprocess": None,
        "projection": {"rows_written": 0, "source_rows": 0, "windows": {}},
        "discovery_task_counts": {},
        "errors": [],
    }


def _task_result(
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
        "affected_lookup_keys": [],
    }


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
