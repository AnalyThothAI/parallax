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
from gmgn_twitter_intel.domains.narrative_intel.services.discussion_digest_service import (
    DEFAULT_MAX_MENTIONS_PER_DIGEST,
    DiscussionDigestService,
)
from gmgn_twitter_intel.domains.narrative_intel.services.evidence_ref_validator import EvidenceRefValidator
from gmgn_twitter_intel.domains.narrative_intel.services.narrative_epoch_policy import (
    DEFAULT_THRESHOLDS,
    EPOCH_POLICY_VERSION,
    NarrativeEpochPolicy,
    NarrativeEpochThreshold,
)
from gmgn_twitter_intel.domains.narrative_intel.types.evidence_refs import EvidenceRef
from gmgn_twitter_intel.platform.cancellation import is_worker_hard_timeout_cancelled


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
        wake_waiter: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.provider = provider
        self.service = DiscussionDigestService(
            min_source_mentions=int(getattr(settings, "min_source_mentions", 3) or 3),
            min_independent_authors=int(getattr(settings, "min_independent_authors", 2) or 2),
            min_semantic_coverage=float(getattr(settings, "min_semantic_coverage", 0.35) or 0.35),
            max_mentions_per_digest=int(
                getattr(settings, "max_mentions_per_digest", DEFAULT_MAX_MENTIONS_PER_DIGEST)
                or DEFAULT_MAX_MENTIONS_PER_DIGEST
            ),
        )
        self.validator = EvidenceRefValidator()
        self.epoch_policy = NarrativeEpochPolicy(
            thresholds=_thresholds_from_settings(settings),
            stance_mix_change_threshold=float(getattr(settings, "stance_mix_change_threshold", 0.20) or 0.20),
            attention_mix_change_threshold=float(getattr(settings, "attention_mix_change_threshold", 0.20) or 0.20),
            price_move_refresh_pct=float(getattr(settings, "price_move_refresh_pct", 12.0) or 12.0),
        )

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        return await self.run_once_async(now_ms=now_ms)

    async def run_once_async(self, *, now_ms: int | None = None) -> WorkerResult:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        limit = max(1, int(getattr(self.settings, "batch_size", 25) or 25))
        targets = await asyncio.to_thread(self._due_targets_sync, now_ms=resolved_now_ms, limit=limit)
        if not targets:
            return WorkerResult(skipped=1, notes={"reason": "no_due_digest_targets", "claimed": 0})

        counts = {"ready": 0, "insufficient": 0, "pending": 0, "semantic_unavailable": 0, "failed": 0}
        refresh_reasons: dict[str, int] = {}
        llm_calls = 0
        llm_failures = 0
        deferred = 0
        deferred_epoch_policy = 0
        for target in targets:
            context = await asyncio.to_thread(self._digest_context_sync, target=target)
            last_ready = await asyncio.to_thread(self._latest_ready_digest_sync, target=target)
            market_context = await asyncio.to_thread(
                self._market_context_sync,
                admission={**target, **context},
                last_ready_digest=last_ready,
            )
            epoch_decision = self.epoch_policy.evaluate(
                admission=_admission_for_policy(target=target, context=context),
                last_ready_digest=last_ready,
                semantic_coverage=context,
                market_context=market_context,
                now_ms=resolved_now_ms,
            )
            refresh_reasons[epoch_decision.reason] = refresh_reasons.get(epoch_decision.reason, 0) + 1
            sealed_context = _sealed_epoch_context(
                target=target,
                context=context,
                decision=epoch_decision,
                now_ms=resolved_now_ms,
            )
            if not epoch_decision.should_refresh:
                if epoch_decision.should_write_status_digest and last_ready is None:
                    status_decision = self.service.refresh_decision(context)
                    refresh_reasons[status_decision.reason] = refresh_reasons.get(status_decision.reason, 0) + 1
                    digest = self.service.build_status_digest(
                        target_type=str(target["target_type"]),
                        target_id=str(target["target_id"]),
                        window=str(target["window"]),
                        scope=str(target["scope"]),
                        context=sealed_context,
                        reason=status_decision.reason,
                        now_ms=resolved_now_ms,
                        status=status_decision.status_if_not_refresh,
                        model_version=f"deterministic:{status_decision.status_if_not_refresh}",
                    )
                    await asyncio.to_thread(
                        self._replace_digest_sync,
                        digest=digest.model_dump(mode="json"),
                        now_ms=resolved_now_ms,
                    )
                    counts[status_decision.status_if_not_refresh] += 1
                else:
                    deferred_epoch_policy += 1
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=resolved_now_ms,
                    next_due_at_ms=epoch_decision.next_due_at_ms,
                )
                continue

            if epoch_decision.reason == "no_ready_digest":
                status_decision = self.service.refresh_decision(context)
                if not status_decision.should_refresh:
                    refresh_reasons[status_decision.reason] = refresh_reasons.get(status_decision.reason, 0) + 1
                    digest = self.service.build_status_digest(
                        target_type=str(target["target_type"]),
                        target_id=str(target["target_id"]),
                        window=str(target["window"]),
                        scope=str(target["scope"]),
                        context=sealed_context,
                        reason=status_decision.reason,
                        now_ms=resolved_now_ms,
                        status=status_decision.status_if_not_refresh,
                        model_version=f"deterministic:{status_decision.status_if_not_refresh}",
                    )
                    await asyncio.to_thread(
                        self._replace_digest_sync,
                        digest=digest.model_dump(mode="json"),
                        now_ms=resolved_now_ms,
                    )
                    await asyncio.to_thread(
                        self._mark_digest_scanned_sync,
                        target=target,
                        now_ms=resolved_now_ms,
                        next_due_at_ms=epoch_decision.next_due_at_ms,
                    )
                    counts[status_decision.status_if_not_refresh] += 1
                    continue

            if llm_calls >= self._max_llm_calls_per_cycle():
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=resolved_now_ms,
                    next_due_at_ms=self._backpressure_next_due_at_ms(now_ms=resolved_now_ms),
                )
                counts["pending"] += 1
                deferred += 1
                refresh_reasons["llm_cycle_budget_exhausted"] = (
                    refresh_reasons.get("llm_cycle_budget_exhausted", 0) + 1
                )
                continue
            if llm_failures >= self._max_llm_failures_per_cycle():
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=resolved_now_ms,
                    next_due_at_ms=self._backpressure_next_due_at_ms(now_ms=resolved_now_ms),
                )
                counts["pending"] += 1
                deferred += 1
                refresh_reasons["llm_failure_budget_exhausted"] = (
                    refresh_reasons.get("llm_failure_budget_exhausted", 0) + 1
                )
                continue

            started_at_ms = _now_ms()
            input_hash = _hash_json(sealed_context)
            run_id = deterministic_run_id(stage="discussion_digest", input_hash=input_hash, started_at_ms=started_at_ms)
            request = self.service.build_digest_request(
                run_id=run_id,
                target_type=str(target["target_type"]),
                target_id=str(target["target_id"]),
                window=str(target["window"]),
                scope=str(target["scope"]),
                context=sealed_context,
                schema_version=NARRATIVE_SCHEMA_VERSION,
                prompt_version=DISCUSSION_DIGEST_PROMPT_VERSION,
            )
            request_audit = _provider_request_audit(
                self.provider,
                "request_audit_for_summarize_discussion",
                run_id=run_id,
                request=request,
            )
            try:
                llm_calls += 1
                result = await self.provider.summarize_discussion(run_id=run_id, request=request)
            except asyncio.CancelledError as exc:
                if not is_worker_hard_timeout_cancelled(exc):
                    raise
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
                    },
                )
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=finished_at_ms,
                    next_due_at_ms=self._provider_failure_next_due_at_ms(now_ms=finished_at_ms),
                )
                raise
            except Exception as exc:
                if _is_agent_no_start_backpressure(exc):
                    await asyncio.to_thread(
                        self._mark_digest_scanned_sync,
                        target=target,
                        now_ms=resolved_now_ms,
                        next_due_at_ms=self._backpressure_next_due_at_ms(now_ms=resolved_now_ms),
                    )
                    counts["pending"] += 1
                    refresh_reasons["agent_backpressure"] = refresh_reasons.get("agent_backpressure", 0) + 1
                    continue
                finished_at_ms = _now_ms()
                llm_failures += 1
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
                    },
                )
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=resolved_now_ms,
                    next_due_at_ms=self._provider_failure_next_due_at_ms(now_ms=resolved_now_ms),
                )
                counts["failed"] += 1
                continue
            finished_at_ms = _now_ms()
            try:
                ready_digest = self.service.publish_ready_digest(
                    result.digest,
                    context=sealed_context,
                    now_ms=finished_at_ms,
                )
            except Exception:
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=finished_at_ms,
                    next_due_at_ms=epoch_decision.next_due_at_ms,
                )
                counts["failed"] += 1
                continue
            allowed_refs = [EvidenceRef.model_validate(ref) for ref in request.allowed_refs]
            validation = self.validator.validate_digest_refs(ready_digest, allowed_refs)
            if not validation.ok:
                await asyncio.to_thread(
                    self._mark_digest_scanned_sync,
                    target=target,
                    now_ms=finished_at_ms,
                    next_due_at_ms=epoch_decision.next_due_at_ms,
                )
                counts["failed"] += 1
                continue
            result_payload = result.model_dump(mode="json")
            result_payload["digest"] = ready_digest.model_dump(mode="json")
            run = {
                "run_id": run_id,
                "stage": "discussion_digest",
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "window": target["window"],
                "scope": target["scope"],
                "provider": self.provider.provider,
                "model": self.provider.model,
                "schema_version": ready_digest.schema_version,
                "prompt_version": result.prompt_version,
                "artifact_version_hash": self.provider.artifact_version_hash,
                "input_hash": input_hash,
                "output_hash": _hash_json(result_payload),
                "request_json": request.model_dump(mode="json"),
                "response_json": result.raw_response,
                "usage_json": (result.agent_run_audit or {}).get("usage") or {},
                "trace_metadata_json": result.agent_run_audit or {},
                "status": "done",
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "latency_ms": finished_at_ms - started_at_ms,
            }
            digest_payload = ready_digest.model_dump(mode="json")
            digest_payload["model_run_id"] = run_id
            await asyncio.to_thread(
                self._record_ready_digest_sync,
                run=run,
                digest=digest_payload,
                now_ms=finished_at_ms,
            )
            await asyncio.to_thread(
                self._mark_digest_scanned_sync,
                target=target,
                now_ms=finished_at_ms,
                next_due_at_ms=epoch_decision.next_due_at_ms,
            )
            counts["ready"] += 1
        return WorkerResult(
            processed=(
                counts["ready"]
                + counts["insufficient"]
                + counts["pending"]
                + counts["semantic_unavailable"]
                + deferred_epoch_policy
            ),
            failed=counts["failed"],
            notes={
                "claimed": len(targets),
                **counts,
                "llm_calls": llm_calls,
                "llm_failures": llm_failures,
                "deferred_llm_budget": deferred,
                "deferred_epoch_policy": deferred_epoch_policy,
                "refresh_reasons": refresh_reasons,
            },
        )

    def _due_targets_sync(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            return list(repos.narratives.due_digest_targets(now_ms=now_ms, limit=limit))

    def _digest_context_sync(self, *, target: dict[str, Any]) -> dict[str, Any]:
        with self._repository_session() as repos:
            return dict(
                repos.narratives.digest_context(
                    target_type=str(target["target_type"]),
                    target_id=str(target["target_id"]),
                    window=str(target["window"]),
                    scope=str(target["scope"]),
                    max_mentions=int(
                        getattr(self.settings, "max_mentions_per_digest", DEFAULT_MAX_MENTIONS_PER_DIGEST)
                        or DEFAULT_MAX_MENTIONS_PER_DIGEST
                    ),
                )
            )

    def _latest_ready_digest_sync(self, *, target: dict[str, Any]) -> dict[str, Any] | None:
        with self._repository_session() as repos:
            method = getattr(repos.narratives, "latest_ready_digest_for_target", None)
            if method is None:
                return None
            digest = method(
                target_type=str(target["target_type"]),
                target_id=str(target["target_id"]),
                window=str(target["window"]),
                scope=str(target["scope"]),
                schema_version=NARRATIVE_SCHEMA_VERSION,
            )
            return dict(digest) if digest else None

    def _market_context_sync(
        self,
        *,
        admission: dict[str, Any],
        last_ready_digest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with self._repository_session() as repos:
            method = getattr(repos.narratives, "market_context_for_admission", None)
            if method is None:
                return {}
            return dict(method(admission, last_ready_digest=last_ready_digest) or {})

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

    def _mark_digest_scanned_sync(self, *, target: dict[str, Any], now_ms: int, next_due_at_ms: int) -> None:
        admission_id = str(target.get("admission_id") or "").strip()
        if not admission_id:
            return
        with self._repository_session() as repos:
            repos.narratives.mark_admissions_digest_scanned(
                [admission_id],
                next_due_at_ms=next_due_at_ms,
                now_ms=now_ms,
            )

    def _next_due_at_ms(self, *, target: dict[str, Any], now_ms: int) -> int:
        interval_ms = max(1, int(float(getattr(self.settings, "interval_seconds", 120.0) or 120.0) * 1000))
        return int(now_ms) + interval_ms

    def _backpressure_next_due_at_ms(self, *, now_ms: int) -> int:
        interval_ms = max(1, int(float(getattr(self.settings, "interval_seconds", 120.0) or 120.0) * 1000))
        return int(now_ms) + min(interval_ms, 30_000)

    def _provider_failure_next_due_at_ms(self, *, now_ms: int) -> int:
        backoff_ms = max(
            1,
            int(float(getattr(self.settings, "provider_failure_backoff_seconds", 600.0) or 600.0) * 1000),
        )
        return int(now_ms) + backoff_ms

    def _max_llm_calls_per_cycle(self) -> int:
        return max(0, int(getattr(self.settings, "max_llm_calls_per_cycle", 3) or 0))

    def _max_llm_failures_per_cycle(self) -> int:
        return max(0, int(getattr(self.settings, "max_llm_failures_per_cycle", 2) or 0))

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _thresholds_from_settings(settings: Any) -> dict[str, NarrativeEpochThreshold]:
    ttl_by_window = getattr(settings, "digest_ttl_by_window_seconds", None) or {}
    thresholds: dict[str, NarrativeEpochThreshold] = {}
    for window, default in DEFAULT_THRESHOLDS.items():
        ttl_seconds = _int_or_none(ttl_by_window.get(window)) if isinstance(ttl_by_window, dict) else None
        max_epoch_age_ms = (
            ttl_seconds * 1000
            if ttl_seconds is not None and ttl_seconds > 0
            else default.max_epoch_age_ms
        )
        thresholds[window] = NarrativeEpochThreshold(
            min_new_sources=default.min_new_sources,
            min_new_authors=default.min_new_authors,
            max_epoch_age_ms=max_epoch_age_ms,
        )
    return thresholds


def _admission_for_policy(*, target: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        **target,
        "source_event_ids": _source_event_ids(target=target, context=context),
        "source_event_ids_json": context.get("source_event_ids_json") or target.get("source_event_ids_json"),
        "source_event_count": context.get("source_event_count") or target.get("source_event_count") or 0,
        "source_fingerprint": context.get("source_fingerprint") or target.get("source_fingerprint"),
        "independent_author_count": (
            context.get("independent_author_count") or target.get("independent_author_count") or 0
        ),
        "source_window_start_ms": context.get("source_window_start_ms") or target.get("source_window_start_ms"),
        "source_window_end_ms": context.get("source_window_end_ms") or target.get("source_window_end_ms"),
    }


def _sealed_epoch_context(
    *,
    target: dict[str, Any],
    context: dict[str, Any],
    decision: Any,
    now_ms: int,
) -> dict[str, Any]:
    source_event_ids = _source_event_ids(target=target, context=context)
    source_fingerprint = context.get("source_fingerprint") or target.get("source_fingerprint")
    return {
        **context,
        "epoch_id": _deterministic_epoch_id(
            target_type=str(target.get("target_type") or ""),
            target_id=str(target.get("target_id") or ""),
            window=str(target.get("window") or ""),
            scope=str(target.get("scope") or ""),
            schema_version=NARRATIVE_SCHEMA_VERSION,
            source_fingerprint=str(source_fingerprint or ""),
            epoch_closed_at_ms=int(now_ms),
        ),
        "epoch_policy_version": decision.epoch_policy_version or EPOCH_POLICY_VERSION,
        "source_event_ids": source_event_ids,
        "source_window_start_ms": context.get("source_window_start_ms") or target.get("source_window_start_ms"),
        "source_window_end_ms": context.get("source_window_end_ms") or target.get("source_window_end_ms"),
        "epoch_closed_at_ms": int(now_ms),
        "display_current_until_ms": int(decision.next_due_at_ms),
        "refresh_reason": decision.refresh_reason or decision.reason,
    }


def _source_event_ids(*, target: dict[str, Any], context: dict[str, Any]) -> list[str]:
    value = (
        context.get("source_event_ids")
        or context.get("source_event_ids_json")
        or target.get("source_event_ids_json")
    )
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        value = decoded
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None]
    return []


def _deterministic_epoch_id(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
    source_fingerprint: str,
    epoch_closed_at_ms: int,
) -> str:
    parts = (target_type, target_id, window, scope, schema_version, source_fingerprint, str(epoch_closed_at_ms))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_agent_no_start_backpressure(exc: Exception) -> bool:
    error_class = getattr(exc, "error_class", None)
    execution_started = bool(getattr(exc, "execution_started", True))
    value = getattr(error_class, "value", error_class)
    return not execution_started and value in {"capacity_denied", "circuit_open", "rate_limited"}


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
