from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS
from parallax.platform.config.settings import TokenCaptureTierWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult

SCORE_KEYS = ("score", "rank_score")
ADVISORY_LOCK_KEY = 2026051503


class TokenCaptureTierWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY
    worker_name = "token_capture_tier"

    def __init__(
        self,
        *,
        pool_bundle: Any,
        settings: TokenCaptureTierWorkerSettings,
        clock: Any | None = None,
        name: str = "token_capture_tier",
        telemetry: Any | None = None,
    ) -> None:
        if pool_bundle is None:
            raise RuntimeError("token_capture_tier_db_required")
        super().__init__(
            name=name,
            settings=settings,
            db=pool_bundle,
            telemetry=telemetry or object(),
        )
        self.batch_size = settings.batch_size
        self.ws_limit = settings.ws_limit
        self.poll_limit = settings.poll_limit
        self.clock = clock or _now_ms

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_now_ms = int(now_ms if now_ms is not None else self.clock())
        result = await asyncio.to_thread(self._project_once, observed_now_ms)
        return WorkerResult(
            processed=int(result.get("rows_written") or 0),
            failed=int(result.get("error") or 0),
            skipped=1 if int(result.get("claimed") or 0) == 0 else 0,
            notes={
                "claimed": int(result.get("claimed") or 0),
                "queue_depth": int(result.get("queue_depth") or 0),
                "source_rows_scanned": int(result.get("source_rows_scanned") or 0),
                "targets_loaded": int(result.get("targets_loaded") or 0),
                "rows_written": int(result.get("rows_written") or 0),
                "result": result,
            },
        )

    def _project_once(self, now_ms: int) -> dict[str, Any]:
        with self.db.worker_session(self.name) as repos:
            result: dict[str, Any] = {
                "claimed": 0,
                "queue_depth": 0,
                "source_rows_scanned": 0,
                "targets_loaded": 0,
                "rows_written": 0,
                "error": 0,
                "started_at_ms": int(now_ms),
                "finished_at_ms": int(now_ms),
            }
            lease_ms = self.settings.lease_ms
            retry_ms = self.settings.retry_ms
            max_attempts = self.settings.max_attempts
            with repos.transaction():
                claims = repos.token_capture_tier_dirty_targets.claim_due(
                    now_ms=now_ms,
                    limit=1,
                    lease_owner=self.name,
                    lease_ms=lease_ms,
                )
            result["claimed"] = len(claims)
            result["queue_depth"] = repos.token_capture_tier_dirty_targets.queue_depth(now_ms=now_ms)
            result["targets_loaded"] = len(claims)
            if not claims:
                result["reason"] = "no_due_token_capture_tier_rank_sets"
                return result
            try:
                with repos.transaction():
                    rows_written = project_once(
                        repos,
                        now_ms=now_ms,
                        batch_size=self.batch_size,
                        ws_limit=self.ws_limit,
                        poll_limit=self.poll_limit,
                    )
                    done = repos.token_capture_tier_dirty_targets.mark_done(claims, now_ms=now_ms)
                    if done != len(claims):
                        raise RuntimeError("token_capture_tier_dirty_target_stale_completion")
                result["rows_written"] = rows_written
            except Exception as exc:
                with repos.transaction():
                    repos.token_capture_tier_dirty_targets.mark_error(
                        claims,
                        error=_error_text(exc),
                        retry_ms=retry_ms,
                        max_attempts=max_attempts,
                        worker_name=self.name,
                        now_ms=now_ms,
                    )
                result["error"] = len(claims)
                result["last_error"] = _error_text(exc)
            return result


