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
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION, WINDOW_MS

SCORE_KEYS = ("score", "rank_score", "composite_rank_score")
RECENCY_SCORE_KEYS = ("computed_at_ms", "source_max_received_at_ms")
DEFAULT_BATCH_SIZE = 100
DEFAULT_WS_LIMIT = 50
DEFAULT_POLL_LIMIT = 200


class TokenCaptureTierWorker(WorkerBase):
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
        self.batch_size = max(1, int(batch_size or getattr(resolved_settings, "batch_size", DEFAULT_BATCH_SIZE)))
        self.ws_limit = max(0, int(ws_limit))
        self.poll_limit = max(0, int(poll_limit))
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
    rows = repos.registry.active_live_market_targets(
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        since_ms=int(now_ms) - WINDOW_MS["24h"],
        limit=resolved_batch_size,
    )
    candidates = _candidate_rows(rows)[:resolved_batch_size]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.target_type, candidate.target_id))

    for index, candidate in enumerate(candidates):
        tier, reason = _tier_for_index(index, ws_limit=max(0, int(ws_limit)), poll_limit=max(0, int(poll_limit)))
        repos.token_capture_tiers.upsert_tier(
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            tier=tier,
            reason=reason,
            score=candidate.score,
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
    target_id = str(row.get("target_id") or "").strip()
    if target_type in {"chain_token", "cex_symbol"} and target_id:
        return target_type, target_id

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
    recency_values = [
        _decimal(value)
        for key in RECENCY_SCORE_KEYS
        if (value := row.get(key)) is not None and str(value).strip() != ""
    ]
    if recency_values:
        return max(recency_values)
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _tier_for_index(index: int, *, ws_limit: int, poll_limit: int) -> tuple[int, str]:
    if index < ws_limit:
        return 1, "ws_subscribed"
    if index < ws_limit + poll_limit:
        return 2, "batch_poll"
    return 3, "inline_only"


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
