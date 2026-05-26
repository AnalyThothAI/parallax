from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_admission import NarrativeAdmissionService


class NarrativeAdmissionWorker(WorkerBase):
    SINGLE_WRITER_KEY = 2026051901

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_bus: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.wake_bus = wake_bus
        self.admission = NarrativeAdmissionService(
            hot_rank_limit=int(getattr(settings, "hot_rank_limit", 50) or 50),
            min_rank_score=int(getattr(settings, "min_rank_score", 30) or 30),
        )

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync, now_ms=now_ms)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        stats = self._process_dirty_targets_sync(now_ms=resolved_now_ms)
        processed = int(stats.get("rows_written") or 0)
        failed = int(stats.get("failed") or 0)
        if failed > 0:
            return WorkerResult(processed=processed, failed=failed, notes=stats)
        if processed <= 0:
            reason = "no_due_narrative_admission_targets"
            if int(stats.get("claimed") or 0) > 0:
                reason = "no_narrative_admission_changes"
            return WorkerResult(skipped=1, notes={"reason": reason, **stats})
        return WorkerResult(processed=processed, notes=stats)

    def _process_dirty_targets_sync(self, *, now_ms: int) -> dict[str, int]:
        admission_limit = max(1, int(getattr(self.settings, "admission_limit", 200) or 200))
        source_limit = max(1, int(getattr(self.settings, "source_limit", 2000) or 2000))
        lease_ms = max(1, int(getattr(self.settings, "lease_seconds", 60) or 60)) * 1000
        retry_ms = max(1, int(getattr(self.settings, "error_retry_seconds", 60) or 60)) * 1000
        model_version = str(getattr(self.settings, "model_version", "unknown") or "unknown")
        stats = {
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "failed": 0,
            "admissions_upserted": 0,
            "admissions_staled": 0,
            "digests_staled": 0,
            "semantics_staled": 0,
            "semantic_rows_enqueued": 0,
            "semantic_rows_existing": 0,
            "digest_targets_enqueued": 0,
        }
        with self._repository_session() as repos, repos.transaction():
            claims = repos.narrative_admission_dirty_targets.claim_due(
                now_ms=now_ms,
                limit=admission_limit,
                lease_owner=self.name,
                lease_ms=lease_ms,
                commit=False,
            )
            stats["claimed"] = len(claims)
            stats["queue_depth"] = repos.narrative_admission_dirty_targets.queue_depth(now_ms=now_ms)
            if not claims:
                return stats

            done_claims: list[dict[str, Any]] = []
            failed_claims: list[tuple[dict[str, Any], str]] = []
            for claim in claims:
                try:
                    with repos.transaction():
                        claim_stats = self._process_claim_sync(
                            repos,
                            claim,
                            now_ms=now_ms,
                            source_limit=source_limit,
                            model_version=model_version,
                        )
                    _merge_stats(stats, claim_stats)
                    done_claims.append(dict(claim))
                except Exception as exc:
                    failed_claims.append((dict(claim), _error_text(exc)))
                    stats["failed"] += 1
            if done_claims:
                repos.narrative_admission_dirty_targets.mark_done(done_claims, now_ms=now_ms, commit=False)
            for failed_claim, error in failed_claims:
                repos.narrative_admission_dirty_targets.mark_error(
                    [failed_claim],
                    error=error,
                    now_ms=now_ms,
                    retry_ms=retry_ms,
                    commit=False,
                )
        return stats

    def _process_claim_sync(
        self,
        repos: Any,
        claim: dict[str, Any],
        *,
        now_ms: int,
        source_limit: int,
        model_version: str,
    ) -> dict[str, int]:
        target_type = _required_claim_text(claim, "target_type")
        target_id = _required_claim_text(claim, "target_id")
        window = _required_claim_text(claim, "window")
        scope = _required_claim_text(claim, "scope")
        projection_version = _required_claim_text(claim, "projection_version")
        schema_version = _required_claim_text(claim, "schema_version")
        stats = {
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "admissions_upserted": 0,
            "admissions_staled": 0,
            "digests_staled": 0,
            "semantics_staled": 0,
            "semantic_rows_enqueued": 0,
            "semantic_rows_existing": 0,
            "digest_targets_enqueued": 0,
        }
        context = repos.narratives.load_radar_admission_target(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            projection_version=projection_version,
            schema_version=schema_version,
        )
        stats["targets_loaded"] += 1
        radar_row = context.get("radar_row") or None
        existing_admission = context.get("existing_admission")
        decisions = self.admission.reconcile_from_radar_rows(
            [_radar_row_for_admission(radar_row)] if radar_row else [],
            existing_admissions=[existing_admission] if existing_admission else [],
            window=window,
            scope=scope,
            schema_version=schema_version,
            now_ms=now_ms,
        )
        if not decisions:
            staled = repos.narratives.stale_admission_target(
                target_type=target_type,
                target_id=target_id,
                window=window,
                scope=scope,
                schema_version=schema_version,
                now_ms=now_ms,
                commit=False,
            )
            stats["admissions_staled"] += int(staled.get("staled_admissions") or 0)
            stats["digests_staled"] += int(staled.get("staled_digests") or 0)
            stats["semantics_staled"] += int(staled.get("staled_semantics") or 0)
            stats["rows_written"] += (
                int(staled.get("staled_admissions") or 0)
                + int(staled.get("staled_digests") or 0)
                + int(staled.get("staled_semantics") or 0)
            )
            return stats

        for decision in decisions:
            payload = asdict(decision)
            projection_computed_at_ms = decision.projection_computed_at_ms or now_ms
            source_end_ms = projection_computed_at_ms
            source_start_ms = max(0, int(source_end_ms) - _window_ms(window))
            source_set = repos.narratives.source_set_for_admission(
                target_type=decision.target_type,
                target_id=decision.target_id,
                since_ms=source_start_ms,
                until_ms=int(source_end_ms),
                watched_only=scope == "matched",
                limit=source_limit,
            )
            source_rows = list(source_set.pop("source_rows", []))
            payload.update(source_set)
            payload["projection_computed_at_ms"] = projection_computed_at_ms
            payload["source_window_start_ms"] = source_start_ms
            payload["source_window_end_ms"] = source_end_ms
            payload["admission_generation"] = f"{window}:{scope}:{source_end_ms}"
            upserted = repos.narratives.upsert_admissions(
                [payload],
                now_ms=now_ms,
                limit=1,
                commit=False,
            )
            upserted_count = int(upserted.get("upserted") or 0)
            stats["admissions_upserted"] += upserted_count
            stats["rows_written"] += upserted_count
            stats["source_rows_scanned"] += int(source_set.get("source_event_count") or 0)
            enqueued = repos.narratives.enqueue_missing_mention_semantics(
                source_rows,
                schema_version=schema_version,
                model_version=model_version,
                now_ms=now_ms,
                commit=False,
            )
            semantic_inserted = int(enqueued.get("inserted") or 0)
            stats["semantic_rows_enqueued"] += semantic_inserted
            stats["semantic_rows_existing"] += int(enqueued.get("existing") or 0)
            stats["rows_written"] += semantic_inserted
            digest_targets = repos.discussion_digest_dirty_targets.enqueue_targets(
                [
                    {
                        "target_type": decision.target_type,
                        "target_id": decision.target_id,
                        "window": window,
                        "scope": scope,
                        "projection_version": projection_version,
                        "schema_version": schema_version,
                        "source_watermark_ms": (
                            decision.source_max_received_at_ms
                            or source_set.get("source_max_received_at_ms")
                            or source_end_ms
                        ),
                        "priority": decision.priority,
                    }
                ],
                reason="narrative_admission_changed",
                now_ms=now_ms,
                commit=False,
            )
            digest_target_count = int(digest_targets.get("targets") or 0)
            stats["digest_targets_enqueued"] += digest_target_count
            stats["rows_written"] += digest_target_count
        return stats

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _required_claim_text(claim: dict[str, Any], key: str) -> str:
    value = str(claim.get(key) or "").strip()
    if not value:
        raise ValueError(f"narrative_admission_dirty_target_missing_{key}")
    return value


def _merge_stats(total: dict[str, int], delta: dict[str, int]) -> None:
    for key, value in delta.items():
        total[key] = int(total.get(key) or 0) + int(value or 0)


def _window_ms(window: str) -> int:
    return {"5m": 300_000, "1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}.get(window, 86_400_000)


def _radar_row_for_admission(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source_event_ids = normalized.get("source_event_ids") or normalized.get("source_event_ids_json") or []
    normalized["source_event_ids"] = [str(event_id) for event_id in source_event_ids if str(event_id)]
    return normalized
