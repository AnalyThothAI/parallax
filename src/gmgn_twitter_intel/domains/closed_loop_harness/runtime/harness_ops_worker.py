from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, cast

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.closed_loop_harness.services.harness_ops import (
    attribute_harness_credits,
    materialize_market_ready_seeds,
    settle_harness_snapshots,
    update_harness_weights,
)

HORIZONS = ("6h", "24h")
PROCESSED_COUNT_SUFFIXES = ("_written", "_updated")
FAILED_COUNT_KEYS = {"errors"}
FAILED_COUNT_SUFFIXES = ("_errors",)


class HarnessOpsWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.batch_limit = max(1, int(getattr(settings, "batch_size", 200) or 200))
        self.horizons = tuple(getattr(settings, "horizons", HORIZONS) or HORIZONS)

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await asyncio.to_thread(self.process_once, now_ms=now_ms)
        return WorkerResult(processed=_processed_count(result), failed=_failed_count(result), notes=result)

    def process_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms if now_ms is not None else _now_ms()
        result: dict[str, Any] = {"materialize": {}, "settlement": {}, "credit": {}, "weights": {}}
        with self._repository_session() as repos:
            result["materialize"] = materialize_market_ready_seeds(
                harness=repos.harness,
                evidence=repos.evidence,
                assets=repos.assets,
                limit=self.batch_limit,
            )
        for horizon in self.horizons:
            with self._repository_session() as repos:
                result["settlement"][horizon] = settle_harness_snapshots(
                    harness=repos.harness,
                    assets=repos.assets,
                    horizon=horizon,
                    now_ms=now,
                    limit=self.batch_limit,
                )
        for horizon in self.horizons:
            with self._repository_session() as repos:
                result["credit"][horizon] = attribute_harness_credits(
                    harness=repos.harness,
                    horizon=horizon,
                    limit=self.batch_limit,
                )
        with self._repository_session() as repos:
            result["weights"] = update_harness_weights(harness=repos.harness, limit=self.batch_limit * 10)
        return result

    def _repository_session(self) -> AbstractContextManager[Any]:
        return cast(
            AbstractContextManager[Any],
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
            ),
        )


def _processed_count(result: dict[str, Any]) -> int:
    return _sum_stage_counts(result, keys=lambda key: key.endswith(PROCESSED_COUNT_SUFFIXES))


def _failed_count(result: dict[str, Any]) -> int:
    return _sum_stage_counts(result, keys=lambda key: key in FAILED_COUNT_KEYS or key.endswith(FAILED_COUNT_SUFFIXES))


def _sum_stage_counts(result: dict[str, Any], *, keys: Callable[[str], bool]) -> int:
    total = 0
    for stage_result in _stage_results(result):
        for key, value in stage_result.items():
            if keys(str(key)) and type(value) is int:
                total += max(0, value)
    return total


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stage_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    stage_results: list[dict[str, Any]] = []
    for value in result.values():
        if isinstance(value, dict) and all(isinstance(inner, dict) for inner in value.values()):
            stage_results.extend(value.values())
        elif isinstance(value, dict):
            stage_results.append(value)
    return stage_results
