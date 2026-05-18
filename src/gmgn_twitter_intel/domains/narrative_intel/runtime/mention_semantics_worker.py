from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
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
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_admission import NarrativeAdmissionService
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION


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
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.provider = provider
        self.wake_bus = wake_bus
        self.service = MentionSemanticsService()
        self.admission = NarrativeAdmissionService(
            hot_rank_limit=int(getattr(settings, "hot_rank_limit", 50) or 50),
            min_rank_score=int(getattr(settings, "min_rank_score", 30) or 30),
            carry_ttl_ms=int(getattr(settings, "carry_ttl_seconds", 3600) or 3600) * 1000,
        )

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await self.run_once_async(now_ms=now_ms)

    async def run_once_async(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        batch_size = max(1, int(getattr(self.settings, "batch_size", 50) or 50))
        admission_stats = await asyncio.to_thread(self._reconcile_admissions_and_enqueue_sync, now_ms=resolved_now_ms)
        rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
        if not rows:
            return WorkerResult(
                skipped=1,
                notes={"reason": "no_due_mentions", "claimed": 0, **_prefixed(admission_stats, "admission_")},
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
        result = await self.provider.label_mentions(run_id=run_id, request=request)
        self.service.validate_batch_result(rows, result)
        finished_at_ms = _now_ms()
        labels = [label.model_dump(mode="json") for label in result.labels]
        failures = list(result.failures)
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
                **_prefixed(admission_stats, "admission_"),
                "labeled": int(complete.get("labeled") or 0),
                "semantic_unavailable": int(complete.get("semantic_unavailable") or 0),
                "failed": int(complete.get("failed") or 0),
                "model": self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
            },
        )

    def _reconcile_admissions_and_enqueue_sync(self, *, now_ms: int) -> dict[str, int]:
        windows = tuple(getattr(self.settings, "windows", ("24h",)) or ("24h",))
        scopes = tuple(getattr(self.settings, "scopes", ("matched",)) or ("matched",))
        admission_limit = max(1, int(getattr(self.settings, "admission_limit", 200) or 200))
        source_limit = max(1, int(getattr(self.settings, "source_limit", 2000) or 2000))
        interval_ms = max(1, int(float(getattr(self.settings, "interval_seconds", 60.0) or 60.0) * 1000))
        stats = {
            "radar_rows": 0,
            "admissions_seen": 0,
            "admissions_upserted": 0,
            "due_admissions": 0,
            "source_mentions": 0,
            "semantic_inserted": 0,
            "semantic_existing": 0,
            "admissions_scanned": 0,
        }
        with self._repository_session() as repos:
            for window in windows:
                for scope in scopes:
                    radar_rows = [
                        _radar_row_for_admission(row)
                        for row in repos.narratives.admitted_radar_rows(
                            window=str(window),
                            scope=str(scope),
                            limit=admission_limit,
                            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                        )
                    ]
                    existing = repos.narratives.admissions_for_window_scope(
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        limit=admission_limit,
                    )
                    decisions = self.admission.reconcile_from_radar_rows(
                        radar_rows,
                        existing_admissions=existing,
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        now_ms=now_ms,
                    )
                    upserted = repos.narratives.upsert_admissions_from_radar_rows(
                        [asdict(decision) for decision in decisions],
                        window=str(window),
                        scope=str(scope),
                        schema_version=NARRATIVE_SCHEMA_VERSION,
                        now_ms=now_ms,
                        source_limit=admission_limit,
                    )
                    stats["radar_rows"] += len(radar_rows)
                    stats["admissions_seen"] += int(upserted.get("seen") or 0)
                    stats["admissions_upserted"] += int(upserted.get("upserted") or 0)

            due_admissions = repos.narratives.due_admissions_for_semantics(now_ms=now_ms, limit=admission_limit)
            stats["due_admissions"] = len(due_admissions)
            scanned_ids: list[str] = []
            for admission in due_admissions:
                source_mentions = repos.narratives.source_mentions_for_admission(
                    target_type=str(admission["target_type"]),
                    target_id=str(admission["target_id"]),
                    since_ms=max(0, now_ms - _window_ms(str(admission.get("window") or "24h"))),
                    watched_only=str(admission.get("scope") or "") == "matched",
                    limit=source_limit,
                )
                enqueued = repos.narratives.enqueue_missing_mention_semantics(
                    source_mentions,
                    schema_version=NARRATIVE_SCHEMA_VERSION,
                    model_version=self.provider.model or NARRATIVE_MODEL_VERSION_UNKNOWN,
                    now_ms=now_ms,
                )
                stats["source_mentions"] += len(source_mentions)
                stats["semantic_inserted"] += int(enqueued.get("inserted") or 0)
                stats["semantic_existing"] += int(enqueued.get("existing") or 0)
                scanned_ids.append(str(admission["admission_id"]))
            marked = repos.narratives.mark_admissions_semantics_scanned(
                scanned_ids,
                next_due_at_ms=now_ms + interval_ms,
                now_ms=now_ms,
            )
            stats["admissions_scanned"] = int(marked.get("updated") or 0)
        return stats

    def _claim_due_rows_sync(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            return list(repos.narratives.due_mentions_for_labeling(now_ms=now_ms, limit=limit))

    def _record_completion_sync(
        self,
        *,
        run: dict[str, Any],
        labels: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, int]:
        with self._repository_session() as repos:
            repos.narratives.record_narrative_model_run(run, commit=True)
            return dict(
                repos.narratives.complete_mention_semantics_batch(
                    run_id=str(run["run_id"]),
                    labels=labels,
                    failures=failures,
                    now_ms=now_ms,
                )
            )

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _window_ms(window: str) -> int:
    return {"5m": 300_000, "1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}.get(window, 86_400_000)


def _radar_row_for_admission(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source_event_ids = normalized.get("source_event_ids") or normalized.get("source_event_ids_json") or []
    normalized["source_event_ids"] = [str(event_id) for event_id in source_event_ids if str(event_id)]
    return normalized


def _prefixed(values: dict[str, int], prefix: str) -> dict[str, int]:
    return {f"{prefix}{key}": value for key, value in values.items()}


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
