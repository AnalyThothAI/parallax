from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.narrative_intel.services.narrative_admission import NarrativeAdmissionService

NARRATIVE_WINDOW_MS_BY_KEY = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "24h": 86_400_000,
}
NARRATIVE_SCOPE_WATCHED_ONLY = {
    "all": False,
    "matched": True,
}


class NarrativeAdmissionWorker(WorkerBase):
    SINGLE_WRITER_KEY = 2026051901

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_waiter: Any | None = None,
    ) -> None:
        if settings is None:
            raise RuntimeError("narrative_admission_settings_required")
        if db is None:
            raise RuntimeError("narrative_admission_db_required")
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.windows = tuple(str(window).strip().lower() for window in settings.windows)
        self.scopes = tuple(str(scope).strip().lower() for scope in settings.scopes)
        self.admission_limit = _positive_worker_setting_int(
            settings,
            "admission_limit",
            error_code="narrative_admission_admission_limit_required",
        )
        self.source_limit = _positive_worker_setting_int(
            settings,
            "source_limit",
            error_code="narrative_admission_source_limit_required",
        )
        self.lease_ms = _positive_worker_setting_int(
            settings,
            "lease_ms",
            error_code="narrative_admission_lease_ms_required",
        )
        self.retry_ms = _positive_worker_setting_int(
            settings,
            "retry_ms",
            error_code="narrative_admission_retry_ms_required",
        )
        self.max_attempts = _positive_worker_setting_int(
            settings,
            "max_attempts",
            error_code="narrative_admission_max_attempts_required",
        )
        self.admission = NarrativeAdmissionService(
            hot_rank_limit=int(settings.hot_rank_limit),
            min_rank_score=int(settings.min_rank_score),
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
        stats = {
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "failed": 0,
            "admissions_upserted": 0,
            "admissions_staled": 0,
        }
        with self._repository_session() as repos, repos.transaction():
            claims = repos.narrative_admission_dirty_targets.claim_due(
                now_ms=now_ms,
                limit=self.admission_limit,
                lease_owner=self.name,
                lease_ms=self.lease_ms,
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
                            source_limit=self.source_limit,
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
                    retry_ms=self.retry_ms,
                    max_attempts=self.max_attempts,
                    worker_name=self.name,
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
    ) -> dict[str, int]:
        target_type = _required_claim_text(claim, "target_type")
        target_id = _required_claim_text(claim, "target_id")
        window = _required_claim_member(claim, "window", self.windows)
        scope = _required_claim_member(claim, "scope", self.scopes)
        projection_version = _required_claim_text(claim, "projection_version")
        schema_version = _required_claim_text(claim, "schema_version")
        stats = {
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "admissions_upserted": 0,
            "admissions_staled": 0,
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
                commit=False,
            )
            stats["admissions_staled"] += int(staled.get("staled_admissions") or 0)
            stats["rows_written"] += int(staled.get("staled_admissions") or 0)
            return stats

        for decision in decisions:
            payload = asdict(decision)
            projection_computed_at_ms = _required_decision_positive_int(
                decision.projection_computed_at_ms,
                error_code="narrative_admission_projection_computed_at_required",
            )
            source_end_ms = _required_decision_positive_int(
                decision.source_max_received_at_ms,
                error_code="narrative_admission_source_watermark_required",
            )
            source_start_ms = max(0, int(source_end_ms) - _window_ms(window))
            source_set = repos.narratives.source_set_for_admission(
                target_type=decision.target_type,
                target_id=decision.target_id,
                since_ms=source_start_ms,
                until_ms=int(source_end_ms),
                watched_only=_watched_only_for_scope(scope),
                limit=source_limit,
            )
            source_set.pop("source_rows", None)
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
        return stats

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
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


def _required_claim_member(claim: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = _required_claim_text(claim, key)
    if value not in allowed:
        allowed_values = ",".join(allowed)
        raise ValueError(f"narrative_admission_dirty_target_invalid_{key}:{value}:allowed={allowed_values}")
    return value


def _merge_stats(total: dict[str, int], delta: dict[str, int]) -> None:
    for key, value in delta.items():
        total[key] = int(total.get(key) or 0) + int(value or 0)


def _window_ms(window: str) -> int:
    try:
        return NARRATIVE_WINDOW_MS_BY_KEY[window]
    except KeyError as exc:
        raise ValueError(f"narrative_admission_dirty_target_invalid_window:{window}") from exc


def _watched_only_for_scope(scope: str) -> bool:
    try:
        return NARRATIVE_SCOPE_WATCHED_ONLY[scope]
    except KeyError as exc:
        raise ValueError(f"narrative_admission_dirty_target_invalid_scope:{scope}") from exc


def _positive_worker_setting_int(settings: Any, field_name: str, *, error_code: str) -> int:
    value = getattr(settings, field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value <= 0:
        raise ValueError(error_code)
    return int(value)


def _radar_row_for_admission(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    try:
        source_event_ids = normalized["source_event_ids_json"]
    except KeyError as exc:
        raise ValueError("narrative_admission_source_event_ids_required") from exc
    if not isinstance(source_event_ids, list):
        raise ValueError("narrative_admission_source_event_ids_invalid")
    if any(not isinstance(event_id, str) or not event_id.strip() for event_id in source_event_ids):
        raise ValueError("narrative_admission_source_event_ids_invalid")
    normalized["source_event_ids"] = [event_id.strip() for event_id in source_event_ids]
    return normalized


def _required_decision_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)
