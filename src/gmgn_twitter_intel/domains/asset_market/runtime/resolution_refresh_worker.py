from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    DEFAULT_REPROCESS_LIMIT,
    DEFAULT_REPROCESS_WINDOW,
    WINDOW_MS,
    deferred_token_radar_projection,
    reprocess_recent_token_intents,
)

from ..identity_evidence_policy import (
    CONFIDENCE_PROVIDER_CANDIDATE,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
)
from ..repositories.discovery_repository import DISCOVERY_PROVIDER, RUNNING_LOOKUP_TIMEOUT_MS

DEFAULT_DISCOVERY_LIMIT = 50
FOUND_SYMBOL_REFRESH_MS = 15 * 60 * 1000
NOT_FOUND_SYMBOL_REFRESH_MS = 5 * 60 * 1000
FOUND_ADDRESS_REFRESH_MS = 24 * 60 * 60 * 1000
NOT_FOUND_ADDRESS_REFRESH_MS = 5 * 60 * 1000
HOT_LOOKBACK_MS = WINDOW_MS["1h"]
HOT_NOT_FOUND_RETRY_MS = 60 * 1000
HOT_PROJECTION_WINDOWS = ("5m", "1h")
HOT_PROJECTION_SCOPES = ("all", "matched")
HOT_PROJECTION_LIMIT = 100
ERROR_REFRESH_BACKOFF_MS = (30_000, 60_000, 300_000, 1_800_000, 3_600_000)
MAX_DEX_SYMBOL_CANDIDATES_PER_CHAIN = 3


class ResolutionRefreshWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        dex_discovery_market: Any = None,
        dex_quote_market: Any = None,
        chain_ids: tuple[str, ...] | list[str] = ("solana", "eip155:1", "eip155:56", "eip155:8453", "ton"),
        wake_bus: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.dex_discovery_market = dex_discovery_market
        self.dex_quote_market = dex_quote_market
        configured_chain_ids = chain_ids if chain_ids else getattr(settings, "chain_ids", ())
        self.chain_ids = tuple(str(item).strip() for item in configured_chain_ids if str(item).strip())
        self.wake_bus = wake_bus
        self.max_attempts = max(1, int(getattr(settings, "max_attempts", 3) or 3))

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else _now_ms())
        result = await asyncio.to_thread(self._run_refresh_once, observed_at_ms)
        if result.get("resolution_wake_lookup_keys") and self.wake_bus is not None:
            self.wake_bus.notify_resolution_updated(lookup_keys=result["resolution_wake_lookup_keys"])
        result.pop("resolution_wake_lookup_keys", None)
        return WorkerResult(
            processed=int(result.get("lookups_done") or 0) + int(result.get("reprocessed_intents") or 0),
            failed=int(result.get("lookups_failed") or 0),
            notes={"result": result},
        )

    def _run_refresh_once(self, now_ms: int) -> dict[str, Any]:
        result = _empty_result(now_ms)
        with self.db.worker_session(self.name) as repos:
            lookups = repos.discovery.claim_due_lookup_keys(
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", DEFAULT_DISCOVERY_LIMIT))),
                lease_ms=RUNNING_LOOKUP_TIMEOUT_MS,
                lease_owner=self.name,
                hot_since_ms=int(now_ms) - HOT_LOOKBACK_MS,
                hot_not_found_retry_ms=HOT_NOT_FOUND_RETRY_MS,
            )
        result["lookups_selected"] = len(lookups)
        affected_lookup_keys: set[str] = set()
        processed_claims: list[dict[str, Any]] = []
        queue_due_by_lookup_key: dict[str, int] = {}
        for lookup in lookups:
            lookup_key = str(lookup.get("lookup_key") or "")
            lookup_type = str(lookup.get("lookup_type") or "")
            try:
                with self.db.worker_session(self.name) as repos:
                    repos.discovery.start_lookup(
                        provider=DISCOVERY_PROVIDER,
                        lookup_key=lookup_key,
                        lookup_type=lookup_type,
                        now_ms=now_ms,
                        commit=False,
                    )
                    repos.conn.commit()
                lookup_result = _fetch_lookup_provider_result(
                    lookup_key=lookup_key,
                    lookup_type=lookup_type,
                    dex_discovery_market=self.dex_discovery_market,
                    chain_ids=self.chain_ids,
                )
                with self.db.worker_session(self.name) as repos:
                    _persist_lookup_provider_result(repos=repos, lookup_result=lookup_result, now_ms=now_ms)
                    candidate_ids = sorted(set(lookup_result["candidate_ids"]))
                    status = "found" if candidate_ids else "not_found"
                    next_refresh_at_ms = now_ms + _refresh_ms(lookup_key=lookup_key, status=status)
                    repos.discovery.finish_lookup(
                        provider=DISCOVERY_PROVIDER,
                        lookup_key=lookup_key,
                        lookup_type=lookup_type,
                        status=status,
                        candidate_ids=candidate_ids,
                        result_hash=_result_hash(candidate_ids),
                        next_refresh_at_ms=next_refresh_at_ms,
                        now_ms=now_ms,
                        commit=False,
                    )
                    repos.conn.commit()
                processed_claims.append(dict(lookup))
                queue_due_by_lookup_key[lookup_key] = _next_queue_due_at_ms(
                    lookup=lookup,
                    status=status,
                    next_refresh_at_ms=next_refresh_at_ms,
                    now_ms=now_ms,
                )
                _merge_lookup_result(result, lookup_result)
                result["lookups_done"] += 1
                if lookup_result["affected_lookup_keys"]:
                    affected_lookup_keys.update(lookup_result["affected_lookup_keys"])
            except Exception as exc:
                retry_due_at_ms = now_ms + _refresh_ms(
                    lookup_key=lookup_key,
                    status="error",
                    error_count=int(lookup.get("error_count") or 0),
                )
                with self.db.worker_session(self.name) as repos:
                    repos.discovery.fail_lookup(
                        provider=DISCOVERY_PROVIDER,
                        lookup_key=lookup_key,
                        lookup_type=lookup_type or _lookup_type(lookup_key),
                        last_error=str(exc),
                        next_refresh_at_ms=retry_due_at_ms,
                        now_ms=now_ms,
                        commit=False,
                    )
                    if _claim_retry_budget_exhausted(lookup, max_attempts=self.max_attempts):
                        terminal = repos.discovery.terminalize_lookup_claims(
                            [lookup],
                            worker_name=self.name,
                            final_status="error",
                            final_reason="provider_error_retry_budget_exhausted",
                            now_ms=now_ms,
                            commit=False,
                        )
                        result["lookups_terminalized"] += int(terminal.get("terminalized") or 0)
                    else:
                        repos.discovery.reschedule_lookup_claims(
                            [lookup],
                            due_at_ms=retry_due_at_ms,
                            now_ms=now_ms,
                            last_error=str(exc),
                            commit=False,
                        )
                    repos.conn.commit()
                result["lookups_failed"] += 1
                result["provider_errors"] += 1
                result["errors"].append({"lookup_key": lookup_key, "error": str(exc)})
        resolved_lookup_keys: set[str] = set()
        if affected_lookup_keys:
            sorted_lookup_keys = sorted(affected_lookup_keys)
            result["affected_lookup_keys"] = sorted_lookup_keys
            with self.db.worker_session(self.name) as repos:
                reprocess_result = reprocess_recent_token_intents(
                    repos=repos,
                    lookup_keys=sorted_lookup_keys,
                    now_ms=now_ms,
                    window=DEFAULT_REPROCESS_WINDOW,
                    limit=max(1, int(getattr(self.settings, "reprocess_limit", DEFAULT_REPROCESS_LIMIT))),
                )
            result["reprocess"] = reprocess_result
            result["reprocessed_intents"] = reprocess_result["reprocessed_intents"]
            if reprocess_result["resolved_intents"]:
                result["resolution_wake_lookup_keys"] = sorted_lookup_keys
                resolved_lookup_keys.update(sorted_lookup_keys)
        if processed_claims:
            _complete_lookup_claims(
                db=self.db,
                worker_name=self.name,
                claims=processed_claims,
                resolved_lookup_keys=resolved_lookup_keys,
                due_by_lookup_key=queue_due_by_lookup_key,
                now_ms=now_ms,
                max_attempts=self.max_attempts,
                result=result,
            )
        with self.db.worker_session(self.name) as repos:
            result["discovery_result_counts"] = repos.discovery.counts()
        return result