def project_once(
    repos: Any,
    *,
    now_ms: int,
    batch_size: int,
    ws_limit: int,
    poll_limit: int,
) -> int:
    repos.require_transaction(operation="token_capture_tier_projection")
    rows = repos.registry.ranked_live_market_targets(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        since_ms=int(now_ms) - WINDOW_MS["24h"],
        limit=batch_size,
    )
    candidates = _candidate_rows(rows)[:batch_size]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.target_type, candidate.target_id))

    # Tier 1 is OKX DEX WS only: only chain_token candidates are eligible. Even if a CEX
    # symbol outranks every chain_token on score, it must drop to Tier 2 batch_poll. This
    # is the projection boundary that prevents the runtime owner of OKX DEX WS from being
    # asked to subscribe to a CEX market id it cannot serve.
    tier1_candidates = [candidate for candidate in candidates if candidate.target_type == "chain_token"]
    tier1 = tier1_candidates[:ws_limit]
    tier1_keys = {(candidate.target_type, candidate.target_id) for candidate in tier1}

    tier2_pool = [
        candidate for candidate in candidates if (candidate.target_type, candidate.target_id) not in tier1_keys
    ]
    tier2 = tier2_pool[:poll_limit]
    tier2_keys = {(candidate.target_type, candidate.target_id) for candidate in tier2}

    tier3 = [
        candidate
        for candidate in candidates
        if (candidate.target_type, candidate.target_id) not in tier1_keys
        and (candidate.target_type, candidate.target_id) not in tier2_keys
    ]

    rows_written = 0
    for candidate in tier1:
        rows_written += _changed_count(
            repos.token_capture_tiers.upsert_tier(
                target_type=candidate.target_type,
                target_id=candidate.target_id,
                tier=1,
                reason="ws_subscribed",
                score=candidate.score,
                updated_at_ms=int(now_ms),
            )
        )
    for candidate in tier2:
        rows_written += _changed_count(
            repos.token_capture_tiers.upsert_tier(
                target_type=candidate.target_type,
                target_id=candidate.target_id,
                tier=2,
                reason="batch_poll",
                score=candidate.score,
                updated_at_ms=int(now_ms),
            )
        )
    for candidate in tier3:
        rows_written += _changed_count(
            repos.token_capture_tiers.upsert_tier(
                target_type=candidate.target_type,
                target_id=candidate.target_id,
                tier=3,
                reason="inline_only",
                score=candidate.score,
                updated_at_ms=int(now_ms),
            )
        )

    active_keys = [
        {"target_type": target_type, "target_id": target_id} for target_type, target_id in (*tier1_keys, *tier2_keys)
    ]
    rows_written += _changed_count(
        repos.token_capture_tiers.demote_hot_rows_outside_rank_set(
            active_keys=active_keys,
            updated_at_ms=int(now_ms),
        )
    )
    return rows_written


@dataclass(frozen=True, slots=True)
class _Candidate:
    target_type: str
    target_id: str
    score: Decimal


def _candidate_rows(rows: Any) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for row in rows:
        candidate = _candidate_from_row(row)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_from_row(row: Mapping[str, Any]) -> _Candidate | None:
    target = _market_target(row)
    if target is None:
        return None
    target_type, target_id = target
    return _Candidate(target_type=target_type, target_id=target_id, score=_score(row))


def _market_target(row: Mapping[str, Any]) -> tuple[str, str] | None:
    target_type = str(row.get("target_type") or "").strip()

    if target_type == "Asset":
        chain_id = str(row.get("chain_id") or "").strip()
        address = str(row.get("address") or "").strip()
        if chain_id and address:
            return "chain_token", f"{chain_id}:{address}"
        return None

    if target_type == "CexToken":
        provider = str(row.get("provider") or "").strip().lower()
        native_market_id = str(row.get("native_market_id") or "").strip().upper()
        if provider and native_market_id:
            return "cex_symbol", f"{provider}:{native_market_id}"
        return None

    return None


def _score(row: Mapping[str, Any]) -> Decimal:
    for key in SCORE_KEYS:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return _decimal(value)
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _changed_count(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value >= 0:
        return value
    raise TypeError("token_capture_tier_changed_count_invalid")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
