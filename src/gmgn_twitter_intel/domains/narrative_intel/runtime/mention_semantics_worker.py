from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.narrative_intel._constants import (
    MENTION_SEMANTICS_PROMPT_VERSION,
    NARRATIVE_MODEL_VERSION_UNKNOWN,
    NARRATIVE_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.narrative_intel.providers import NarrativeIntelProvider
from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_repository import deterministic_run_id
from gmgn_twitter_intel.domains.narrative_intel.services.mention_semantics_service import MentionSemanticsService
from gmgn_twitter_intel.platform.cancellation import is_worker_hard_timeout_cancelled


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
        rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
        enqueue_stats: dict[str, int] = {}
        if not rows:
            enqueue_stats = await asyncio.to_thread(self._enqueue_missing_from_admissions_sync, now_ms=resolved_now_ms)
            rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
        if not rows:
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "no_due_mentions",
                    "claimed": 0,
                    **_prefixed(enqueue_stats, "enqueue_"),
                },
            )

        started_at_ms = _now_ms()
        input_hash = _hash_json(rows)
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
            result = await self.provider.label_mentions(run_id=run_id, request=request)
        except asyncio.CancelledError as exc:
            if not is_worker_hard_timeout_cancelled(exc):
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
            raise
        except Exception as exc:
            if _is_agent_no_start_backpressure(exc):
                reason = _agent_backpressure_reason(exc)
                return WorkerResult(
                    skipped=len(rows),
                    notes={
                        "claimed": len(rows),
                        **_prefixed(enqueue_stats, "enqueue_"),
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
            return WorkerResult(
                processed=semantic_unavailable,
                failed=failed,
                notes={
                    "claimed": len(rows),
                    **_prefixed(enqueue_stats, "enqueue_"),
                    "labeled": 0,
                    "semantic_unavailable": semantic_unavailable,
                    "failed": failed,
                    "provider_error": type(exc).__name__,
                    "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                },
            )
        result = self.service.validate_batch_result(rows, result)
        finished_at_ms = _now_ms()
        labels = _attach_semantic_identity(
            [label.model_dump(mode="json") for label in result.labels],
            rows=rows,
        )
        labeled_keys = {
            (str(label.get("event_id")), str(label.get("target_type")), str(label.get("target_id"))) for label in labels
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
        if changed and self.wake_bus is not None and hasattr(self.wake_bus, "notify_narrative_semantics_updated"):
            self.wake_bus.notify_narrative_semantics_updated(window="*", scope="*", target_count=changed)
        return WorkerResult(
            processed=changed,
            failed=int(complete.get("failed") or 0),
            notes={
                "claimed": len(rows),
                **_prefixed(enqueue_stats, "enqueue_"),
                "labeled": int(complete.get("labeled") or 0),
                "semantic_unavailable": int(complete.get("semantic_unavailable") or 0),
                "failed": int(complete.get("failed") or 0),
                "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
            },
        )

    def _enqueue_missing_from_admissions_sync(self, *, now_ms: int) -> dict[str, int]:
        admission_limit = max(1, int(getattr(self.settings, "admission_limit", 200) or 200))
        source_limit = max(1, int(getattr(self.settings, "source_limit", 2000) or 2000))
        cycle_enqueue_budget = max(
            1,
            int(getattr(self.settings, "max_semantic_rows_enqueued_per_cycle", 120) or 120),
        )
        per_admission_enqueue_budget = max(
            1,
            int(getattr(self.settings, "max_semantic_rows_enqueued_per_admission", 20) or 20),
        )
        max_pending_per_target = max(
            1,
            int(getattr(self.settings, "max_pending_semantics_per_target", 80) or 80),
        )
        interval_ms = max(1, int(float(getattr(self.settings, "interval_seconds", 60.0) or 60.0) * 1000))
        partial_retry_ms = max(
            1,
            int(float(getattr(self.settings, "partial_enqueue_retry_seconds", 5.0) or 5.0) * 1000),
        )
        stats = {
            "due_admissions": 0,
            "source_rows": 0,
            "semantic_inserted": 0,
            "semantic_existing": 0,
            "semantic_suppressed_budget": 0,
            "missing_after_enqueue": 0,
            "semantic_pending_before": 0,
            "semantic_pending_cap_hits": 0,
            "admissions_scanned": 0,
        }
        remaining_cycle_budget = cycle_enqueue_budget
        with self._repository_session() as repos:
            due_admissions = repos.narratives.due_admissions_for_semantics(
                now_ms=now_ms,
                limit=admission_limit,
                windows=_settings_windows(self.settings),
            )
            stats["due_admissions"] = len(due_admissions)
            for admission in due_admissions:
                source_rows = repos.narratives.source_rows_for_admission(admission, limit=source_limit)
                missing_source_rows = _missing_source_rows_for_semantics(
                    repos.narratives,
                    admission,
                    limit=source_limit,
                    schema_version=NARRATIVE_SCHEMA_VERSION,
                    fallback_source_rows=source_rows,
                )
                pending_count = repos.narratives.pending_mention_semantics_count(
                    target_type=str(admission["target_type"]),
                    target_id=str(admission["target_id"]),
                    schema_version=NARRATIVE_SCHEMA_VERSION,
                )
                stats["semantic_pending_before"] += pending_count
                target_budget = max(0, max_pending_per_target - pending_count)
                existing_count = max(0, len(source_rows) - len(missing_source_rows))
                stats["semantic_existing"] += existing_count
                allowed_count = min(
                    len(missing_source_rows),
                    target_budget,
                    remaining_cycle_budget,
                    per_admission_enqueue_budget,
                )
                missing_after_enqueue = max(0, len(missing_source_rows) - allowed_count)
                if allowed_count <= 0:
                    if missing_source_rows and target_budget <= 0:
                        stats["semantic_pending_cap_hits"] += 1
                    stats["source_rows"] += len(source_rows)
                    stats["semantic_suppressed_budget"] += missing_after_enqueue
                    stats["missing_after_enqueue"] += missing_after_enqueue
                    self._mark_admission_semantics_scanned(
                        repos.narratives,
                        admission_id=str(admission["admission_id"]),
                        next_due_at_ms=now_ms + (partial_retry_ms if missing_after_enqueue else interval_ms),
                        now_ms=now_ms,
                        stats=stats,
                    )
                    continue
                selected_mentions = missing_source_rows[:allowed_count]
                enqueued = repos.narratives.enqueue_missing_mention_semantics(
                    selected_mentions,
                    schema_version=NARRATIVE_SCHEMA_VERSION,
                    model_version=self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                    now_ms=now_ms,
                )
                stats["source_rows"] += len(source_rows)
                stats["semantic_inserted"] += int(enqueued.get("inserted") or 0)
                stats["semantic_existing"] += int(enqueued.get("existing") or 0)
                stats["semantic_suppressed_budget"] += missing_after_enqueue
                stats["missing_after_enqueue"] += missing_after_enqueue
                remaining_cycle_budget -= int(enqueued.get("inserted") or 0)
                self._mark_admission_semantics_scanned(
                    repos.narratives,
                    admission_id=str(admission["admission_id"]),
                    next_due_at_ms=now_ms + (partial_retry_ms if missing_after_enqueue else interval_ms),
                    now_ms=now_ms,
                    stats=stats,
                )
        return stats

    def _claim_due_rows_sync(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        max_per_target = max(1, int(getattr(self.settings, "max_semantics_claimed_per_target_per_cycle", 3) or 3))
        with self._repository_session() as repos:
            return list(
                repos.narratives.due_mentions_for_labeling(
                    now_ms=now_ms,
                    limit=limit,
                    max_per_target=max_per_target,
                )
            )

    def _mark_admission_semantics_scanned(
        self,
        narrative_repository: Any,
        *,
        admission_id: str,
        next_due_at_ms: int,
        now_ms: int,
        stats: dict[str, int],
    ) -> None:
        marked = narrative_repository.mark_admissions_semantics_scanned(
            [admission_id],
            next_due_at_ms=next_due_at_ms,
            now_ms=now_ms,
        )
        stats["admissions_scanned"] += int(marked.get("updated") or 0)

    def _record_completion_sync(
        self,
        *,
        run: dict[str, Any],
        labels: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, int]:
        with self._repository_session() as repos:
            repos.narratives.record_narrative_model_run(run, commit=False)
            return dict(
                repos.narratives.complete_mention_semantics_batch(
                    run_id=str(run["run_id"]),
                    labels=labels,
                    failures=failures,
                    now_ms=now_ms,
                )
            )

    def _provider_failure_next_retry_at_ms(self, *, now_ms: int) -> int:
        backoff_ms = max(
            1,
            int(float(getattr(self.settings, "provider_failure_backoff_seconds", 60.0) or 60.0) * 1000),
        )
        return int(now_ms) + backoff_ms

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _missing_source_rows_for_semantics(
    narrative_repository: Any,
    admission: dict[str, Any],
    *,
    limit: int,
    schema_version: str,
    fallback_source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    method = getattr(narrative_repository, "missing_source_rows_for_mention_semantics", None)
    if callable(method):
        return list(method(admission, limit=limit, schema_version=schema_version))
    return list(fallback_source_rows)


def _is_agent_no_start_backpressure(exc: Exception) -> bool:
    error_class = getattr(exc, "error_class", None)
    execution_started = bool(getattr(exc, "execution_started", True))
    value = getattr(error_class, "value", error_class)
    return not execution_started and value in {"capacity_denied", "circuit_open", "rate_limited"}


def _agent_backpressure_reason(exc: Exception) -> str:
    error_class = getattr(exc, "error_class", None)
    return str(getattr(error_class, "value", error_class) or "capacity_denied")


def _prefixed(values: dict[str, int], prefix: str) -> dict[str, int]:
    return {f"{prefix}{key}": value for key, value in values.items()}


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
        row = row_by_key.get(
            (str(item.get("event_id")), str(item.get("target_type")), str(item.get("target_id")))
        )
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
        enriched.append(next_item)
    return enriched


def _settings_windows(settings: Any) -> tuple[str, ...]:
    return tuple(getattr(settings, "windows", ("1h",)) or ("1h",))


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_request_audit(provider: Any, method_name: str, **kwargs: Any) -> dict[str, Any]:
    method = getattr(provider, method_name, None)
    if method is None:
        method = getattr(getattr(provider, "_client", None), method_name)
    return dict(method(**kwargs))
