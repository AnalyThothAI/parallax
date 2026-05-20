from __future__ import annotations

import time
import uuid
from typing import Any

DAY_MS = 24 * 60 * 60 * 1000
DEFAULT_RETENTION_DAYS = 7
DEFAULT_SETTLEMENT_GRACE_DAYS = 2
DEFAULT_BATCH_SIZE = 10_000
DEFAULT_MAX_BATCHES = 1


class TokenRadarRetentionService:
    def __init__(self, *, token_radar: Any) -> None:
        self.token_radar = token_radar

    def prune(
        self,
        *,
        now_ms: int | None = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        settlement_grace_days: int = DEFAULT_SETTLEMENT_GRACE_DAYS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_batches: int = DEFAULT_MAX_BATCHES,
        dry_run: bool = True,
        execute: bool = False,
    ) -> dict[str, Any]:
        if dry_run and execute:
            raise ValueError("dry_run and execute are mutually exclusive")
        resolved_retention_days = int(retention_days)
        resolved_settlement_grace_days = int(settlement_grace_days)
        if resolved_retention_days < 2:
            raise ValueError("retention_days must be >= 2")
        minimum_retention_days = resolved_settlement_grace_days + 1
        if resolved_retention_days < minimum_retention_days:
            raise ValueError("retention_days must be >= settlement_grace_days + 1")

        resolved_batch_size = max(1, int(batch_size))
        resolved_max_batches = max(1, int(max_batches))
        resolved_now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        effective_days = max(resolved_retention_days, minimum_retention_days)
        cutoff_ms = resolved_now_ms - effective_days * DAY_MS
        mode = "execute" if execute else "dry_run"
        plan_limit = resolved_batch_size * resolved_max_batches
        planned_rows = self.token_radar.plan_prunable_rows(cutoff_ms=cutoff_ms, limit=plan_limit)
        protected = self.token_radar.protected_batch_counts()
        run_id = f"token-radar-retention:{uuid.uuid4().hex}"

        if not execute:
            self.token_radar.insert_retention_run(
                {
                    "run_id": run_id,
                    "mode": mode,
                    "retention_days": resolved_retention_days,
                    "cutoff_ms": cutoff_ms,
                    "batch_size": resolved_batch_size,
                    "max_batches": resolved_max_batches,
                    "rows_planned": len(planned_rows),
                    "rows_deleted": 0,
                    "status": "dry_run",
                    "error": None,
                    "started_at_ms": resolved_now_ms,
                    "finished_at_ms": resolved_now_ms,
                    "created_at_ms": resolved_now_ms,
                }
            )
            return {
                "run_id": run_id,
                "mode": mode,
                "retention_days": resolved_retention_days,
                "settlement_grace_days": resolved_settlement_grace_days,
                "cutoff_ms": cutoff_ms,
                "batch_size": resolved_batch_size,
                "max_batches": resolved_max_batches,
                "rows_planned": len(planned_rows),
                "rows_deleted": 0,
                **protected,
            }

        self.token_radar.insert_retention_run(
            {
                "run_id": run_id,
                "mode": mode,
                "retention_days": resolved_retention_days,
                "cutoff_ms": cutoff_ms,
                "batch_size": resolved_batch_size,
                "max_batches": resolved_max_batches,
                "rows_planned": len(planned_rows),
                "rows_deleted": 0,
                "status": "running",
                "error": None,
                "started_at_ms": resolved_now_ms,
                "finished_at_ms": None,
                "created_at_ms": resolved_now_ms,
            }
        )
        rows_deleted = 0
        try:
            for _ in range(resolved_max_batches):
                deleted = self.token_radar.delete_prunable_rows_batch(
                    cutoff_ms=cutoff_ms,
                    batch_size=resolved_batch_size,
                )
                rows_deleted += int(deleted)
                if int(deleted) <= 0:
                    break
            self.token_radar.finish_retention_run(run_id, status="done", rows_deleted=rows_deleted)
        except Exception as exc:
            self.token_radar.finish_retention_run(
                run_id,
                status="failed",
                rows_deleted=rows_deleted,
                error=str(exc),
            )
            raise
        return {
            "run_id": run_id,
            "mode": mode,
            "retention_days": resolved_retention_days,
            "settlement_grace_days": resolved_settlement_grace_days,
            "cutoff_ms": cutoff_ms,
            "batch_size": resolved_batch_size,
            "max_batches": resolved_max_batches,
            "rows_planned": len(planned_rows),
            "rows_deleted": rows_deleted,
            **protected,
        }


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_BATCHES",
    "DEFAULT_RETENTION_DAYS",
    "DEFAULT_SETTLEMENT_GRACE_DAYS",
    "TokenRadarRetentionService",
]
