from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult

ADVISORY_LOCK_KEY = 2026052401
DEFAULT_RETRY_MS = 30_000


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
            },
        )

    def _run_once_sync(self, now_ms: int) -> dict[str, Any]:
        claims = self._claim_due(now_ms=now_ms)
        result: dict[str, Any] = {"claimed": len(claims), "changed": 0, "missing": 0, "failed": 0}
        changed_targets: list[tuple[str, str]] = []
        for claim in claims:
            try:
                changed, target = self._process_claim(claim, now_ms=now_ms)
            except Exception as exc:
                result["failed"] += 1
                self._mark_error(claim, error=_error_text(exc), now_ms=now_ms)
                continue
            if target is None:
                result["missing"] += 1
                continue
            if changed:
                result["changed"] += 1
                changed_targets.append(target)
        self._emit_token_radar_wakes(changed_targets)
        return result

    def _claim_due(self, *, now_ms: int) -> list[dict[str, Any]]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            return repos.market_tick_current_dirty_targets.claim_due(
                limit=max(1, int(getattr(self.settings, "batch_size", 100) or 100)),
                now_ms=int(now_ms),
                lease_ms=max(1, int(getattr(self.settings, "lease_ms", 120_000) or 120_000)),
                lease_owner=self.name,
                commit=True,
            )

    def _process_claim(self, claim: Mapping[str, Any], *, now_ms: int) -> tuple[bool, tuple[str, str] | None]:
        target_type = str(claim.get("target_type") or "")
        target_id = str(claim.get("target_id") or "")
        with self.db.worker_transaction(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            tick_row = repos.market_tick_current.latest_tick_for_target(
                target_type=target_type,
                target_id=target_id,
            )
            if tick_row is None:
                repos.market_tick_current_dirty_targets.mark_done([claim], now_ms=now_ms, commit=False)
                return False, None
            changed = repos.market_tick_current.upsert_current_from_tick(tick_row, now_ms=now_ms)
            if changed:
                repos.token_radar_dirty_targets.enqueue_market_targets(
                    [(target_type, target_id)],
                    reason="market_tick_current_changed",
                    now_ms=now_ms,
                    commit=False,
                )
            repos.market_tick_current_dirty_targets.mark_done([claim], now_ms=now_ms, commit=False)
        return bool(changed), (target_type, target_id)

    def _mark_error(self, claim: Mapping[str, Any], *, error: str, now_ms: int) -> None:
        with self.db.worker_transaction(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            repos.market_tick_current_dirty_targets.mark_error(
                [claim],
                error=error,
                retry_ms=max(1, int(getattr(self.settings, "retry_ms", DEFAULT_RETRY_MS) or DEFAULT_RETRY_MS)),
                now_ms=now_ms,
                commit=False,
            )

    def _emit_token_radar_wakes(self, targets: list[tuple[str, str]]) -> None:
        if self.wake_emitter is None:
            return
        notify_market_tick_current_updated = getattr(self.wake_emitter, "notify_market_tick_current_updated", None)
        if notify_market_tick_current_updated is not None:
            for target_type, target_id in targets:
                notify_market_tick_current_updated(target_type=target_type, target_id=target_id)
            return
        notify_token_radar_updated = getattr(self.wake_emitter, "notify_token_radar_updated", None)
        if notify_token_radar_updated is not None and targets:
            notify_token_radar_updated(window="5m", scope="all")


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


__all__ = ["MarketTickCurrentProjectionWorker"]
