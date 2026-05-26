from __future__ import annotations

import hashlib
import json
from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.platform.db.json_safety import postgres_safe_json

WORK_CHOICES = (
    "pulse_trigger",
    "narrative_admission",
    "discussion_digest",
    "profile_current",
    "image_source",
    "asset_profile_refresh",
    "capture_tier",
    "live_market_targets",
)
PULSE_TRIGGER_WINDOWS = ("1h", "4h")
PULSE_TRIGGER_SCOPES = ("all", "matched")
NARRATIVE_ADMISSION_WINDOWS = ("1h",)
NARRATIVE_ADMISSION_SCOPES = ("all",)
DISCUSSION_DIGEST_WINDOWS = ("1h",)
DISCUSSION_DIGEST_SCOPES = ("all", "matched")
PULSE_TRIGGER_REPAIR_REASON = "ops_runtime_worker_repair"
NARRATIVE_ADMISSION_REPAIR_REASON = "ops_runtime_worker_repair"
DISCUSSION_DIGEST_REPAIR_REASON = "ops_runtime_worker_repair"
PROFILE_CURRENT_REPAIR_REASON = "ops_runtime_worker_repair"
IMAGE_SOURCE_REPAIR_REASON = "ops_runtime_worker_repair"
ASSET_PROFILE_REFRESH_REPAIR_REASON = "ops_runtime_worker_repair"
CAPTURE_TIER_REPAIR_REASON = "ops_runtime_worker_repair"
PULSE_TRIGGER_MAX_SINCE_HOURS = 4.0
NARRATIVE_ADMISSION_MAX_SINCE_HOURS = 4.0
DISCUSSION_DIGEST_MAX_SINCE_HOURS = 4.0
DETERMINISTIC_REPAIR_MAX_SINCE_HOURS = 24.0
PULSE_TRIGGER_DEFAULT_DRY_RUN_LIMIT = 500
PULSE_TRIGGER_MAX_LIMIT = 500
PULSE_TRIGGER_TARGET_SAMPLE_LIMIT = 20
PULSE_TRIGGER_MAX_QUEUE_DEPTH = 10_000
PULSE_TRIGGER_MAX_DUE_QUEUE_DEPTH = 5_000
PULSE_TRIGGER_MAX_DOWNSTREAM_JOB_DEPTH = 100
PULSE_TRIGGER_MAX_DOWNSTREAM_WINDOW_SCOPE_JOB_DEPTH = 25


