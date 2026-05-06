from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from loguru import logger

from ..market.okx_cex_client import OkxClientError
from ..market.okx_chains import OKX_CHAIN_INDEX_TO_CHAIN, OKX_CHAIN_TO_CHAIN_INDEX
from ..market.okx_models import OkxDexTokenCandidate

RATE_LIMIT_BACKOFF_MS = 5 * 60 * 1000
DEFAULT_FAILURE_BACKOFF_MS = 60 * 1000


class AssetResolutionWorker:
    def __init__(
        self,
        *,
        client,
        chain_indexes: tuple[str, ...],
        assets=None,
        repository_session=None,
        poll_interval: float = 5.0,
    ) -> None:
        if assets is None and repository_session is None:
            raise ValueError("assets or repository_session is required")
        self.client = client
        self.assets = assets
        self.repository_session = repository_session
        self.chain_indexes = tuple(str(chain).strip() for chain in chain_indexes if str(chain).strip())
        self.poll_interval = poll_interval
        self._stopped = False
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None

    async def run(self) -> None:
        while not self._stopped:
            try:
                self.last_result = self.process_one(now_ms=_now_ms())
                self.last_run_at_ms = _now_ms()
            except Exception as exc:  # pragma: no cover - watchdog path
                logger.exception(f"Asset resolution worker failed: {exc}")
            await asyncio.sleep(max(0.1, float(self.poll_interval)))

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close:
            close()

    def process_one(self, *, now_ms: int | None = None) -> dict[str, Any]:
        resolved_now_ms = int(now_ms or _now_ms())
        if self.assets is not None:
            return self._process_one_with_assets(self.assets, now_ms=resolved_now_ms)
        with self.repository_session() as repos:
            return self._process_one_with_assets(repos.assets, now_ms=resolved_now_ms)

    def _process_one_with_assets(self, assets, *, now_ms: int) -> dict[str, Any]:
        job = assets.claim_resolution_job(now_ms=now_ms)
        if not job:
            return {"processed": False}
        job_id = str(job["job_id"])
        try:
            result = self._process_job(assets, job=job, now_ms=now_ms)
        except Exception as exc:
            backoff_ms = RATE_LIMIT_BACKOFF_MS if _is_rate_limited_error(exc) else DEFAULT_FAILURE_BACKOFF_MS
            assets.finish_resolution_job(
                job_id=job_id,
                status="failed",
                error=str(exc),
                next_run_at_ms=now_ms + backoff_ms,
                commit=True,
            )
            return {"processed": True, "job_id": job_id, "status": "failed", "error": str(exc)}
        assets.finish_resolution_job(job_id=job_id, status="succeeded", error=None, commit=True)
        return {"processed": True, "job_id": job_id, "status": "succeeded", **result}

    def _process_job(self, assets, *, job: dict[str, Any], now_ms: int) -> dict[str, Any]:
        job_type = str(job.get("job_type") or "")
        if job_type == "symbol_resolution":
            return self._process_symbol_job(assets, job=job, now_ms=now_ms)
        if job_type == "ca_resolution":
            return self._process_ca_job(assets, job=job, now_ms=now_ms)
        return {"candidate_count": 0, "ignored": "unknown_job_type"}

    def _process_symbol_job(self, assets, *, job: dict[str, Any], now_ms: int) -> dict[str, Any]:
        symbol = _normalize_symbol(job.get("normalized_symbol"))
        if not symbol:
            return {"candidate_count": 0, "ignored": "missing_symbol"}
        candidates = self.client.search_tokens(query=symbol, chain_indexes=self.chain_indexes)
        rows = self._write_candidates(assets, symbol=symbol, candidates=candidates, now_ms=now_ms)
        selected = _single_resolved_candidate(symbol=symbol, rows=rows)
        if selected is not None:
            assets.reassign_symbol_attributions(
                symbol=symbol,
                asset_id=str(selected["asset_id"]),
                venue_id=str(selected["venue_id"]),
                decision_time_ms=now_ms,
                commit=False,
            )
        return {"candidate_count": len(candidates)}

    def _process_ca_job(self, assets, *, job: dict[str, Any], now_ms: int) -> dict[str, Any]:
        address = str(job.get("address_hint") or "").strip()
        if not address:
            return {"candidate_count": 0, "ignored": "missing_address"}
        candidates = self.client.search_tokens(
            query=address,
            chain_indexes=_chain_indexes_for_job(job, self.chain_indexes),
        )
        rows = self._write_candidates(assets, symbol=None, candidates=candidates, now_ms=now_ms)
        selected = _single_resolved_ca_candidate(rows)
        if selected is not None:
            assets.reassign_ca_attributions(
                address=address,
                chain=job.get("chain_hint"),
                asset_id=str(selected["asset_id"]),
                venue_id=str(selected["venue_id"]),
                decision_time_ms=now_ms,
                commit=False,
            )
        return {"candidate_count": len(candidates)}

    def _write_candidates(
        self,
        assets,
        *,
        symbol: str | None,
        candidates: list[OkxDexTokenCandidate],
        now_ms: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        mention_rows = assets.mentions_needing_symbol_resolution(symbol, limit=1000) if symbol else []
        for candidate in candidates:
            chain = _candidate_chain(candidate)
            result = assets.upsert_dex_asset(
                chain=chain,
                address=candidate.address,
                symbol=candidate.symbol,
                observed_at_ms=now_ms,
                provider="okx_dex",
                source_payload_hash=_payload_hash(candidate.raw),
                commit=False,
            )
            asset_id = str(result.asset["asset_id"])
            venue_id = str(result.venue["venue_id"]) if result.venue else None
            row = {"asset_id": asset_id, "venue_id": venue_id, "symbol": candidate.symbol}
            rows.append(row)
            self._write_market_snapshot(
                assets,
                candidate=candidate,
                asset_id=asset_id,
                venue_id=venue_id,
                now_ms=now_ms,
            )
            for mention in mention_rows:
                assets.insert_resolution_candidate(
                    mention_id=str(mention["mention_id"]),
                    provider="okx_dex",
                    candidate_kind="dex_token_search",
                    score=_candidate_score(candidate),
                    decision="candidate",
                    asset_id=asset_id,
                    venue_id=venue_id,
                    reasons=["okx_dex_token_search"],
                    risks=[],
                    raw_observation_id=None,
                    created_at_ms=now_ms,
                    commit=False,
                )
        return rows

    @staticmethod
    def _write_market_snapshot(
        assets,
        *,
        candidate: OkxDexTokenCandidate,
        asset_id: str,
        venue_id: str | None,
        now_ms: int,
    ) -> None:
        if not venue_id:
            return
        if not _candidate_has_market_data(candidate):
            return
        assets.insert_market_snapshot(
            asset_id=asset_id,
            venue_id=venue_id,
            provider="okx_dex",
            observed_at_ms=now_ms,
            price_usd=candidate.price_usd,
            market_cap_usd=candidate.market_cap_usd,
            liquidity_usd=candidate.liquidity_usd,
            holders=candidate.holders,
            source_payload_hash=_payload_hash(candidate.raw),
            commit=False,
        )


def _single_resolved_candidate(*, symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    matching = [row for row in rows if _normalize_symbol(row.get("symbol")) == symbol]
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in matching:
        asset_id = str(row.get("asset_id") or "")
        venue_id = str(row.get("venue_id") or "")
        if asset_id and venue_id:
            unique[(asset_id, venue_id)] = row
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def _single_resolved_ca_candidate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        asset_id = str(row.get("asset_id") or "")
        venue_id = str(row.get("venue_id") or "")
        if asset_id and venue_id:
            unique[(asset_id, venue_id)] = row
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def _candidate_chain(candidate: OkxDexTokenCandidate) -> str:
    if candidate.chain:
        return candidate.chain
    return OKX_CHAIN_INDEX_TO_CHAIN.get(candidate.chain_index, candidate.chain_index)


def _candidate_score(candidate: OkxDexTokenCandidate) -> float:
    score = 0.65
    if candidate.community_recognized:
        score += 0.2
    if candidate.liquidity_usd and candidate.liquidity_usd > 0:
        score += 0.1
    if candidate.holders and candidate.holders > 0:
        score += 0.05
    return min(score, 1.0)


def _candidate_has_market_data(candidate: OkxDexTokenCandidate) -> bool:
    return any(
        value is not None
        for value in (
            candidate.price_usd,
            candidate.market_cap_usd,
            candidate.liquidity_usd,
            candidate.holders,
        )
    )


def _chain_indexes_for_job(job: dict[str, Any], fallback: tuple[str, ...]) -> tuple[str, ...]:
    chain_hint = str(job.get("chain_hint") or "").strip().lower()
    chain_index = OKX_CHAIN_TO_CHAIN_INDEX.get(chain_hint)
    if chain_index:
        return (chain_index,)
    return fallback


def _is_rate_limited_error(exc: Exception) -> bool:
    if isinstance(exc, OkxClientError) and "429" in str(exc):
        return True
    return "429" in str(exc)


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