def run_resolution_refresh_once(
    *,
    repos: Any,
    dex_discovery_market: Any,
    dex_quote_market: Any = None,
    chain_ids: tuple[str, ...] | list[str],
    now_ms: int,
    lookup_limit: int = DEFAULT_DISCOVERY_LIMIT,
    reprocess_limit: int = DEFAULT_REPROCESS_LIMIT,
    max_attempts: int = 3,
    wake_bus: Any | None = None,
) -> dict[str, Any]:
    result = _empty_result(now_ms)
    lookups = repos.discovery.claim_due_lookup_keys(
        now_ms=now_ms,
        limit=lookup_limit,
        lease_ms=RUNNING_LOOKUP_TIMEOUT_MS,
        lease_owner="resolution_refresh",
        hot_since_ms=int(now_ms) - HOT_LOOKBACK_MS,
        hot_not_found_retry_ms=HOT_NOT_FOUND_RETRY_MS,
    )
    result["lookups_selected"] = len(lookups)
    affected_lookup_keys: set[str] = set()
    processed_claims: list[dict[str, Any]] = []
    queue_due_by_lookup_key: dict[str, int] = {}
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
                dex_discovery_market=dex_discovery_market,
                chain_ids=tuple(chain_ids),
                now_ms=now_ms,
            )
            _merge_lookup_result(result, lookup_result)
            candidate_ids = sorted(set(lookup_result["candidate_ids"]))
            status = "found" if candidate_ids else "not_found"
            next_refresh_at_ms = now_ms + _refresh_ms(lookup_key=lookup_key, status=status)
            repos.discovery.finish_lookup(
                provider=DISCOVERY_PROVIDER,
                lookup_key=lookup_key,
                lookup_type=lookup_type,
                status=status,
                candidate_ids=candidate_ids,
                result_hash=_result_hash(candidate_ids),
                next_refresh_at_ms=next_refresh_at_ms,
                now_ms=now_ms,
                commit=False,
            )
            repos.conn.commit()
            processed_claims.append(dict(lookup))
            queue_due_by_lookup_key[lookup_key] = _next_queue_due_at_ms(
                lookup=lookup,
                status=status,
                next_refresh_at_ms=next_refresh_at_ms,
                now_ms=now_ms,
            )
            result["lookups_done"] += 1
            if lookup_result["affected_lookup_keys"]:
                affected_lookup_keys.update(lookup_result["affected_lookup_keys"])
        except Exception as exc:
            repos.conn.rollback()
            retry_due_at_ms = now_ms + _refresh_ms(
                lookup_key=lookup_key,
                status="error",
                error_count=int(lookup.get("error_count") or 0),
            )
            repos.discovery.fail_lookup(
                provider=DISCOVERY_PROVIDER,
                lookup_key=lookup_key,
                lookup_type=lookup_type or _lookup_type(lookup_key),
                last_error=str(exc),
                next_refresh_at_ms=retry_due_at_ms,
                now_ms=now_ms,
                commit=False,
            )
            if _claim_retry_budget_exhausted(lookup, max_attempts=max_attempts):
                terminal = repos.discovery.terminalize_lookup_claims(
                    [lookup],
                    worker_name="resolution_refresh",
                    final_status="error",
                    final_reason="provider_error_retry_budget_exhausted",
                    now_ms=now_ms,
                    commit=False,
                )
                result["lookups_terminalized"] += int(terminal.get("terminalized") or 0)
            else:
                repos.discovery.reschedule_lookup_claims(
                    [lookup],
                    due_at_ms=retry_due_at_ms,
                    now_ms=now_ms,
                    last_error=str(exc),
                    commit=False,
                )
            repos.conn.commit()
            result["lookups_failed"] += 1
            result["provider_errors"] += 1
            result["errors"].append({"lookup_key": lookup_key, "error": str(exc)})
    resolved_lookup_keys: set[str] = set()
    if affected_lookup_keys:
        sorted_lookup_keys = sorted(affected_lookup_keys)
        result["affected_lookup_keys"] = sorted_lookup_keys
        reprocess_result = reprocess_recent_token_intents(
            repos=repos,
            lookup_keys=sorted_lookup_keys,
            now_ms=now_ms,
            window=DEFAULT_REPROCESS_WINDOW,
            limit=reprocess_limit,
        )
        result["reprocess"] = reprocess_result
        result["reprocessed_intents"] = reprocess_result["reprocessed_intents"]
        if reprocess_result["resolved_intents"] and wake_bus is not None:
            wake_bus.notify_resolution_updated(lookup_keys=sorted_lookup_keys)
        if reprocess_result["resolved_intents"]:
            resolved_lookup_keys.update(sorted_lookup_keys)
    if processed_claims:
        _finish_lookup_claims(
            repos=repos,
            claims=processed_claims,
            resolved_lookup_keys=resolved_lookup_keys,
            due_by_lookup_key=queue_due_by_lookup_key,
            now_ms=now_ms,
            worker_name="resolution_refresh",
            max_attempts=max_attempts,
            result=result,
        )
    result["discovery_result_counts"] = repos.discovery.counts()
    return result