def enqueue_runtime_worker_dirty_targets(
    repos: Any,
    *,
    work: str,
    window: str,
    scope: str,
    since_hours: float | None,
    target_id: str | None,
    target_type: str | None = None,
    provider: str | None = None,
    source_url: str | None = None,
    limit: int | None = None,
    execute: bool = False,
    now_ms: int = 0,
) -> dict[str, Any]:
    normalized_work = str(work or "").strip()
    if normalized_work not in WORK_CHOICES:
        raise ValueError(f"unsupported runtime worker dirty target repair work: {normalized_work}")
    if normalized_work == "narrative_admission":
        return _enqueue_narrative_admission_dirty_targets(
            repos,
            window=window,
            scope=scope,
            since_hours=since_hours,
            target_id=target_id,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    if normalized_work == "discussion_digest":
        return _enqueue_discussion_digest_dirty_targets(
            repos,
            window=window,
            scope=scope,
            since_hours=since_hours,
            target_id=target_id,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    if normalized_work == "profile_current":
        return _enqueue_profile_current_dirty_targets(
            repos,
            since_hours=since_hours,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    if normalized_work == "image_source":
        return _enqueue_image_source_dirty_targets(
            repos,
            since_hours=since_hours,
            target_type=target_type,
            target_id=target_id,
            source_url=source_url,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    if normalized_work == "asset_profile_refresh":
        return _enqueue_asset_profile_refresh_targets(
            repos,
            since_hours=since_hours,
            provider=provider,
            target_id=target_id,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    if normalized_work in {"capture_tier", "live_market_targets"}:
        return _enqueue_capture_tier_dirty_targets(
            repos,
            work=normalized_work,
            limit=limit,
            execute=execute,
            now_ms=now_ms,
        )
    return _enqueue_pulse_trigger_dirty_targets(
        repos,
        window=window,
        scope=scope,
        since_hours=since_hours,
        target_id=target_id,
        limit=limit,
        execute=execute,
        now_ms=now_ms,
    )


def _enqueue_pulse_trigger_dirty_targets(
    repos: Any,
    *,
    window: str,
    scope: str,
    since_hours: float | None,
    target_id: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_window = str(window or "").strip()
    if normalized_window not in PULSE_TRIGGER_WINDOWS:
        raise ValueError(f"unsupported pulse_trigger repair window: {normalized_window}")
    normalized_scope = str(scope or "").strip()
    if normalized_scope not in PULSE_TRIGGER_SCOPES:
        raise ValueError(f"unsupported pulse_trigger repair scope: {normalized_scope}")

    normalized_target_id = str(target_id or "").strip() or None
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="pulse_trigger",
        max_since_hours=PULSE_TRIGGER_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours or --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="pulse_trigger")
    since_ms = (
        int(now_ms) - int(normalized_since_hours * 60 * 60 * 1000) if normalized_since_hours is not None else None
    )
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="pulse_trigger_dirty_targets",
        now_ms=int(now_ms),
    )
    downstream_job_depth = _pending_agent_job_count(repos)
    downstream_window_scope_job_depth = _pending_agent_job_count_for_window_scope(
        repos,
        window=normalized_window,
        scope=normalized_scope,
    )
    rows = _fetch_pulse_trigger_candidates(
        repos.conn,
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        window=normalized_window,
        scope=normalized_scope,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
    )
    targets = [
        _pulse_trigger_target(
            row,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            repair_reason=PULSE_TRIGGER_REPAIR_REASON,
        )
        for row in rows
    ]
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=downstream_job_depth,
        downstream_window_scope_job_depth=downstream_window_scope_job_depth,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        result = repos.pulse_trigger_dirty_targets.enqueue_targets(
            [
                {
                    "target_type": target["target_type"],
                    "target_id": target["target_id"],
                    "window": target["window"],
                    "scope": target["scope"],
                    "source_watermark_ms": target["source_watermark_ms"],
                    "payload_hash": target["payload_hash"],
                }
                for target in targets
            ],
            reason=PULSE_TRIGGER_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return {
        "work": "pulse_trigger",
        "window": normalized_window,
        "scope": normalized_scope,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "dry_run": not bool(execute),
        "execute": bool(execute),
        "since_hours": normalized_since_hours,
        "since_ms": since_ms,
        "target_id": normalized_target_id,
        "limit": parsed_limit,
        "candidate_count": len(targets),
        "would_enqueue_count": len(targets),
        "current_queue_depth": queue_depths["current_queue_depth"],
        "due_queue_depth": queue_depths["due_queue_depth"],
        "downstream_job_depth": downstream_job_depth,
        "downstream_window_scope_job_depth": downstream_window_scope_job_depth,
        "guardrail_violations": guardrail_violations,
        "enqueued_count": enqueued_count,
        "target_sample_count": min(len(targets), PULSE_TRIGGER_TARGET_SAMPLE_LIMIT),
        "target_sample": targets[:PULSE_TRIGGER_TARGET_SAMPLE_LIMIT],
    }


def _enqueue_narrative_admission_dirty_targets(
    repos: Any,
    *,
    window: str,
    scope: str,
    since_hours: float | None,
    target_id: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_window = str(window or "").strip()
    if normalized_window not in NARRATIVE_ADMISSION_WINDOWS:
        raise ValueError(f"unsupported narrative_admission repair window: {normalized_window}")
    normalized_scope = str(scope or "").strip()
    if normalized_scope not in NARRATIVE_ADMISSION_SCOPES:
        raise ValueError(f"unsupported narrative_admission repair scope: {normalized_scope}")

    normalized_target_id = str(target_id or "").strip() or None
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="narrative_admission",
        max_since_hours=NARRATIVE_ADMISSION_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours or --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="narrative_admission")
    since_ms = (
        int(now_ms) - int(normalized_since_hours * 60 * 60 * 1000) if normalized_since_hours is not None else None
    )
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="narrative_admission_dirty_targets",
        now_ms=int(now_ms),
    )
    rows = _fetch_pulse_trigger_candidates(
        repos.conn,
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        window=normalized_window,
        scope=normalized_scope,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
    )
    targets = [
        _narrative_admission_target(
            row,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
            repair_reason=NARRATIVE_ADMISSION_REPAIR_REASON,
        )
        for row in rows
    ]
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        repo = getattr(repos, "narrative_admission_dirty_targets", None)
        if repo is None:
            raise RuntimeError("narrative_admission_dirty_targets repository is required for repair execution")
        result = repo.enqueue_targets(
            [
                {
                    "target_type": target["target_type"],
                    "target_id": target["target_id"],
                    "window": target["window"],
                    "scope": target["scope"],
                    "projection_version": target["projection_version"],
                    "schema_version": target["schema_version"],
                    "source_watermark_ms": target["source_watermark_ms"],
                    "payload_hash": target["payload_hash"],
                }
                for target in targets
            ],
            reason=NARRATIVE_ADMISSION_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return {
        "work": "narrative_admission",
        "window": normalized_window,
        "scope": normalized_scope,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "dry_run": not bool(execute),
        "execute": bool(execute),
        "since_hours": normalized_since_hours,
        "since_ms": since_ms,
        "target_id": normalized_target_id,
        "limit": parsed_limit,
        "candidate_count": len(targets),
        "would_enqueue_count": len(targets),
        "current_queue_depth": queue_depths["current_queue_depth"],
        "due_queue_depth": queue_depths["due_queue_depth"],
        "downstream_job_depth": 0,
        "downstream_window_scope_job_depth": 0,
        "guardrail_violations": guardrail_violations,
        "enqueued_count": enqueued_count,
        "target_sample_count": min(len(targets), PULSE_TRIGGER_TARGET_SAMPLE_LIMIT),
        "target_sample": targets[:PULSE_TRIGGER_TARGET_SAMPLE_LIMIT],
    }


def _enqueue_discussion_digest_dirty_targets(
    repos: Any,
    *,
    window: str,
    scope: str,
    since_hours: float | None,
    target_id: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_window = str(window or "").strip()
    if normalized_window not in DISCUSSION_DIGEST_WINDOWS:
        raise ValueError(f"unsupported discussion_digest repair window: {normalized_window}")
    normalized_scope = str(scope or "").strip()
    if normalized_scope not in DISCUSSION_DIGEST_SCOPES:
        raise ValueError(f"unsupported discussion_digest repair scope: {normalized_scope}")

    normalized_target_id = str(target_id or "").strip() or None
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="discussion_digest",
        max_since_hours=DISCUSSION_DIGEST_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours or --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="discussion_digest")
    since_ms = (
        int(now_ms) - int(normalized_since_hours * 60 * 60 * 1000) if normalized_since_hours is not None else None
    )
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="discussion_digest_dirty_targets",
        now_ms=int(now_ms),
    )
    rows = _fetch_discussion_digest_candidates(
        repos.conn,
        schema_version=NARRATIVE_SCHEMA_VERSION,
        window=normalized_window,
        scope=normalized_scope,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
    )
    targets = [
        _discussion_digest_target(
            row,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
            repair_reason=DISCUSSION_DIGEST_REPAIR_REASON,
        )
        for row in rows
    ]
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        repo = getattr(repos, "discussion_digest_dirty_targets", None)
        if repo is None:
            raise RuntimeError("discussion_digest_dirty_targets repository is required for repair execution")
        result = repo.enqueue_targets(
            [
                {
                    "target_type": target["target_type"],
                    "target_id": target["target_id"],
                    "window": target["window"],
                    "scope": target["scope"],
                    "projection_version": target["projection_version"],
                    "schema_version": target["schema_version"],
                    "source_watermark_ms": target["source_watermark_ms"],
                    "payload_hash": target["payload_hash"],
                }
                for target in targets
            ],
            reason=DISCUSSION_DIGEST_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return {
        "work": "discussion_digest",
        "window": normalized_window,
        "scope": normalized_scope,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "dry_run": not bool(execute),
        "execute": bool(execute),
        "since_hours": normalized_since_hours,
        "since_ms": since_ms,
        "target_id": normalized_target_id,
        "limit": parsed_limit,
        "candidate_count": len(targets),
        "would_enqueue_count": len(targets),
        "current_queue_depth": queue_depths["current_queue_depth"],
        "due_queue_depth": queue_depths["due_queue_depth"],
        "downstream_job_depth": 0,
        "downstream_window_scope_job_depth": 0,
        "guardrail_violations": guardrail_violations,
        "enqueued_count": enqueued_count,
        "target_sample_count": min(len(targets), PULSE_TRIGGER_TARGET_SAMPLE_LIMIT),
        "target_sample": targets[:PULSE_TRIGGER_TARGET_SAMPLE_LIMIT],
    }


def _enqueue_profile_current_dirty_targets(
    repos: Any,
    *,
    since_hours: float | None,
    target_type: str | None,
    target_id: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_target_id = str(target_id or "").strip() or None
    normalized_target_type = _target_type_value(target_type=target_type, target_id=normalized_target_id)
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="profile_current",
        max_since_hours=DETERMINISTIC_REPAIR_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours or --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="profile_current")
    since_ms = _since_ms(now_ms=now_ms, since_hours=normalized_since_hours)
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="token_profile_current_dirty_targets",
        now_ms=int(now_ms),
    )
    targets = (
        [
            {
                "target_type": normalized_target_type,
                "target_id": normalized_target_id,
                "source_watermark_ms": int(now_ms),
                "priority": 100,
            }
        ]
        if normalized_target_id is not None and since_ms is None
        else _fetch_profile_current_candidates(
            repos.conn,
            since_ms=since_ms,
            target_type=normalized_target_type if normalized_target_id else None,
            target_id=normalized_target_id,
            limit=parsed_limit,
        )
    )
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        repo = getattr(repos, "token_profile_current_dirty_targets", None)
        if repo is None:
            raise RuntimeError("token_profile_current_dirty_targets repository is required for repair execution")
        result = repo.enqueue_targets(
            targets,
            reason=PROFILE_CURRENT_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return _repair_result(
        work="profile_current",
        dry_run=not bool(execute),
        execute=execute,
        since_hours=normalized_since_hours,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
        targets=targets,
        queue_depths=queue_depths,
        guardrail_violations=guardrail_violations,
        enqueued_count=enqueued_count,
        extra={"target_type": normalized_target_type if normalized_target_id else None},
    )


def _enqueue_image_source_dirty_targets(
    repos: Any,
    *,
    since_hours: float | None,
    target_type: str | None,
    target_id: str | None,
    source_url: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_source_url = str(source_url or "").strip() or None
    normalized_target_id = str(target_id or "").strip() or None
    normalized_target_type = _target_type_value(target_type=target_type, target_id=normalized_target_id)
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="image_source",
        max_since_hours=DETERMINISTIC_REPAIR_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None and normalized_source_url is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours, --target-id, or --source-url")
    if normalized_source_url is not None and normalized_target_id is None:
        raise ValueError("image_source repair with --source-url also requires --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="image_source")
    since_ms = _since_ms(now_ms=now_ms, since_hours=normalized_since_hours)
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="token_image_source_dirty_targets",
        now_ms=int(now_ms),
    )
    targets = (
        [
            {
                "source_url": normalized_source_url,
                "source_provider": "ops_repair",
                "source_kind": "manual_source_url",
                "target_type": normalized_target_type,
                "target_id": normalized_target_id,
                "raw_ref_json": {"source": "ops_runtime_worker_repair"},
                "source_watermark_ms": int(now_ms),
                "priority": 100,
            }
        ]
        if normalized_source_url is not None
        else _fetch_image_source_candidates(
            repos.conn,
            since_ms=since_ms,
            target_type=normalized_target_type if normalized_target_id else None,
            target_id=normalized_target_id,
            limit=parsed_limit,
        )
    )
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        repo = getattr(repos, "token_image_source_dirty_targets", None)
        if repo is None:
            raise RuntimeError("token_image_source_dirty_targets repository is required for repair execution")
        result = repo.enqueue_targets(
            targets,
            reason=IMAGE_SOURCE_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return _repair_result(
        work="image_source",
        dry_run=not bool(execute),
        execute=execute,
        since_hours=normalized_since_hours,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
        targets=targets,
        queue_depths=queue_depths,
        guardrail_violations=guardrail_violations,
        enqueued_count=enqueued_count,
        extra={
            "target_type": normalized_target_type if normalized_target_id else None,
            "source_url": normalized_source_url,
        },
    )


def _enqueue_asset_profile_refresh_targets(
    repos: Any,
    *,
    since_hours: float | None,
    provider: str | None,
    target_id: str | None,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    normalized_provider = str(provider or "").strip()
    if not normalized_provider:
        raise ValueError("asset_profile_refresh repair requires --provider")
    normalized_target_id = str(target_id or "").strip() or None
    normalized_since_hours = _since_hours_value(
        since_hours,
        work="asset_profile_refresh",
        max_since_hours=DETERMINISTIC_REPAIR_MAX_SINCE_HOURS,
    )
    if normalized_since_hours is None and normalized_target_id is None:
        raise ValueError("enqueue-runtime-worker-dirty-targets requires --since-hours or --target-id")

    parsed_limit = _limit_value(limit, execute=execute, work="asset_profile_refresh")
    since_ms = _since_ms(now_ms=now_ms, since_hours=normalized_since_hours)
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="asset_profile_refresh_targets",
        now_ms=int(now_ms),
    )
    targets = _fetch_asset_profile_refresh_candidates(
        repos.conn,
        provider=normalized_provider,
        since_ms=since_ms,
        target_id=normalized_target_id,
        now_ms=now_ms,
        limit=parsed_limit,
    )
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute and targets:
        repo = getattr(repos, "asset_profile_refresh_targets", None)
        if repo is None:
            raise RuntimeError("asset_profile_refresh_targets repository is required for repair execution")
        result = repo.enqueue_targets(
            targets,
            reason=ASSET_PROFILE_REFRESH_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return _repair_result(
        work="asset_profile_refresh",
        dry_run=not bool(execute),
        execute=execute,
        since_hours=normalized_since_hours,
        since_ms=since_ms,
        target_id=normalized_target_id,
        limit=parsed_limit,
        targets=targets,
        queue_depths=queue_depths,
        guardrail_violations=guardrail_violations,
        enqueued_count=enqueued_count,
        extra={"provider": normalized_provider},
    )


def _enqueue_capture_tier_dirty_targets(
    repos: Any,
    *,
    work: str,
    limit: int | None,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    parsed_limit = _limit_value(limit, execute=execute, work=work)
    queue_depths = _runtime_worker_queue_depths(
        repos.conn,
        table_name="token_capture_tier_dirty_targets",
        now_ms=int(now_ms),
    )
    targets = [{"work_name": "active_live_market_rank_set", "partition_key": "global"}]
    guardrail_violations = _guardrail_violations(
        candidate_count=len(targets),
        would_enqueue_count=len(targets),
        current_queue_depth=queue_depths["current_queue_depth"],
        due_queue_depth=queue_depths["due_queue_depth"],
        downstream_job_depth=0,
        downstream_window_scope_job_depth=0,
    )
    if execute and guardrail_violations:
        raise ValueError(
            "runtime worker dirty target repair guardrail refused execution: " + ", ".join(guardrail_violations)
        )

    enqueued_count = 0
    if execute:
        repo = getattr(repos, "token_capture_tier_dirty_targets", None)
        if repo is None:
            raise RuntimeError("token_capture_tier_dirty_targets repository is required for repair execution")
        result = repo.enqueue_global(
            reason=CAPTURE_TIER_REPAIR_REASON,
            now_ms=int(now_ms),
            commit=False,
        )
        enqueued_count = _enqueued_count(result)
        repos.conn.commit()

    return _repair_result(
        work=work,
        dry_run=not bool(execute),
        execute=execute,
        since_hours=None,
        since_ms=None,
        target_id="global",
        limit=parsed_limit,
        targets=targets,
        queue_depths=queue_depths,
        guardrail_violations=guardrail_violations,
        enqueued_count=enqueued_count,
        extra={"partition_key": "global"},
    )


def _fetch_pulse_trigger_candidates(
    conn: Any,
    *,
    projection_version: str,
    window: str,
    scope: str,
    since_ms: int | None,
    target_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH bounded AS (
          SELECT
            current_rows.target_type,
            current_rows.target_id,
            current_rows."window",
            current_rows.scope,
            GREATEST(
              current_rows.source_max_received_at_ms,
              current_rows.computed_at_ms
            ) AS source_watermark_ms,
            current_rows.payload_hash AS current_row_payload_hash,
            row_number() OVER (
              PARTITION BY
                current_rows.target_type,
                current_rows.target_id,
                current_rows."window",
                current_rows.scope
              ORDER BY
                GREATEST(current_rows.source_max_received_at_ms, current_rows.computed_at_ms) DESC,
                current_rows.rank ASC,
                current_rows.lane DESC
            ) AS target_rank
          FROM token_radar_current_rows current_rows
          WHERE current_rows.projection_version = %(projection_version)s
            AND current_rows."window" = %(window)s
            AND current_rows.scope = %(scope)s
            AND current_rows.target_id IS NOT NULL
            AND (%(target_id)s IS NULL OR current_rows.target_id = %(target_id)s)
            AND (
              %(since_ms)s IS NULL
              OR current_rows.source_max_received_at_ms >= %(since_ms)s
              OR current_rows.computed_at_ms >= %(since_ms)s
            )
        )
        SELECT
          target_type,
          target_id,
          "window",
          scope,
          source_watermark_ms,
          current_row_payload_hash
        FROM bounded
        WHERE target_rank = 1
        ORDER BY source_watermark_ms DESC, target_type ASC, target_id ASC
        LIMIT %(limit)s
        """,
        {
            "projection_version": str(projection_version),
            "window": str(window),
            "scope": str(scope),
            "since_ms": int(since_ms) if since_ms is not None else None,
            "target_id": str(target_id) if target_id is not None else None,
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_discussion_digest_candidates(
    conn: Any,
    *,
    schema_version: str,
    window: str,
    scope: str,
    since_ms: int | None,
    target_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          admissions.target_type,
          admissions.target_id,
          admissions."window",
          admissions.scope,
          GREATEST(
            COALESCE(admissions.source_max_received_at_ms, 0),
            COALESCE(admissions.source_window_end_ms, 0),
            COALESCE(admissions.updated_at_ms, 0)
          ) AS source_watermark_ms,
          admissions.source_fingerprint AS current_row_payload_hash
        FROM narrative_admissions AS admissions
        WHERE admissions.schema_version = %(schema_version)s
          AND admissions.status = 'admitted'
          AND admissions."window" = %(window)s
          AND admissions.scope = %(scope)s
          AND admissions.target_id IS NOT NULL
          AND (%(target_id)s IS NULL OR admissions.target_id = %(target_id)s)
          AND (
            %(since_ms)s IS NULL
            OR admissions.source_max_received_at_ms >= %(since_ms)s
            OR admissions.source_window_end_ms >= %(since_ms)s
            OR admissions.updated_at_ms >= %(since_ms)s
          )
        ORDER BY source_watermark_ms DESC, admissions.target_type ASC, admissions.target_id ASC
        LIMIT %(limit)s
        """,
        {
            "schema_version": str(schema_version),
            "window": str(window),
            "scope": str(scope),
            "since_ms": int(since_ms) if since_ms is not None else None,
            "target_id": str(target_id) if target_id is not None else None,
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_profile_current_candidates(
    conn: Any,
    *,
    since_ms: int | None,
    target_type: str | None,
    target_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH current_radar_sets AS MATERIALIZED (
          SELECT "window", scope, computed_at_ms
          FROM token_radar_projection_coverage
          WHERE projection_version = %(projection_version)s
            AND status = 'ready'
            AND computed_at_ms IS NOT NULL
        ),
        radar_targets AS MATERIALIZED (
          SELECT
            token_radar_current_rows.target_type,
            token_radar_current_rows.target_id,
            MAX(token_radar_current_rows.source_max_received_at_ms) AS source_watermark_ms
          FROM current_radar_sets
          JOIN token_radar_current_rows
            ON token_radar_current_rows.projection_version = %(projection_version)s
           AND token_radar_current_rows."window" = current_radar_sets."window"
           AND token_radar_current_rows.scope = current_radar_sets.scope
           AND token_radar_current_rows.computed_at_ms = current_radar_sets.computed_at_ms
          WHERE token_radar_current_rows.target_type IN ('Asset', 'CexToken')
            AND token_radar_current_rows.target_id IS NOT NULL
            AND (%(target_type)s IS NULL OR token_radar_current_rows.target_type = %(target_type)s)
            AND (%(target_id)s IS NULL OR token_radar_current_rows.target_id = %(target_id)s)
            AND (%(since_ms)s IS NULL OR token_radar_current_rows.source_max_received_at_ms >= %(since_ms)s)
          GROUP BY token_radar_current_rows.target_type, token_radar_current_rows.target_id
        ),
        recent_resolution_targets AS MATERIALIZED (
          SELECT
            token_intent_resolutions.target_type,
            token_intent_resolutions.target_id,
            MAX(events.received_at_ms) AS source_watermark_ms
          FROM events
          JOIN token_intent_resolutions
            ON token_intent_resolutions.event_id = events.event_id
          WHERE (%(since_ms)s IS NULL OR events.received_at_ms >= %(since_ms)s)
            AND token_intent_resolutions.is_current = true
            AND token_intent_resolutions.resolver_policy_version = %(resolver_policy_version)s
            AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
            AND token_intent_resolutions.target_id IS NOT NULL
            AND (%(target_type)s IS NULL OR token_intent_resolutions.target_type = %(target_type)s)
            AND (%(target_id)s IS NULL OR token_intent_resolutions.target_id = %(target_id)s)
          GROUP BY token_intent_resolutions.target_type, token_intent_resolutions.target_id
        ),
        target_seeds AS (
          SELECT * FROM radar_targets
          UNION ALL
          SELECT * FROM recent_resolution_targets
        )
        SELECT
          target_type,
          target_id,
          MAX(source_watermark_ms) AS source_watermark_ms,
          100 AS priority
        FROM target_seeds
        GROUP BY target_type, target_id
        ORDER BY MAX(source_watermark_ms) DESC NULLS LAST, target_type ASC, target_id ASC
        LIMIT %(limit)s
        """,
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "resolver_policy_version": "token_radar_v5_identity_resolver",
            "since_ms": int(since_ms) if since_ms is not None else None,
            "target_type": str(target_type) if target_type is not None else None,
            "target_id": str(target_id) if target_id is not None else None,
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_image_source_candidates(
    conn: Any,
    *,
    since_ms: int | None,
    target_type: str | None,
    target_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH source_rows AS (
          SELECT
            NULLIF(btrim(asset_profiles.logo_url), '') AS source_url,
            asset_profiles.provider AS source_provider,
            'asset_profiles.logo_url' AS source_kind,
            'Asset' AS target_type,
            asset_profiles.asset_id AS target_id,
            jsonb_build_object(
              'asset_id', asset_profiles.asset_id,
              'provider', asset_profiles.provider
            ) AS raw_ref_json,
            COALESCE(asset_profiles.updated_at_ms, asset_profiles.observed_at_ms, 0) AS source_watermark_ms,
            100 AS priority
          FROM asset_profiles
          WHERE asset_profiles.status = 'ready'
            AND NULLIF(btrim(asset_profiles.logo_url), '') IS NOT NULL
            AND (%(since_ms)s IS NULL OR asset_profiles.updated_at_ms >= %(since_ms)s)
            AND (%(target_type)s IS NULL OR %(target_type)s = 'Asset')
            AND (%(target_id)s IS NULL OR asset_profiles.asset_id = %(target_id)s)

          UNION ALL

          SELECT
            NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'i'), '') AS source_url,
            'gmgn_stream_snapshot' AS source_provider,
            'asset_identity_evidence.raw_payload_json.i' AS source_kind,
            'Asset' AS target_type,
            asset_identity_evidence.asset_id AS target_id,
            jsonb_build_object(
              'asset_id', asset_identity_evidence.asset_id,
              'provider', asset_identity_evidence.provider,
              'evidence_id', asset_identity_evidence.evidence_id,
              'evidence_kind', asset_identity_evidence.evidence_kind
            ) AS raw_ref_json,
            COALESCE(asset_identity_evidence.observed_at_ms, 0) AS source_watermark_ms,
            100 AS priority
          FROM asset_identity_evidence
          WHERE asset_identity_evidence.provider = 'gmgn'
            AND asset_identity_evidence.evidence_kind = 'gmgn_payload_exact'
            AND NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'i'), '') IS NOT NULL
            AND (%(since_ms)s IS NULL OR asset_identity_evidence.observed_at_ms >= %(since_ms)s)
            AND (%(target_type)s IS NULL OR %(target_type)s = 'Asset')
            AND (%(target_id)s IS NULL OR asset_identity_evidence.asset_id = %(target_id)s)

          UNION ALL

          SELECT
            NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'tokenLogoUrl'), '') AS source_url,
            'okx_dex_evidence' AS source_provider,
            'asset_identity_evidence.raw_payload_json.tokenLogoUrl' AS source_kind,
            'Asset' AS target_type,
            asset_identity_evidence.asset_id AS target_id,
            jsonb_build_object(
              'asset_id', asset_identity_evidence.asset_id,
              'provider', asset_identity_evidence.provider,
              'evidence_id', asset_identity_evidence.evidence_id,
              'evidence_kind', asset_identity_evidence.evidence_kind
            ) AS raw_ref_json,
            COALESCE(asset_identity_evidence.observed_at_ms, 0) AS source_watermark_ms,
            100 AS priority
          FROM asset_identity_evidence
          WHERE asset_identity_evidence.provider = 'okx'
            AND asset_identity_evidence.evidence_kind = 'okx_dex_exact_address'
            AND NULLIF(btrim(asset_identity_evidence.raw_payload_json->>'tokenLogoUrl'), '') IS NOT NULL
            AND (%(since_ms)s IS NULL OR asset_identity_evidence.observed_at_ms >= %(since_ms)s)
            AND (%(target_type)s IS NULL OR %(target_type)s = 'Asset')
            AND (%(target_id)s IS NULL OR asset_identity_evidence.asset_id = %(target_id)s)

          UNION ALL

          SELECT
            NULLIF(btrim(cex_token_profiles.logo_url), '') AS source_url,
            cex_token_profiles.provider AS source_provider,
            'cex_token_profiles.logo_url' AS source_kind,
            'CexToken' AS target_type,
            cex_token_profiles.cex_token_id AS target_id,
            jsonb_build_object(
              'cex_token_id', cex_token_profiles.cex_token_id,
              'provider', cex_token_profiles.provider,
              'source_ref', cex_token_profiles.source_ref
            ) AS raw_ref_json,
            COALESCE(cex_token_profiles.updated_at_ms, cex_token_profiles.observed_at_ms, 0) AS source_watermark_ms,
            100 AS priority
          FROM cex_token_profiles
          WHERE cex_token_profiles.status = 'ready'
            AND NULLIF(btrim(cex_token_profiles.logo_url), '') IS NOT NULL
            AND (%(since_ms)s IS NULL OR cex_token_profiles.updated_at_ms >= %(since_ms)s)
            AND (%(target_type)s IS NULL OR %(target_type)s = 'CexToken')
            AND (%(target_id)s IS NULL OR cex_token_profiles.cex_token_id = %(target_id)s)
        ),
        deduped AS (
          SELECT
            *,
            row_number() OVER (
              PARTITION BY source_url, target_type, target_id
              ORDER BY source_watermark_ms DESC, source_provider ASC, source_kind ASC
            ) AS row_number
          FROM source_rows
          WHERE source_url IS NOT NULL
        )
        SELECT
          source_url,
          source_provider,
          source_kind,
          target_type,
          target_id,
          raw_ref_json,
          source_watermark_ms,
          priority
        FROM deduped
        WHERE row_number = 1
        ORDER BY source_watermark_ms DESC, source_url ASC
        LIMIT %(limit)s
        """,
        {
            "since_ms": int(since_ms) if since_ms is not None else None,
            "target_type": str(target_type) if target_type is not None else None,
            "target_id": str(target_id) if target_id is not None else None,
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_asset_profile_refresh_candidates(
    conn: Any,
    *,
    provider: str,
    since_ms: int | None,
    target_id: str | None,
    now_ms: int,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH candidate_assets AS (
          SELECT
            token_intent_resolutions.target_id AS asset_id,
            MAX(events.received_at_ms) AS source_watermark_ms
          FROM events
          JOIN token_intent_resolutions
            ON token_intent_resolutions.event_id = events.event_id
          WHERE (%(since_ms)s IS NULL OR events.received_at_ms >= %(since_ms)s)
            AND token_intent_resolutions.is_current = true
            AND token_intent_resolutions.resolver_policy_version = %(resolver_policy_version)s
            AND token_intent_resolutions.target_type = 'Asset'
            AND token_intent_resolutions.target_id IS NOT NULL
            AND (%(target_id)s IS NULL OR token_intent_resolutions.target_id = %(target_id)s)
          GROUP BY token_intent_resolutions.target_id
          UNION
          SELECT
            token_radar_current_rows.target_id AS asset_id,
            MAX(token_radar_current_rows.source_max_received_at_ms) AS source_watermark_ms
          FROM token_radar_current_rows
          WHERE token_radar_current_rows.projection_version = %(projection_version)s
            AND token_radar_current_rows.target_type = 'Asset'
            AND token_radar_current_rows.target_id IS NOT NULL
            AND (%(since_ms)s IS NULL OR token_radar_current_rows.source_max_received_at_ms >= %(since_ms)s)
            AND (%(target_id)s IS NULL OR token_radar_current_rows.target_id = %(target_id)s)
          GROUP BY token_radar_current_rows.target_id
          UNION
          SELECT
            registry_assets.asset_id,
            %(now_ms)s AS source_watermark_ms
          FROM registry_assets
          WHERE %(target_id)s IS NOT NULL
            AND registry_assets.asset_id = %(target_id)s
        )
        SELECT
          %(provider)s AS provider,
          'Asset' AS target_type,
          candidate_assets.asset_id AS target_id,
          registry_assets.chain_id,
          registry_assets.address,
          asset_identity_current.canonical_symbol AS symbol,
          MAX(candidate_assets.source_watermark_ms) AS source_watermark_ms,
          100 AS priority
        FROM candidate_assets
        JOIN registry_assets
          ON registry_assets.asset_id = candidate_assets.asset_id
        LEFT JOIN asset_identity_current
          ON asset_identity_current.asset_id = candidate_assets.asset_id
        WHERE registry_assets.chain_id IS NOT NULL
          AND registry_assets.address IS NOT NULL
        GROUP BY
          candidate_assets.asset_id,
          registry_assets.chain_id,
          registry_assets.address,
          asset_identity_current.canonical_symbol
        ORDER BY MAX(candidate_assets.source_watermark_ms) DESC, candidate_assets.asset_id ASC
        LIMIT %(limit)s
        """,
        {
            "provider": str(provider),
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "resolver_policy_version": "token_radar_v5_identity_resolver",
            "since_ms": int(since_ms) if since_ms is not None else None,
            "target_id": str(target_id) if target_id is not None else None,
            "now_ms": int(now_ms),
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _pulse_trigger_target(row: dict[str, Any], *, projection_version: str, repair_reason: str) -> dict[str, Any]:
    target = {
        "target_type": str(row.get("target_type") or ""),
        "target_id": str(row.get("target_id") or ""),
        "window": str(row.get("window") or ""),
        "scope": str(row.get("scope") or ""),
        "source_watermark_ms": int(row.get("source_watermark_ms") or 0),
        "current_row_payload_hash": str(row.get("current_row_payload_hash") or ""),
    }
    payload = {
        "target": {
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "window": target["window"],
            "scope": target["scope"],
        },
        "projection_version": str(projection_version),
        "source_watermark_ms": target["source_watermark_ms"],
        "current_row_payload_hash": target["current_row_payload_hash"],
        "reason": str(repair_reason),
    }
    target["payload_hash"] = _payload_hash(payload)
    return target


def _narrative_admission_target(
    row: dict[str, Any],
    *,
    projection_version: str,
    schema_version: str,
    repair_reason: str,
) -> dict[str, Any]:
    target = {
        "target_type": str(row.get("target_type") or ""),
        "target_id": str(row.get("target_id") or ""),
        "window": str(row.get("window") or ""),
        "scope": str(row.get("scope") or ""),
        "projection_version": str(projection_version),
        "schema_version": str(schema_version),
        "source_watermark_ms": int(row.get("source_watermark_ms") or 0),
        "current_row_payload_hash": str(row.get("current_row_payload_hash") or ""),
    }
    payload = {
        "target": {
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "window": target["window"],
            "scope": target["scope"],
        },
        "projection_version": target["projection_version"],
        "schema_version": target["schema_version"],
        "source_watermark_ms": target["source_watermark_ms"],
        "current_row_payload_hash": target["current_row_payload_hash"],
        "reason": str(repair_reason),
    }
    target["payload_hash"] = _payload_hash(payload)
    return target


def _discussion_digest_target(
    row: dict[str, Any],
    *,
    projection_version: str,
    schema_version: str,
    repair_reason: str,
) -> dict[str, Any]:
    target = {
        "target_type": str(row.get("target_type") or ""),
        "target_id": str(row.get("target_id") or ""),
        "window": str(row.get("window") or ""),
        "scope": str(row.get("scope") or ""),
        "projection_version": str(projection_version),
        "schema_version": str(schema_version),
        "source_watermark_ms": int(row.get("source_watermark_ms") or 0),
        "current_row_payload_hash": str(row.get("current_row_payload_hash") or ""),
    }
    payload = {
        "target": {
            "target_type": target["target_type"],
            "target_id": target["target_id"],
            "window": target["window"],
            "scope": target["scope"],
        },
        "projection_version": target["projection_version"],
        "schema_version": target["schema_version"],
        "source_watermark_ms": target["source_watermark_ms"],
        "current_row_payload_hash": target["current_row_payload_hash"],
        "reason": str(repair_reason),
    }
    target["payload_hash"] = _payload_hash(payload)
    return target


def _payload_hash(payload: dict[str, Any]) -> str:
    safe_payload = postgres_safe_json(payload)
    encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _since_hours_value(value: float | None, *, work: str, max_since_hours: float) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("--since-hours must be greater than 0")
    if parsed > max_since_hours:
        raise ValueError(f"--since-hours must be <= {max_since_hours:g} for {work} repair")
    return parsed


def _since_ms(*, now_ms: int, since_hours: float | None) -> int | None:
    if since_hours is None:
        return None
    return int(now_ms) - int(float(since_hours) * 60 * 60 * 1000)


def _limit_value(value: int | None, *, execute: bool, work: str) -> int:
    if value is None:
        if execute:
            raise ValueError("--execute requires explicit --limit for runtime worker dirty target repair")
        return PULSE_TRIGGER_DEFAULT_DRY_RUN_LIMIT
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("--limit must be greater than 0")
    if parsed > PULSE_TRIGGER_MAX_LIMIT:
        raise ValueError(f"--limit must be <= {PULSE_TRIGGER_MAX_LIMIT} for {work} repair")
    return parsed


def _runtime_worker_queue_depths(conn: Any, *, table_name: str, now_ms: int) -> dict[str, int]:
    if table_name not in {
        "pulse_trigger_dirty_targets",
        "narrative_admission_dirty_targets",
        "discussion_digest_dirty_targets",
        "token_profile_current_dirty_targets",
        "token_image_source_dirty_targets",
        "asset_profile_refresh_targets",
        "token_capture_tier_dirty_targets",
    }:
        raise ValueError(f"unsupported dirty target queue table: {table_name}")
    row = conn.execute(
        f"""
        SELECT
          count(*) AS current_queue_depth,
          count(*) FILTER (
            WHERE due_at_ms <= %(now_ms)s
              AND (leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s)
          ) AS due_queue_depth
        FROM {table_name}
        """,
        {"now_ms": int(now_ms)},
    ).fetchone()
    return {
        "current_queue_depth": int(row["current_queue_depth"] if row else 0),
        "due_queue_depth": int(row["due_queue_depth"] if row else 0),
    }


def _pending_agent_job_count(repos: Any) -> int:
    pulse_jobs = getattr(repos, "pulse_jobs", None)
    count_func = getattr(pulse_jobs, "pending_agent_job_count", None)
    if count_func is None:
        return 0
    return int(count_func())


def _pending_agent_job_count_for_window_scope(repos: Any, *, window: str, scope: str) -> int:
    pulse_jobs = getattr(repos, "pulse_jobs", None)
    count_func = getattr(pulse_jobs, "pending_agent_job_count_for_window_scope", None)
    if count_func is None:
        return 0
    return int(count_func(window=window, scope=scope))


def _guardrail_violations(
    *,
    candidate_count: int,
    would_enqueue_count: int,
    current_queue_depth: int,
    due_queue_depth: int,
    downstream_job_depth: int,
    downstream_window_scope_job_depth: int,
) -> list[str]:
    violations: list[str] = []
    if candidate_count > PULSE_TRIGGER_MAX_LIMIT:
        violations.append("candidate_count")
    if would_enqueue_count > PULSE_TRIGGER_MAX_LIMIT:
        violations.append("would_enqueue_count")
    if current_queue_depth > PULSE_TRIGGER_MAX_QUEUE_DEPTH:
        violations.append("current_queue_depth")
    if due_queue_depth > PULSE_TRIGGER_MAX_DUE_QUEUE_DEPTH:
        violations.append("due_queue_depth")
    if downstream_job_depth > PULSE_TRIGGER_MAX_DOWNSTREAM_JOB_DEPTH:
        violations.append("downstream_job_depth")
    if downstream_window_scope_job_depth > PULSE_TRIGGER_MAX_DOWNSTREAM_WINDOW_SCOPE_JOB_DEPTH:
        violations.append("downstream_window_scope_job_depth")
    return violations


def _target_type_value(*, target_type: str | None, target_id: str | None) -> str:
    normalized = str(target_type or "").strip()
    if normalized:
        if normalized not in {"Asset", "CexToken"}:
            raise ValueError("--target-type must be Asset or CexToken")
        return normalized
    normalized_target_id = str(target_id or "").strip()
    if normalized_target_id.startswith("cex_token:"):
        return "CexToken"
    return "Asset"


def _repair_result(
    *,
    work: str,
    dry_run: bool,
    execute: bool,
    since_hours: float | None,
    since_ms: int | None,
    target_id: str | None,
    limit: int,
    targets: list[dict[str, Any]],
    queue_depths: dict[str, int],
    guardrail_violations: list[str],
    enqueued_count: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "work": str(work),
        "dry_run": bool(dry_run),
        "execute": bool(execute),
        "since_hours": since_hours,
        "since_ms": since_ms,
        "target_id": target_id,
        "limit": int(limit),
        "candidate_count": len(targets),
        "would_enqueue_count": len(targets),
        "current_queue_depth": queue_depths["current_queue_depth"],
        "due_queue_depth": queue_depths["due_queue_depth"],
        "downstream_job_depth": 0,
        "downstream_window_scope_job_depth": 0,
        "guardrail_violations": guardrail_violations,
        "enqueued_count": int(enqueued_count),
        "target_sample_count": min(len(targets), PULSE_TRIGGER_TARGET_SAMPLE_LIMIT),
        "target_sample": targets[:PULSE_TRIGGER_TARGET_SAMPLE_LIMIT],
    }
    if extra:
        result.update(extra)
    return result


def _enqueued_count(result: Any) -> int:
    if isinstance(result, dict):
        return int(result.get("targets") or result.get("enqueued") or 0)
    return int(result or 0)


__all__ = [
    "DISCUSSION_DIGEST_SCOPES",
    "DISCUSSION_DIGEST_WINDOWS",
    "PULSE_TRIGGER_SCOPES",
    "PULSE_TRIGGER_WINDOWS",
    "WORK_CHOICES",
    "enqueue_runtime_worker_dirty_targets",
]
