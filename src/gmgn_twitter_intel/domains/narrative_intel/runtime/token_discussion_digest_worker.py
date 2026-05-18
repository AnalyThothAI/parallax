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
    DISCUSSION_DIGEST_PROMPT_VERSION,
    NARRATIVE_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.narrative_intel.providers import NarrativeIntelProvider
from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_repository import deterministic_run_id
from gmgn_twitter_intel.domains.narrative_intel.services.discussion_digest_service import DiscussionDigestService
from gmgn_twitter_intel.domains.narrative_intel.services.evidence_ref_validator import EvidenceRefValidator
from gmgn_twitter_intel.domains.narrative_intel.types.evidence_refs import EvidenceRef


class TokenDiscussionDigestWorker(WorkerBase):
    SINGLE_WRITER_KEY = 2026051802

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        provider: NarrativeIntelProvider,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.provider = provider
        self.service = DiscussionDigestService(
            min_source_mentions=int(getattr(settings, "min_source_mentions", 3) or 3),
            min_independent_authors=int(getattr(settings, "min_independent_authors", 2) or 2),
            min_semantic_coverage=float(getattr(settings, "min_semantic_coverage", 0.35) or 0.35),
            max_mentions_per_digest=int(getattr(settings, "max_mentions_per_digest", 120) or 120),
        )
        self.validator = EvidenceRefValidator()

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await self.run_once_async(now_ms=now_ms)

    async def run_once_async(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        limit = max(1, int(getattr(self.settings, "batch_size", 25) or 25))
        targets = await asyncio.to_thread(self._due_targets_sync, now_ms=resolved_now_ms, limit=limit)
        if not targets:
            return WorkerResult(skipped=1, notes={"reason": "no_due_digest_targets", "claimed": 0})

        counts = {"ready": 0, "insufficient": 0, "pending": 0, "failed": 0}
        refresh_reasons: dict[str, int] = {}
        for target in targets:
            context = await asyncio.to_thread(self._digest_context_sync, target=target, now_ms=resolved_now_ms)
            decision = self.service.refresh_decision(context)
            refresh_reasons[decision.reason] = refresh_reasons.get(decision.reason, 0) + 1
            if not decision.should_refresh:
                digest = self.service.build_insufficient_digest(
                    target_type=str(target["target_type"]),
                    target_id=str(target["target_id"]),
                    window=str(target["window"]),
                    scope=str(target["scope"]),
                    context=context,
                    reason=decision.reason,
                    now_ms=resolved_now_ms,
                )
                await asyncio.to_thread(
                    self._replace_digest_sync,
                    digest=digest.model_dump(mode="json"),
                    now_ms=resolved_now_ms,
                )
                counts["insufficient"] += 1
                continue

            started_at_ms = _now_ms()
            input_hash = _hash_json(context)
            run_id = deterministic_run_id(stage="discussion_digest", input_hash=input_hash, started_at_ms=started_at_ms)
            request = self.service.build_digest_request(
                run_id=run_id,
                target_type=str(target["target_type"]),
                target_id=str(target["target_id"]),
                window=str(target["window"]),
                scope=str(target["scope"]),
                context=context,
                schema_version=NARRATIVE_SCHEMA_VERSION,
                prompt_version=DISCUSSION_DIGEST_PROMPT_VERSION,
            )
            try:
                result = await self.provider.summarize_discussion(run_id=run_id, request=request)
            except Exception as exc:
                finished_at_ms = _now_ms()
                await asyncio.to_thread(
                    self._record_failed_run_sync,
                    run={
                        "run_id": run_id,
                        "stage": "discussion_digest",
                        "target_type": target["target_type"],
                        "target_id": target["target_id"],
                        "window": target["window"],
                        "scope": target["scope"],
                        "provider": self.provider.provider,
                        "model": self.provider.model,
                        "schema_version": NARRATIVE_SCHEMA_VERSION,
                        "prompt_version": DISCUSSION_DIGEST_PROMPT_VERSION,
                        "artifact_version_hash": self.provider.artifact_version_hash,
                        "input_hash": input_hash,
                        "output_hash": None,
                        "request_json": request.model_dump(mode="json"),
                        "response_json": None,
                        "usage_json": {},
                        "trace_metadata_json": {"error_type": type(exc).__name__},
                        "status": "failed",
                        "error": str(exc),
                        "started_at_ms": started_at_ms,
                        "finished_at_ms": finished_at_ms,
                        "latency_ms": finished_at_ms - started_at_ms,
                    },
                )
                counts["failed"] += 1
                continue
            allowed_refs = [EvidenceRef.model_validate(ref) for ref in request.allowed_refs]
            validation = self.validator.validate_digest_refs(result.digest, allowed_refs)
            if not validation.ok:
                counts["failed"] += 1
                continue
            finished_at_ms = _now_ms()
            run = {
                "run_id": run_id,
                "stage": "discussion_digest",
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "window": target["window"],
                "scope": target["scope"],
                "provider": self.provider.provider,
                "model": self.provider.model,
                "schema_version": result.schema_version,
                "prompt_version": result.prompt_version,
                "artifact_version_hash": self.provider.artifact_version_hash,
                "input_hash": input_hash,
                "output_hash": _hash_json(result.model_dump(mode="json")),
                "request_json": request.model_dump(mode="json"),
                "response_json": result.raw_response,
                "usage_json": (result.agent_run_audit or {}).get("usage") or {},
                "trace_metadata_json": result.agent_run_audit or {},
                "status": "done",
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "latency_ms": finished_at_ms - started_at_ms,
            }
            digest_payload = result.digest.model_dump(mode="json")
            digest_payload["model_run_id"] = run_id
            await asyncio.to_thread(
                self._record_ready_digest_sync,
                run=run,
                digest=digest_payload,
                now_ms=finished_at_ms,
            )
            counts["ready"] += 1
        return WorkerResult(
            processed=counts["ready"] + counts["insufficient"],
            failed=counts["failed"],
            notes={"claimed": len(targets), **counts, "refresh_reasons": refresh_reasons},
        )

    def _due_targets_sync(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            return list(repos.narratives.due_digest_targets(now_ms=now_ms, limit=limit))

    def _digest_context_sync(self, *, target: dict[str, Any], now_ms: int) -> dict[str, Any]:
        since_ms = now_ms - _window_ms(str(target.get("window") or "24h"))
        with self._repository_session() as repos:
            return dict(
                repos.narratives.digest_context(
                    target_type=str(target["target_type"]),
                    target_id=str(target["target_id"]),
                    window=str(target["window"]),
                    scope=str(target["scope"]),
                    since_ms=since_ms,
                    max_mentions=int(getattr(self.settings, "max_mentions_per_digest", 120) or 120),
                )
            )

    def _replace_digest_sync(self, *, digest: dict[str, Any], now_ms: int) -> None:
        with self._repository_session() as repos:
            repos.narratives.replace_current_digest(digest, now_ms=now_ms)

    def _record_ready_digest_sync(self, *, run: dict[str, Any], digest: dict[str, Any], now_ms: int) -> None:
        with self._repository_session() as repos:
            repos.narratives.record_narrative_model_run(run, commit=True)
            repos.narratives.replace_current_digest(digest, now_ms=now_ms)

    def _record_failed_run_sync(self, *, run: dict[str, Any]) -> None:
        with self._repository_session() as repos:
            repos.narratives.record_narrative_model_run(run, commit=True)

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _window_ms(window: str) -> int:
    return {"5m": 300_000, "1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}.get(window, 86_400_000)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