def _process_lookup(
    *,
    repos: Any,
    lookup_key: str,
    lookup_type: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if lookup_type == "dex_symbol_lookup":
        return _process_dex_symbol_lookup(
            repos=repos,
            lookup_key=lookup_key,
            dex_discovery_market=dex_discovery_market,
            chain_ids=chain_ids,
            now_ms=now_ms,
        )
    if lookup_type == "address_lookup":
        return _process_address_lookup(
            repos=repos,
            lookup_key=lookup_key,
            dex_discovery_market=dex_discovery_market,
            chain_ids=chain_ids,
            now_ms=now_ms,
        )
    return _lookup_result()


def _fetch_lookup_provider_result(
    *,
    lookup_key: str,
    lookup_type: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
) -> dict[str, Any]:
    if lookup_type == "dex_symbol_lookup":
        return _fetch_dex_symbol_lookup_result(
            lookup_key=lookup_key,
            dex_discovery_market=dex_discovery_market,
            chain_ids=chain_ids,
        )
    if lookup_type == "address_lookup":
        return _fetch_address_lookup_result(
            lookup_key=lookup_key,
            dex_discovery_market=dex_discovery_market,
            chain_ids=chain_ids,
        )
    return _lookup_result()


def _fetch_dex_symbol_lookup_result(
    *,
    lookup_key: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
) -> dict[str, Any]:
    if dex_discovery_market is None:
        raise RuntimeError("dex discovery client is not configured")
    symbol = _normalize_symbol(lookup_key.removeprefix("symbol:"))
    if not symbol:
        return _lookup_result()
    candidates = dex_discovery_market.search_tokens(query=symbol, chain_ids=chain_ids)
    provider_ranks = _provider_ranks(candidates)
    result = _lookup_result(search_requests=1)
    matched_candidates = [
        candidate for candidate in candidates if _normalize_symbol(getattr(candidate, "symbol", None)) == symbol
    ]
    retained_candidates = _retained_symbol_candidates(
        matched_candidates,
        per_chain_limit=MAX_DEX_SYMBOL_CANDIDATES_PER_CHAIN,
    )
    result["search_candidates_seen"] = len(matched_candidates)
    result["search_candidates_rejected"] = max(0, len(matched_candidates) - len(retained_candidates))
    result["_candidate_writes"] = [
        {
            "candidate": candidate,
            "evidence_kind": EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            "confidence": CONFIDENCE_PROVIDER_CANDIDATE,
            "lookup_mode": "symbol_search",
            "provider_rank": provider_ranks.get(_candidate_identity_key(candidate)),
        }
        for candidate in retained_candidates
    ]
    if retained_candidates:
        result["affected_lookup_keys"].extend([f"symbol:{symbol}", f"project_symbol:{symbol}", f"cex_token:{symbol}"])
    return result


def _fetch_address_lookup_result(
    *,
    lookup_key: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
) -> dict[str, Any]:
    if dex_discovery_market is None:
        raise RuntimeError("dex discovery client is not configured")
    parsed = _parse_address_lookup_key(lookup_key)
    address = parsed["address"]
    if not address:
        return _lookup_result()
    chain_id = _chain_id(parsed["chain_id"])
    requested_chains = (chain_id,) if chain_id else chain_ids
    requested_chains = tuple(chain for chain in requested_chains if chain)
    if not requested_chains:
        return _lookup_result()
    candidates = dex_discovery_market.search_tokens(query=address, chain_ids=requested_chains)
    result = _lookup_result(search_requests=1)
    writes = []
    for candidate in candidates:
        candidate_address = _normalize_address(getattr(candidate, "address", None))
        candidate_chain = _chain_id(getattr(candidate, "chain_id", None))
        if candidate_address != address:
            continue
        if chain_id and candidate_chain != chain_id:
            continue
        writes.append(
            {
                "candidate": candidate,
                "evidence_kind": EVIDENCE_OKX_DEX_EXACT_ADDRESS,
                "confidence": CONFIDENCE_PROVIDER_EXACT,
                "lookup_mode": "exact_address",
                "provider_rank": None,
            }
        )
        if candidate_chain:
            result["affected_lookup_keys"].append(f"address:{candidate_chain}:{address}")
    if writes:
        result["affected_lookup_keys"].append(f"address:{chain_id or 'unknown'}:{address}")
    result["_candidate_writes"] = writes
    return result


def _persist_lookup_provider_result(*, repos: Any, lookup_result: dict[str, Any], now_ms: int) -> None:
    for item in lookup_result.pop("_candidate_writes", []):
        asset_id = _write_dex_candidate(
            repos=repos,
            candidate=item["candidate"],
            now_ms=now_ms,
            evidence_kind=str(item["evidence_kind"]),
            confidence=str(item["confidence"]),
            lookup_mode=str(item["lookup_mode"]),
            provider_rank=item.get("provider_rank"),
        )
        if not asset_id:
            continue
        lookup_result["candidate_ids"].append(asset_id)
        lookup_result["search_hits"] += 1
        lookup_result["assets_written"] += 1


def _process_dex_symbol_lookup(
    *,
    repos: Any,
    lookup_key: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_discovery_market is None:
        raise RuntimeError("dex discovery client is not configured")
    symbol = _normalize_symbol(lookup_key.removeprefix("symbol:"))
    if not symbol:
        return _lookup_result()
    candidates = dex_discovery_market.search_tokens(query=symbol, chain_ids=chain_ids)
    provider_ranks = _provider_ranks(candidates)
    result = _lookup_result(search_requests=1)
    matched_candidates = [
        candidate for candidate in candidates if _normalize_symbol(getattr(candidate, "symbol", None)) == symbol
    ]
    retained_candidates = _retained_symbol_candidates(
        matched_candidates,
        per_chain_limit=MAX_DEX_SYMBOL_CANDIDATES_PER_CHAIN,
    )
    result["search_candidates_seen"] = len(matched_candidates)
    result["search_candidates_rejected"] = max(0, len(matched_candidates) - len(retained_candidates))
    retained_asset_ids: list[str] = []
    for candidate in retained_candidates:
        asset_id = _write_dex_candidate(
            repos=repos,
            candidate=candidate,
            now_ms=now_ms,
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
            lookup_mode="symbol_search",
            provider_rank=provider_ranks.get(_candidate_identity_key(candidate)),
        )
        if not asset_id:
            continue
        retained_asset_ids.append(asset_id)
        result["candidate_ids"].append(asset_id)
        result["search_hits"] += 1
        result["assets_written"] += 1
    if result["search_hits"]:
        result["affected_lookup_keys"].extend([f"symbol:{symbol}", f"project_symbol:{symbol}", f"cex_token:{symbol}"])
    return result


def _process_address_lookup(
    *,
    repos: Any,
    lookup_key: str,
    dex_discovery_market: Any,
    chain_ids: tuple[str, ...],
    now_ms: int,
) -> dict[str, Any]:
    if dex_discovery_market is None:
        raise RuntimeError("dex discovery client is not configured")
    parsed = _parse_address_lookup_key(lookup_key)
    address = parsed["address"]
    if not address:
        return _lookup_result()
    chain_id = _chain_id(parsed["chain_id"])
    requested_chains = (chain_id,) if chain_id else chain_ids
    requested_chains = tuple(chain for chain in requested_chains if chain)
    if not requested_chains:
        return _lookup_result()
    candidates = dex_discovery_market.search_tokens(query=address, chain_ids=requested_chains)
    result = _lookup_result(search_requests=1)
    for candidate in candidates:
        candidate_address = _normalize_address(getattr(candidate, "address", None))
        candidate_chain = _chain_id(getattr(candidate, "chain_id", None))
        if candidate_address != address:
            continue
        if chain_id and candidate_chain != chain_id:
            continue
        asset_id = _write_dex_candidate(
            repos=repos,
            candidate=candidate,
            now_ms=now_ms,
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            confidence=CONFIDENCE_PROVIDER_EXACT,
            lookup_mode="exact_address",
        )
        if not asset_id:
            continue
        result["candidate_ids"].append(asset_id)
        result["search_hits"] += 1
        result["assets_written"] += 1
        if candidate_chain:
            result["affected_lookup_keys"].append(f"address:{candidate_chain}:{address}")
    if result["search_hits"]:
        result["affected_lookup_keys"].append(f"address:{chain_id or 'unknown'}:{address}")
    return result


def _write_dex_candidate(
    *,
    repos: Any,
    candidate: Any,
    now_ms: int,
    evidence_kind: str,
    confidence: str,
    lookup_mode: str,
    provider_rank: int | None = None,
) -> str | None:
    chain_id = _chain_id(getattr(candidate, "chain_id", None))
    address = _normalize_address(getattr(candidate, "address", None))
    symbol = _normalize_symbol(getattr(candidate, "symbol", None))
    if not chain_id or not address or not symbol:
        return None
    asset = repos.registry.upsert_chain_asset(
        chain_id=chain_id,
        address=address,
        observed_at_ms=now_ms,
        commit=False,
    )
    raw_payload = {**getattr(candidate, "raw", {}), "payload_hash": _payload_hash(getattr(candidate, "raw", {}))}
    if provider_rank is not None:
        raw_payload["provider_rank"] = provider_rank
    repos.identity_evidence.upsert_identity_evidence(
        asset_id=str(asset["asset_id"]),
        evidence_kind=evidence_kind,
        provider="okx",
        lookup_mode=lookup_mode,
        chain_id=str(asset["chain_id"]),
        address=str(asset["address"]),
        symbol=symbol,
        name=getattr(candidate, "name", None),
        decimals=None,
        confidence=confidence,
        raw_payload=raw_payload,
        observed_at_ms=now_ms,
        commit=False,
    )
    repos.identity_evidence.recompute_current_identity(str(asset["asset_id"]), now_ms=now_ms, commit=False)
    return str(asset["asset_id"])


def _merge_lookup_result(result: dict[str, Any], lookup_result: dict[str, Any]) -> None:
    for key in (
        "search_requests",
        "search_hits",
        "search_candidates_seen",
        "search_candidates_rejected",
        "assets_written",
    ):
        result[key] += int(lookup_result.get(key) or 0)


def _empty_result(now_ms: int) -> dict[str, Any]:
    return {
        "now_ms": int(now_ms),
        "lookups_selected": 0,
        "lookups_done": 0,
        "lookups_failed": 0,
        "lookups_terminalized": 0,
        "provider_errors": 0,
        "search_requests": 0,
        "search_hits": 0,
        "search_candidates_seen": 0,
        "search_candidates_rejected": 0,
        "assets_written": 0,
        "reprocessed_intents": 0,
        "reprocess": None,
        "anchor": None,
        "projection": deferred_token_radar_projection(),
        "affected_lookup_keys": [],
        "discovery_result_counts": {},
        "errors": [],
    }


def _complete_lookup_claims(
    *,
    db: Any,
    worker_name: str,
    claims: list[dict[str, Any]],
    resolved_lookup_keys: set[str],
    due_by_lookup_key: dict[str, int],
    now_ms: int,
    max_attempts: int,
    result: dict[str, Any],
) -> None:
    with db.worker_session(worker_name) as repos:
        _finish_lookup_claims(
            repos=repos,
            claims=claims,
            resolved_lookup_keys=resolved_lookup_keys,
            due_by_lookup_key=due_by_lookup_key,
            now_ms=now_ms,
            worker_name=worker_name,
            max_attempts=max_attempts,
            result=result,
        )


def _finish_lookup_claims(
    *,
    repos: Any,
    claims: list[dict[str, Any]],
    resolved_lookup_keys: set[str],
    due_by_lookup_key: dict[str, int],
    now_ms: int,
    worker_name: str,
    max_attempts: int,
    result: dict[str, Any],
) -> None:
    done = [claim for claim in claims if str(claim.get("lookup_key") or "") in resolved_lookup_keys]
    if done:
        repos.discovery.mark_lookup_done(done, now_ms=now_ms, commit=False)
    for claim in claims:
        lookup_key = str(claim.get("lookup_key") or "")
        if lookup_key in resolved_lookup_keys:
            continue
        if _claim_retry_budget_exhausted(claim, max_attempts=max_attempts):
            terminal = repos.discovery.terminalize_lookup_claims(
                [claim],
                worker_name=worker_name,
                final_status="not_found",
                final_reason="not_found_retry_budget_exhausted",
                now_ms=now_ms,
                commit=False,
            )
            result["lookups_terminalized"] += int(terminal.get("terminalized") or 0)
            continue
        repos.discovery.reschedule_lookup_claims(
            [claim],
            due_at_ms=due_by_lookup_key.get(lookup_key, now_ms + HOT_NOT_FOUND_RETRY_MS),
            now_ms=now_ms,
            commit=False,
        )
    repos.conn.commit()


def _claim_retry_budget_exhausted(claim: dict[str, Any], *, max_attempts: int) -> bool:
    return int(claim.get("attempt_count") or 0) >= max(1, int(max_attempts))


def _next_queue_due_at_ms(
    *,
    lookup: dict[str, Any],
    status: str,
    next_refresh_at_ms: int,
    now_ms: int,
) -> int:
    latest_seen_ms = int(lookup.get("latest_seen_ms") or 0)
    if status == "not_found" and latest_seen_ms >= int(now_ms) - HOT_LOOKBACK_MS:
        return int(now_ms) + HOT_NOT_FOUND_RETRY_MS
    return int(next_refresh_at_ms)


def _lookup_result(
    *,
    search_requests: int = 0,
    search_hits: int = 0,
) -> dict[str, Any]:
    return {
        "search_requests": int(search_requests),
        "search_hits": int(search_hits),
        "search_candidates_seen": 0,
        "search_candidates_rejected": 0,
        "assets_written": 0,
        "candidate_ids": [],
        "affected_lookup_keys": [],
    }


def _retained_symbol_candidates(candidates: list[Any], *, per_chain_limit: int) -> list[Any]:
    by_chain: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        chain_id = _chain_id(getattr(candidate, "chain_id", None))
        address = _normalize_address(getattr(candidate, "address", None))
        if not chain_id or not address:
            continue
        chain_bucket = by_chain.setdefault(chain_id, {})
        existing = chain_bucket.get(address)
        if existing is None or _candidate_rank_key(candidate) < _candidate_rank_key(existing):
            chain_bucket[address] = candidate
    retained: list[Any] = []
    for chain_id in sorted(by_chain):
        ranked = sorted(by_chain[chain_id].values(), key=_candidate_rank_key)
        retained.extend(ranked[: max(0, int(per_chain_limit))])
    return retained


def _candidate_rank_key(candidate: Any) -> tuple[float, int, str]:
    address = _normalize_address(getattr(candidate, "address", None))
    has_price_rank = 0 if getattr(candidate, "price_usd", None) is not None else 1
    return (-_candidate_quality_score(candidate), has_price_rank, address)


def _provider_ranks(candidates: list[Any]) -> dict[tuple[str | None, str], int]:
    ranks: dict[tuple[str | None, str], int] = {}
    for index, candidate in enumerate(candidates):
        key = _candidate_identity_key(candidate)
        if key[1] and key not in ranks:
            ranks[key] = index
    return ranks


def _candidate_identity_key(candidate: Any) -> tuple[str | None, str]:
    return (
        _chain_id(getattr(candidate, "chain_id", None)),
        _normalize_address(getattr(candidate, "address", None)),
    )


def _candidate_quality_score(candidate: Any) -> float:
    return (
        0.5 * _log10_number(getattr(candidate, "market_cap_usd", None))
        + 0.3 * _log10_number(getattr(candidate, "liquidity_usd", None))
        + 0.2 * _log10_number(getattr(candidate, "holders", None))
    )


def _log10_number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 0:
        return 0.0
    return math.log10(numeric + 1.0)


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


def _refresh_ms(*, lookup_key: str, status: str, error_count: int = 0) -> int:
    if status == "error":
        index = min(max(0, int(error_count)), len(ERROR_REFRESH_BACKOFF_MS) - 1)
        return ERROR_REFRESH_BACKOFF_MS[index]
    if lookup_key.startswith("address:"):
        return FOUND_ADDRESS_REFRESH_MS if status == "found" else NOT_FOUND_ADDRESS_REFRESH_MS
    return FOUND_SYMBOL_REFRESH_MS if status == "found" else NOT_FOUND_SYMBOL_REFRESH_MS


def _result_hash(candidate_ids: list[str]) -> str:
    payload = json.dumps(sorted(set(candidate_ids)), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
