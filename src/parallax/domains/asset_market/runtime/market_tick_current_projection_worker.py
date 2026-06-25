from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult

ADVISORY_LOCK_KEY = 2026052401


class MarketTickCurrentProjectionWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_emitter: Any | None = None,
        wake_waiter: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.wake_emitter = wake_emitter

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._run_once_sync, resolved_now_ms)
        processed = int(result["changed"]) + int(result["missing"])
        skipped = 1 if int(result["claimed"]) == 0 else 0
        return WorkerResult(
            processed=processed,
            failed=int(result["failed"]),
            skipped=skipped,
            notes={
                "claimed": int(result["claimed"]),
                "changed": int(result["changed"]),
                "missing": int(result["missing"]),
                "failed": int(result["failed"]),
                "token_radar_dirty_enqueued": int(result["token_radar_dirty_enqueued"]),
            },
        )

    def _run_once_sync(self, now_ms: int) -> dict[str, Any]:
        claims = self._claim_due(now_ms=now_ms)
        result: dict[str, Any] = {
            "claimed": len(claims),
            "changed": 0,
            "missing": 0,
            "failed": 0,
            "token_radar_dirty_enqueued": 0,
        }
        for claim in claims:
            try:
                claim_result = self._process_claim(claim, now_ms=now_ms)
            except Exception as exc:
                result["failed"] += 1
                self._mark_error(claim, error=_error_text(exc), now_ms=now_ms)
                continue
            if claim_result.missing:
                result["missing"] += 1
                continue
            if claim_result.changed:
                result["changed"] += 1
            result["token_radar_dirty_enqueued"] += claim_result.token_radar_dirty_enqueued
        self._emit_token_radar_wake(token_radar_dirty_enqueued=int(result["token_radar_dirty_enqueued"]))
        return result

    def _claim_due(self, *, now_ms: int) -> list[dict[str, Any]]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            return cast(
                list[dict[str, Any]],
                repos.market_tick_current_dirty_targets.claim_due(
                    limit=_required_positive_int(
                        self.settings.batch_size,
                        error_code="market_tick_current_batch_size_required",
                    ),
                    now_ms=int(now_ms),
                    lease_ms=_required_positive_int(
                        self.settings.lease_ms,
                        error_code="market_tick_current_lease_ms_required",
                    ),
                    lease_owner=self.name,
                    commit=True,
                ),
            )

    def _process_claim(self, claim: Mapping[str, Any], *, now_ms: int) -> _ClaimResult:
        target_type = str(claim.get("target_type") or "")
        target_id = str(claim.get("target_id") or "")
        token_radar_dirty_enqueued = 0
        with self.db.worker_transaction(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            tick_row = repos.market_tick_current.latest_tick_for_target(
                target_type=target_type,
                target_id=target_id,
            )
            if tick_row is None:
                repos.market_tick_current_dirty_targets.mark_done([claim], now_ms=now_ms, commit=False)
                return _ClaimResult(changed=False, missing=True, token_radar_dirty_enqueued=0)
            changed = repos.market_tick_current.upsert_current_from_tick(tick_row, now_ms=now_ms)
            if changed:
                token_radar_dirty_enqueued = int(
                    repos.token_radar_dirty_targets.enqueue_market_targets(
                        [(target_type, target_id)],
                        reason="market_tick_current_changed",
                        now_ms=now_ms,
                        commit=False,
                    )
                    or 0
                )
            repos.market_tick_current_dirty_targets.mark_done([claim], now_ms=now_ms, commit=False)
        return _ClaimResult(
            changed=bool(changed),
            missing=False,
            token_radar_dirty_enqueued=token_radar_dirty_enqueued,
        )

    def _mark_error(self, claim: Mapping[str, Any], *, error: str, now_ms: int) -> None:
        with self.db.worker_transaction(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            repos.market_tick_current_dirty_targets.mark_error(
                [claim],
                error=error,
                retry_ms=_required_positive_int(
                    self.settings.retry_ms,
                    error_code="market_tick_current_retry_ms_required",
                ),
                max_attempts=_required_positive_int(
                    self.settings.max_attempts,
                    error_code="market_tick_current_max_attempts_required",
                ),
                worker_name=self.name,
                now_ms=now_ms,
                commit=False,
            )

    def _emit_token_radar_wake(self, *, token_radar_dirty_enqueued: int) -> None:
        if token_radar_dirty_enqueued <= 0:
            return
        if self.wake_emitter is None:
            return
        self.wake_emitter.notify_market_tick_current_updated(target_type="batch", target_id="market_tick_current")


@dataclass(frozen=True)
class _ClaimResult:
    changed: bool
    missing: bool
    token_radar_dirty_enqueued: int


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


__all__ = ["MarketTickCurrentProjectionWorker"]
