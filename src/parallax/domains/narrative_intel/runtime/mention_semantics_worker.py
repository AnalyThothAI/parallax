from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.narrative_intel._constants import (
    MENTION_SEMANTICS_PROMPT_VERSION,
    NARRATIVE_MODEL_VERSION_UNKNOWN,
    NARRATIVE_SCHEMA_VERSION,
)
from parallax.domains.narrative_intel.providers import NarrativeIntelProvider
from parallax.domains.narrative_intel.repositories.narrative_repository import deterministic_run_id
from parallax.domains.narrative_intel.services.mention_semantics_service import MentionSemanticsService
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.agent_execution import AgentCapacityReservation
from parallax.platform.cancellation import is_worker_hard_timeout_cancelled

MENTION_SEMANTICS_LANE = "narrative.mention_semantics"


class MentionSemanticsWorker(WorkerBase):
    SINGLE_WRITER_KEY = 2026051801

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        provider: NarrativeIntelProvider,
        wake_bus: Any | None = None,
        wake_waiter: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.provider = provider
        self.wake_bus = wake_bus
        self.service = MentionSemanticsService()

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await self.run_once_async(now_ms=now_ms)

    async def run_once_async(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        configured_batch_size = max(1, int(getattr(self.settings, "batch_size", 50) or 50))
        provider_batch_size = max(1, int(getattr(self.settings, "provider_batch_size", configured_batch_size) or 1))
        batch_size = min(configured_batch_size, provider_batch_size)
        max_attempts = max(1, int(getattr(self.settings, "max_attempts", 3) or 3))
        queue_depth = await asyncio.to_thread(self._queue_depth_sync, now_ms=resolved_now_ms)
        if queue_depth <= 0:
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "no_due_mentions",
                    "claimed": 0,
                    "queue_depth": queue_depth,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                },
            )
        try:
            reservation = _try_reserve_provider_execution(self.provider, MENTION_SEMANTICS_LANE)
        except Exception as exc:
            return WorkerResult(
                skipped=1,
                notes={
                    "claimed": 0,
                    "queue_depth": queue_depth,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                    "agent_reservation_error": type(exc).__name__,
                },
            )
        if not reservation.acquired:
            reason = _reservation_backpressure_reason(reservation)
            return WorkerResult(
                skipped=1,
                notes={
                    "claimed": 0,
                    "queue_depth": queue_depth,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                    "agent_backpressure": reason,
                    f"agent_backpressure_{reason}": 1,
                },
            )
        try:
            rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
            if not rows:
                await _release_reservation(reservation)
                return WorkerResult(
                    skipped=1,
                    notes={
                        "reason": "no_due_mentions",
                        "claimed": 0,
                        "queue_depth": queue_depth,
                        "source_rows_scanned": 0,
                        "targets_loaded": 0,
                        "rows_written": 0,
                    },
                )

            started_at_ms = _now_ms()
            input_hash = _hash_json(_mention_semantics_input_rows(rows))
            run_id = deterministic_run_id(stage="mention_semantics", input_hash=input_hash, started_at_ms=started_at_ms)
            request = self.service.build_batch_request(
                rows,
                run_id=run_id,
                schema_version=NARRATIVE_SCHEMA_VERSION,
                prompt_version=MENTION_SEMANTICS_PROMPT_VERSION,
            )
            request_audit = _provider_request_audit(
                self.provider,
                "request_audit_for_label_mentions",
                run_id=run_id,
                request=request,
            )
            try:
                result = await _label_mentions(
                    self.provider,
                    run_id=run_id,
                    request=request,
                    reservation=reservation,
                )
            except asyncio.CancelledError as exc:
                if not is_worker_hard_timeout_cancelled(exc):
                    await _release_reservation(reservation)
                    raise
                finished_at_ms = _now_ms()
                failures = [
                    _provider_failure_for_row(
                        row,
                        error="worker_timeout_cancelled",
                        default_next_retry_at_ms=self._provider_failure_next_retry_at_ms(now_ms=finished_at_ms),
                        max_attempts=0,
                    )
                    for row in rows
                ]
                run_payload = {
                    "run_id": run_id,
                    "stage": "mention_semantics",
                    "provider": self.provider.provider,
                    "model": self.provider.model,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "prompt_version": MENTION_SEMANTICS_PROMPT_VERSION,
                    "artifact_version_hash": self.provider.artifact_version_hash,
                    "input_hash": input_hash,
                    "output_hash": None,
                    "evidence_event_ids_json": [row.get("event_id") for row in rows if row.get("event_id")],
                    "request_json": request.model_dump(mode="json"),
                    "response_json": None,
                    "usage_json": request_audit.get("usage") or {},
                    "trace_metadata_json": {
                        **request_audit,
                        "error_type": "CancelledError",
                    },
                    "status": "failed",
                    "error": "worker_timeout_cancelled",
                    "execution_started": True,
                    "started_at_ms": started_at_ms,
                    "finished_at_ms": finished_at_ms,
                    "latency_ms": finished_at_ms - started_at_ms,
                }
                await asyncio.to_thread(
                    self._record_completion_sync,
                    run=run_payload,
                    labels=[],
                    failures=failures,
                    now_ms=finished_at_ms,
                )
                await _release_reservation(reservation)
                raise
            except Exception as exc:
                if _is_agent_no_start_backpressure(exc):
                    reason = _agent_backpressure_reason(exc)
                    released = await asyncio.to_thread(
                        self._release_claimed_rows_sync,
                        rows=rows,
                        now_ms=resolved_now_ms,
                        retry_ms=self._provider_failure_retry_ms(),
                        error=reason,
                    )
                    await _release_reservation(reservation)
                    return WorkerResult(
                        skipped=len(rows),
                        notes={
                            "claimed": len(rows),
                            "queue_depth": await asyncio.to_thread(self._queue_depth_sync, now_ms=resolved_now_ms),
                            "source_rows_scanned": 0,
                            "targets_loaded": len(rows),
                            "rows_written": released,
                            "agent_backpressure": reason,
                            f"agent_backpressure_{reason}": 1,
                        },
                    )
                finished_at_ms = _now_ms()
                failures = [
                    _provider_failure_for_row(
                        row,
                        error=f"{type(exc).__name__}: {exc}",
                        default_next_retry_at_ms=finished_at_ms + 60_000,
                        max_attempts=max_attempts,
                    )
                    for row in rows
                ]
                run_payload = {
                    "run_id": run_id,
                    "stage": "mention_semantics",
                    "provider": self.provider.provider,
                    "model": self.provider.model,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "prompt_version": MENTION_SEMANTICS_PROMPT_VERSION,
                    "artifact_version_hash": self.provider.artifact_version_hash,
                    "input_hash": input_hash,
                    "output_hash": None,
                    "evidence_event_ids_json": [row.get("event_id") for row in rows if row.get("event_id")],
                    "request_json": request.model_dump(mode="json"),
                    "response_json": None,
                    "usage_json": request_audit.get("usage") or {},
                    "trace_metadata_json": {
                        **request_audit,
                        "error_type": type(exc).__name__,
                    },
                    "status": "failed",
                    "error": str(exc),
                    "execution_started": True,
                    "started_at_ms": started_at_ms,
                    "finished_at_ms": finished_at_ms,
                    "latency_ms": finished_at_ms - started_at_ms,
                }
                complete = await asyncio.to_thread(
                    self._record_completion_sync,
                    run=run_payload,
                    labels=[],
                    failures=failures,
                    now_ms=finished_at_ms,
                )
                semantic_unavailable = int(complete.get("semantic_unavailable") or 0)
                failed = int(complete.get("failed") or 0)
                digest_targets_enqueued = int(complete.get("digest_targets_enqueued") or 0)
                await _release_reservation(reservation)
                return WorkerResult(
                    processed=semantic_unavailable,
                    failed=failed,
                    notes={
                        "claimed": len(rows),
                        "queue_depth": await asyncio.to_thread(self._queue_depth_sync, now_ms=resolved_now_ms),
                        "source_rows_scanned": 0,
                        "targets_loaded": len(rows),
                        "rows_written": semantic_unavailable + failed + digest_targets_enqueued,
                        "labeled": 0,
                        "semantic_unavailable": semantic_unavailable,
                        "failed": failed,
                        "digest_targets_enqueued": digest_targets_enqueued,
                        "provider_error": type(exc).__name__,
                        "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                    },
                )
            try:
                result = self.service.validate_batch_result(rows, result)
            except Exception as exc:
                finished_at_ms = _now_ms()
                failures = [
                    _provider_failure_for_row(
                        row,
                        error=f"{type(exc).__name__}: {exc}",
                        default_next_retry_at_ms=finished_at_ms + 60_000,
                        max_attempts=max_attempts,
                    )
                    for row in rows
                ]
                run_payload = {
                    "run_id": run_id,
                    "stage": "mention_semantics",
                    "provider": self.provider.provider,
                    "model": self.provider.model,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "prompt_version": MENTION_SEMANTICS_PROMPT_VERSION,
                    "artifact_version_hash": self.provider.artifact_version_hash,
                    "input_hash": input_hash,
                    "output_hash": None,
                    "evidence_event_ids_json": [row.get("event_id") for row in rows if row.get("event_id")],
                    "request_json": request.model_dump(mode="json"),
                    "response_json": _jsonish(result),
                    "usage_json": request_audit.get("usage") or {},
                    "trace_metadata_json": {
                        **request_audit,
                        "error_type": type(exc).__name__,
                    },
                    "status": "failed",
                    "error": str(exc),
                    "execution_started": True,
                    "started_at_ms": started_at_ms,
                    "finished_at_ms": finished_at_ms,
                    "latency_ms": finished_at_ms - started_at_ms,
                }
                complete = await asyncio.to_thread(
                    self._record_completion_sync,
                    run=run_payload,
                    labels=[],
                    failures=failures,
                    now_ms=finished_at_ms,
                )
                semantic_unavailable = int(complete.get("semantic_unavailable") or 0)
                failed = int(complete.get("failed") or 0)
                digest_targets_enqueued = int(complete.get("digest_targets_enqueued") or 0)
                await _release_reservation(reservation)
                return WorkerResult(
                    processed=semantic_unavailable,
                    failed=failed,
                    notes={
                        "claimed": len(rows),
                        "queue_depth": await asyncio.to_thread(self._queue_depth_sync, now_ms=resolved_now_ms),
                        "source_rows_scanned": 0,
                        "targets_loaded": len(rows),
                        "rows_written": semantic_unavailable + failed + digest_targets_enqueued,
                        "labeled": 0,
                        "semantic_unavailable": semantic_unavailable,
                        "failed": failed,
                        "digest_targets_enqueued": digest_targets_enqueued,
                        "provider_error": type(exc).__name__,
                        "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                    },
                )
            finished_at_ms = _now_ms()
            labels = _attach_semantic_identity(
                [label.model_dump(mode="json") for label in result.labels],
                rows=rows,
            )
            labeled_keys = {
                (
                    str(label.get("event_id")),
                    str(label.get("target_type")),
                    str(label.get("target_id")),
                )
                for label in labels
            }
            failures = _attach_semantic_identity(
                self.service.normalize_failures(
                    rows,
                    list(result.failures),
                    labeled_keys=labeled_keys,
                    default_next_retry_at_ms=finished_at_ms + 60_000,
                ),
                rows=rows,
            )
            failures = _terminalize_failures_after_max_attempts(
                rows=rows,
                failures=failures,
                max_attempts=max_attempts,
            )
            audit = dict(result.agent_run_audit or {})
            run_payload = {
                "run_id": run_id,
                "stage": "mention_semantics",
                "provider": self.provider.provider,
                "model": self.provider.model,
                "schema_version": result.schema_version,
                "prompt_version": result.prompt_version,
                "artifact_version_hash": self.provider.artifact_version_hash,
                "input_hash": input_hash,
                "output_hash": _hash_json(result.model_dump(mode="json")),
                "evidence_event_ids_json": [row.get("event_id") for row in rows if row.get("event_id")],
                "request_json": request.model_dump(mode="json"),
                "response_json": result.raw_response,
                "usage_json": audit.get("usage") or {},
                "trace_metadata_json": audit,
                "status": "done",
                "execution_started": True,
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "latency_ms": finished_at_ms - started_at_ms,
            }
            complete = await asyncio.to_thread(
                self._record_completion_sync,
                run=run_payload,
                labels=labels,
                failures=failures,
                now_ms=finished_at_ms,
            )
            changed = int(complete.get("labeled") or 0) + int(complete.get("semantic_unavailable") or 0)
            digest_targets_enqueued = int(complete.get("digest_targets_enqueued") or 0)
            if changed and self.wake_bus is not None and hasattr(self.wake_bus, "notify_narrative_semantics_updated"):
                self.wake_bus.notify_narrative_semantics_updated(window="*", scope="*", target_count=changed)
            await _release_reservation(reservation)
            return WorkerResult(
                processed=changed,
                failed=int(complete.get("failed") or 0),
                notes={
                    "claimed": len(rows),
                    "queue_depth": await asyncio.to_thread(self._queue_depth_sync, now_ms=resolved_now_ms),
                    "source_rows_scanned": 0,
                    "targets_loaded": len(rows),
                    "rows_written": changed + int(complete.get("failed") or 0) + digest_targets_enqueued,
                    "labeled": int(complete.get("labeled") or 0),
                    "semantic_unavailable": int(complete.get("semantic_unavailable") or 0),
                    "failed": int(complete.get("failed") or 0),
                    "digest_targets_enqueued": digest_targets_enqueued,
                    "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                },
            )
        finally:
            await _release_reservation(reservation)

    def _claim_due_rows_sync(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        max_per_target = max(1, int(getattr(self.settings, "max_semantics_claimed_per_target_per_cycle", 3) or 3))
        lease_ms = max(1, int(getattr(self.settings, "lease_seconds", 60) or 60)) * 1000
        with self._repository_session() as repos:
            return list(
                repos.narratives.claim_due_mention_semantics(
                    now_ms=now_ms,
                    limit=limit,
                    lease_owner=self.name,
                    lease_ms=lease_ms,
                    max_per_target=max_per_target,
                )
            )

    def _queue_depth_sync(self, *, now_ms: int) -> int:
        with self._repository_session() as repos:
            return int(repos.narratives.mention_semantics_queue_depth(now_ms=now_ms))

    def _release_claimed_rows_sync(
        self,
        *,
        rows: list[dict[str, Any]],
        now_ms: int,
        retry_ms: int,
        error: str,
    ) -> int:
        with self._repository_session() as repos:
            return int(
                repos.narratives.release_mention_semantics_claims(
                    rows,
                    next_retry_at_ms=now_ms + retry_ms,
                    now_ms=now_ms,
                    error=error,
                )
            )

    def _record_completion_sync(
        self,
        *,
        run: dict[str, Any],
        labels: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, int]:
        with self._repository_session() as repos, repos.transaction():
            repos.narratives.record_narrative_model_run(run, commit=False)
            completion = dict(
                repos.narratives.complete_mention_semantics_batch(
                    run_id=str(run["run_id"]),
                    labels=labels,
                    failures=failures,
                    now_ms=now_ms,
                    commit=False,
                )
            )
            completed_rows = [*labels, *failures]
            updated = (
                int(completion.get("labeled") or 0)
                + int(completion.get("semantic_unavailable") or 0)
                + int(completion.get("failed") or 0)
            )
            if completed_rows and updated > 0:
                digest_targets = repos.narratives.digest_dirty_targets_for_mention_semantics_claims(
                    completed_rows,
                    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                    schema_version=NARRATIVE_SCHEMA_VERSION,
                )
                digest_enqueued = repos.discussion_digest_dirty_targets.enqueue_targets(
                    digest_targets,
                    reason="mention_semantics_completed",
                    now_ms=now_ms,
                    commit=False,
                )
                completion["digest_targets_enqueued"] = int(digest_enqueued.get("targets") or 0)
            else:
                completion["digest_targets_enqueued"] = 0
            return completion

    def _provider_failure_next_retry_at_ms(self, *, now_ms: int) -> int:
        return int(now_ms) + self._provider_failure_retry_ms()

    def _provider_failure_retry_ms(self) -> int:
        backoff_ms = max(
            1,
            int(float(getattr(self.settings, "provider_failure_backoff_seconds", 60.0) or 60.0) * 1000),
        )
        return backoff_ms

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _try_reserve_provider_execution(provider: Any, lane: str) -> AgentCapacityReservation:
    return cast(AgentCapacityReservation, provider.try_reserve_execution(lane))


async def _label_mentions(
    provider: Any,
    *,
    run_id: str,
    request: Any,
    reservation: AgentCapacityReservation,
) -> Any:
    return await provider.label_mentions(run_id=run_id, request=request, reservation=reservation)


async def _release_reservation(reservation: AgentCapacityReservation) -> None:
    await reservation.release()


def _reservation_backpressure_reason(reservation: AgentCapacityReservation) -> str:
    reason = getattr(reservation, "reason", None)
    return str(getattr(reason, "value", reason) or "capacity_denied")


def _jsonish(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dump(mode="json")
    if isinstance(value, dict | list | tuple | str | int | float | bool) or value is None:
        return value
    return {"repr": repr(value)}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_agent_no_start_backpressure(exc: Exception) -> bool:
    error_class = getattr(exc, "error_class", None)
    execution_started = bool(getattr(exc, "execution_started", True))
    value = getattr(error_class, "value", error_class)
    return not execution_started and value in {"capacity_denied", "circuit_open", "rate_limited", "quota_exhausted"}


def _agent_backpressure_reason(exc: Exception) -> str:
    error_class = getattr(exc, "error_class", None)
    return str(getattr(error_class, "value", error_class) or "capacity_denied")


def _provider_failure_for_row(
    row: dict[str, Any],
    *,
    error: str,
    default_next_retry_at_ms: int,
    max_attempts: int,
) -> dict[str, Any]:
    failure = {
        "semantic_id": row.get("semantic_id"),
        "event_id": row.get("event_id"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "schema_version": row.get("schema_version") or NARRATIVE_SCHEMA_VERSION,
        "text_fingerprint": row.get("text_fingerprint"),
        "lease_owner": row.get("lease_owner"),
        "attempt_count": row.get("attempt_count"),
        "error": error,
        "next_retry_at_ms": default_next_retry_at_ms,
    }
    if max_attempts > 0 and int(row.get("retry_count") or 0) + 1 >= max_attempts:
        failure["status"] = "semantic_unavailable"
        failure["next_retry_at_ms"] = 0
    return failure


def _terminalize_failures_after_max_attempts(
    *,
    rows: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    max_attempts: int,
) -> list[dict[str, Any]]:
    row_by_key = {
        (str(row.get("event_id")), str(row.get("target_type")), str(row.get("target_id"))): row for row in rows
    }
    terminalized = []
    for failure in failures:
        item = dict(failure)
        row = row_by_key.get((str(item.get("event_id")), str(item.get("target_type")), str(item.get("target_id"))))
        if row is not None and int(row.get("retry_count") or 0) + 1 >= max_attempts:
            item["status"] = "semantic_unavailable"
            item["next_retry_at_ms"] = 0
        terminalized.append(item)
    return terminalized


def _attach_semantic_identity(items: list[dict[str, Any]], *, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("event_id")), str(row.get("target_type")), str(row.get("target_id")))
        rows_by_key.setdefault(key, []).append(row)

    enriched: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        key = (str(next_item.get("event_id")), str(next_item.get("target_type")), str(next_item.get("target_id")))
        matching_rows = rows_by_key.get(key) or []
        if len(matching_rows) == 1:
            row = matching_rows[0]
            next_item.setdefault("semantic_id", row.get("semantic_id"))
            next_item.setdefault("schema_version", row.get("schema_version") or NARRATIVE_SCHEMA_VERSION)
            next_item.setdefault("text_fingerprint", row.get("text_fingerprint"))
            next_item.setdefault("lease_owner", row.get("lease_owner"))
            next_item.setdefault("attempt_count", row.get("attempt_count"))
        enriched.append(next_item)
    return enriched


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mention_semantics_input_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": str(row.get("event_id") or ""),
            "target_type": str(row.get("target_type") or ""),
            "target_id": str(row.get("target_id") or ""),
            "text_clean": str(row.get("text_clean") or row.get("text") or ""),
            "text_fingerprint": str(row.get("text_fingerprint") or ""),
        }
        for row in rows
    ]


def _provider_request_audit(provider: Any, method_name: str, **kwargs: Any) -> dict[str, Any]:
    method = getattr(provider, method_name)
    return dict(method(**kwargs))
