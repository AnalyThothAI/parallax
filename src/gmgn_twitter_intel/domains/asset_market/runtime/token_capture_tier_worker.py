from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS

SCORE_KEYS = ("score", "rank_score")
DEFAULT_BATCH_SIZE = 100
DEFAULT_WS_LIMIT = 50
DEFAULT_POLL_LIMIT = 200
ADVISORY_LOCK_KEY = 2026051503


class TokenCaptureTierWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY
    worker_name = "token_capture_tier"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        interval_seconds: float | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        ws_limit: int = DEFAULT_WS_LIMIT,
        poll_limit: int = DEFAULT_POLL_LIMIT,
        clock: Any | None = None,
        name: str = "token_capture_tier",
        settings: Any | None = None,
        db: Any | None = None,
        telemetry: Any | None = None,
    ) -> None:
        resolved_settings = _settings(settings, interval_seconds=interval_seconds, batch_size=batch_size)
        super().__init__(
            name=name,
            settings=resolved_settings,
            db=pool_bundle or db,
            telemetry=telemetry or object(),
        )
        self.batch_size = max(1, int(getattr(resolved_settings, "batch_size", batch_size)))
        self.ws_limit = max(0, int(getattr(resolved_settings, "ws_limit", ws_limit)))
        self.poll_limit = max(0, int(getattr(resolved_settings, "poll_limit", poll_limit)))
        self.clock = clock or _now_ms

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_now_ms = int(now_ms if now_ms is not None else self.clock())
        processed = await asyncio.to_thread(self._project_once, observed_now_ms)
        return WorkerResult(processed=processed, notes={"updated_tiers": processed})

    def _project_once(self, now_ms: int) -> int:
        with self.db.worker_session(self.name) as repos:
            return project_once(
                repos,
                now_ms=now_ms,
                batch_size=self.batch_size,
                ws_limit=self.ws_limit,
                poll_limit=self.poll_limit,
            )


def project_once(
    repos: Any,
    *,
    now_ms: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ws_limit: int = DEFAULT_WS_LIMIT,
    poll_limit: int = DEFAULT_POLL_LIMIT,
) -> int:
    resolved_batch_size = max(1, int(batch_size))
    resolved_ws_limit = max(0, int(ws_limit))
    resolved_poll_limit = max(0, int(poll_limit))
    rows = repos.registry.active_live_market_targets(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        since_ms=int(now_ms) - WINDOW_MS["24h"],
        limit=resolved_batch_size,
    )
    candidates = _candidate_rows(rows)[:resolved_batch_size]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.target_type, candidate.target_id))

    # Tier 1 is OKX DEX WS only: only chain_token candidates are eligible. Even if a CEX
    # symbol outranks every chain_token on score, it must drop to Tier 2 batch_poll. This
    # is the projection boundary that prevents the runtime owner of OKX DEX WS from being
    # asked to subscribe to a CEX market id it cannot serve.
    tier1_candidates = [candidate for candidate in candidates if candidate.target_type == "chain_token"]
    tier1 = tier1_candidates[:resolved_ws_limit]
    tier1_keys = {(candidate.target_type, candidate.target_id) for candidate in tier1}

    tier2_pool = [
        candidate for candidate in candidates if (candidate.target_type, candidate.target_id) not in tier1_keys
    ]
    tier2 = tier2_pool[:resolved_poll_limit]
    tier2_keys = {(candidate.target_type, candidate.target_id) for candidate in tier2}

    tier3 = [
        candidate
        for candidate in candidates
        if (candidate.target_type, candidate.target_id) not in tier1_keys
        and (candidate.target_type, candidate.target_id) not in tier2_keys
    ]

    for candidate in tier1:
        repos.token_capture_tiers.upsert_tier(
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            tier=1,
            reason="ws_subscribed",
            score=candidate.score,
            updated_at_ms=int(now_ms),
        )
    for candidate in tier2:
        repos.token_capture_tiers.upsert_tier(
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            tier=2,
            reason="batch_poll",
            score=candidate.score,
            updated_at_ms=int(now_ms),
        )
    for candidate in tier3:
        repos.token_capture_tiers.upsert_tier(
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            tier=3,
            reason="inline_only",
            score=candidate.score,
            updated_at_ms=int(now_ms),
        )

    active_keys = [
        {"target_type": target_type, "target_id": target_id} for target_type, target_id in (*tier1_keys, *tier2_keys)
    ]
    repos.token_capture_tiers.demote_absent_hot_rows(
        active_keys=active_keys,
        updated_at_ms=int(now_ms),
    )
    _commit_if_supported(repos)
    return len(candidates)


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


def _commit_if_supported(repos: Any) -> None:
    conn = getattr(repos, "conn", None)
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()
        return
    commit = getattr(repos, "commit", None)
    if callable(commit):
        commit()


def _settings(settings: Any | None, *, interval_seconds: float | None, batch_size: int) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else 5.0,
            timeout_seconds=120.0,
            batch_size=batch_size,
        )
    if interval_seconds is None:
        return settings
    try:
        settings.interval_seconds = interval_seconds
        return settings
    except Exception:
        values = dict(getattr(settings, "__dict__", {}))
        values["interval_seconds"] = interval_seconds
        return SimpleNamespace(**values)


def _now_ms() -> int:
    return int(time.time() * 1000)
