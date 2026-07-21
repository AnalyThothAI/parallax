from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.app.operations.reference_data_sync import (
    sync_binance_cex_profiles_once,
    sync_binance_usdt_perp_universe,
    sync_us_equity_symbols_once,
)
from parallax.app.operations.run_worker_once import (
    refresh_asset_profiles_once,
    repair_token_profile_images_once,
    run_worker_once,
)
from parallax.app.runtime.ops_cli_queries import (
    token_radar_max_market_tick_observed_at_ms,
    token_radar_max_resolution_ms,
    token_radar_publication_status,
    token_radar_source_count,
)
from parallax.app.runtime.projection_dirty_targets import enqueue_projection_dirty_targets
from parallax.app.runtime.repository_session import repositories
from parallax.app.surfaces.cli.commands import queue_ops
from parallax.domains.asset_market.repositories.token_capture_tier_dirty_target_repository import (
    token_capture_tier_rank_set_payload_hash,
)
from parallax.domains.token_intel._constants import WINDOW_MS
from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    require_token_factor_snapshot,
)
from parallax.domains.token_intel.runtime.token_intent_rebuild import rebuild_recent_token_intents
from parallax.domains.token_intel.scoring.factor_diagnostics import factor_distribution_report
from parallax.domains.token_intel.services.token_resolution_refresh import reprocess_recent_token_intents
from parallax.platform.config.settings import load_settings
from parallax.platform.db.postgres_audit import ProjectionValidationAudit
from parallax.platform.validation import require_nonnegative_int, require_positive_int


def handle_ops(args: object, parser: object) -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)

    if args.ops_command == "refresh-asset-profiles":
        data = refresh_asset_profiles_once(settings, limit=args.limit).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "rebuild-token-profiles":
        data = run_worker_once(settings, "token_profile_current", {"batch_size": args.limit}).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "mirror-token-images":
        data = run_worker_once(settings, "token_image_mirror", {"batch_size": args.limit}).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "repair-token-profile-images":
        data = repair_token_profile_images_once(settings, limit=args.limit).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "run-resolution-refresh":
        data = run_worker_once(
            settings,
            "resolution_refresh",
            {"batch_size": args.limit, "reprocess_limit": args.reprocess_limit},
        ).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "reprocess-token-intents":
        now_ms = _now_ms()
        with repositories(settings) as repos:
            reprocess = reprocess_recent_token_intents(
                repos=repos,
                now_ms=now_ms,
                window=args.window,
                limit=args.limit,
                lookup_keys=args.lookup_key or None,
            )
        projection = run_worker_once(
            settings,
            "token_radar_projection",
            {"batch_size": args.projection_limit},
        ).payload()
        return 0, {"ok": True, "data": {"reprocess": reprocess, "projection": projection}}

    if args.ops_command == "rebuild-token-intents":
        now_ms = _now_ms()
        with repositories(settings) as repos:
            data = rebuild_recent_token_intents(
                repos=repos,
                now_ms=now_ms,
                window=args.window,
                limit=args.limit,
                projection_limit=args.projection_limit,
            )
        data["projection"] = run_worker_once(
            settings,
            "token_radar_projection",
            {"batch_size": args.projection_limit},
        ).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "rebuild-token-radar":
        data = run_worker_once(
            settings,
            "token_radar_projection",
            {"windows": (args.window,), "scopes": (args.scope,), "batch_size": args.limit},
        ).payload()
        return 0, {"ok": True, "data": data}

    if args.ops_command == "sync-binance-usdt-perp-universe":
        data = sync_binance_usdt_perp_universe(
            settings,
            dry_run=bool(args.dry_run),
            execute=bool(args.execute),
        )
        return 0, {"ok": True, "data": data}

    if args.ops_command == "sync-binance-cex-profiles":
        data = sync_binance_cex_profiles_once(settings)
        return 0, {"ok": True, "data": data}

    if args.ops_command == "sync-us-equity-symbols":
        data = sync_us_equity_symbols_once(settings)
        return 0, {"ok": True, "data": data}

    with repositories(settings) as repos:
        if args.ops_command == "news-dedup-diagnostics":
            window_hours = float(args.window_hours)
            if window_hours <= 0:
                raise ValueError("news_dedup_window_hours_required")
            return (
                0,
                {
                    "ok": True,
                    "data": repos.news_pages.news_dedup_diagnostics(
                        window_ms=int(window_hours * 3_600_000),
                        now_ms=_now_ms(),
                    ),
                },
            )

        if args.ops_command == "rebuild-news-canonical-items":
            data = _rebuild_news_canonical_items(
                repos,
                limit=args.limit,
                dry_run=bool(args.dry_run),
                execute=bool(args.execute),
                now_ms=_now_ms(),
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "queue-inspect":
            return queue_ops.handle_queue_inspect(args, repos)

        if args.ops_command == "queue-resolve":
            return queue_ops.handle_queue_resolve(args, repos, now_ms=_now_ms())

        if args.ops_command == "queue-resolve-bucket":
            return queue_ops.handle_queue_resolve_bucket(args, repos, now_ms=_now_ms())

        if args.ops_command == "reconcile-event-anchor-jobs":
            if args.execute:
                with repos.transaction():
                    data = repos.event_anchor_jobs.reconcile_ready_historical_jobs(
                        limit=args.limit,
                        now_ms=_now_ms(),
                        execute=True,
                    )
            else:
                data = repos.event_anchor_jobs.reconcile_ready_historical_jobs(
                    limit=args.limit,
                    now_ms=_now_ms(),
                    execute=False,
                )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "factor-diagnostics":
            rows = repos.token_radar.latest_current_rows(
                window=args.window,
                scope=args.scope,
                venue=TOKEN_RADAR_DEFAULT_VENUE,
                limit=args.limit,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            )
            data = factor_distribution_report(rows)
            return (0 if data["ok"] else 1), {"ok": data["ok"], "data": data}

        if args.ops_command == "enqueue-token-radar-dirty-targets":
            data = _enqueue_token_radar_dirty_targets(
                repos,
                source=args.source,
                since_ms=args.since_ms,
                limit=args.limit,
                dry_run=bool(args.dry_run),
                execute=bool(args.execute),
                now_ms=_now_ms(),
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "enqueue-token-capture-tier-rank-set":
            data = _enqueue_token_capture_tier_rank_set(
                repos,
                window=args.window,
                limit=args.limit,
                dry_run=bool(args.dry_run),
                execute=bool(args.execute),
                now_ms=_now_ms(),
            )
            return 0, {"ok": True, "data": data}

        signals = repos.signals

        if args.ops_command == "projection-status":
            return 0, {
                "ok": True,
                "data": token_radar_publication_status(
                    signals.conn,
                    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                ),
            }

        if args.ops_command == "validate-projections":
            data = ProjectionValidationAudit(signals.conn).run(sample=args.sample)
            return (0 if data.get("ok") else 1), {"ok": bool(data.get("ok")), "data": data}

        if args.ops_command == "enqueue-projection-dirty-targets":
            now_ms = _now_ms()
            since_ms = now_ms - int(float(args.since_hours) * 60 * 60 * 1000) if args.since_hours is not None else None
            data = enqueue_projection_dirty_targets(
                repos,
                domain=args.domain,
                execute=bool(args.execute),
                now_ms=now_ms,
                projection=args.projection,
                since_ms=since_ms,
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "audit-token-intent":
            if not args.event_id and not args.intent_id:
                parser.error("audit-token-intent requires --event-id or --intent-id")
            data = _audit_token_intent(repos, event_id=args.event_id or None, intent_id=args.intent_id or None)
            return 0, {"ok": True, "data": data}

        if args.ops_command == "audit-token-radar":
            data = _audit_token_radar(
                repos,
                window=args.window,
                scope=args.scope,
                limit=args.limit,
                now_ms=_now_ms(),
            )
            return (0 if data["ok"] else 1), {"ok": data["ok"], "data": data}

    return 2, {"ok": False, "error": f"unknown ops command: {args.ops_command}"}


def _enqueue_token_radar_dirty_targets(
    repos: object,
    *,
    source: str,
    since_ms: int,
    limit: int,
    dry_run: bool,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    parsed_since_ms = require_nonnegative_int(
        since_ms,
        error_code="ops_token_radar_dirty_targets_since_ms_required",
    )
    parsed_limit = require_positive_int(
        limit,
        error_code="ops_token_radar_dirty_targets_limit_required",
    )
    data: dict[str, Any] = {
        "source": str(source),
        "since_ms": parsed_since_ms,
        "limit": parsed_limit,
        "dry_run": bool(dry_run),
        "execute": bool(execute),
    }
    if source == "events":
        repository = repos.token_radar_dirty_targets
        candidates = repository.count_recent_resolved_target_candidates(
            since_ms=parsed_since_ms,
            now_ms=now_ms,
            limit=parsed_limit,
        )
        data["candidates"] = int(candidates)
        if dry_run:
            data["would_enqueue"] = int(
                repository.count_recent_resolved_target_enqueue_candidates(
                    since_ms=parsed_since_ms,
                    now_ms=now_ms,
                    limit=parsed_limit,
                )
            )
            return data
        with repos.transaction():
            data["enqueued"] = int(
                repository.enqueue_recent_resolved_targets(
                    since_ms=parsed_since_ms,
                    now_ms=now_ms,
                    limit=parsed_limit,
                    reason="ops_events_repair",
                )
            )
        return data
    if source == "market-current":
        repository = repos.token_radar_dirty_targets
        candidates = repository.count_market_current_target_candidates(
            since_ms=parsed_since_ms,
            now_ms=now_ms,
            limit=parsed_limit,
        )
        data["candidates"] = int(candidates)
        if dry_run:
            data["would_enqueue"] = int(
                repository.count_market_current_target_enqueue_candidates(
                    since_ms=parsed_since_ms,
                    now_ms=now_ms,
                    limit=parsed_limit,
                )
            )
            return data
        with repos.transaction():
            data["enqueued"] = int(
                repository.enqueue_market_current_targets(
                    since_ms=parsed_since_ms,
                    now_ms=now_ms,
                    limit=parsed_limit,
                    reason="ops_market_current_repair",
                )
            )
        return data
    raise ValueError(f"unknown token radar dirty target source: {source}")


def _enqueue_token_capture_tier_rank_set(
    repos: object,
    *,
    window: str,
    limit: int,
    dry_run: bool,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    parsed_window = str(window)
    parsed_limit = require_positive_int(
        limit,
        error_code="ops_capture_tier_rank_set_limit_required",
    )
    since_ms = max(0, int(now_ms) - _ops_window_ms(parsed_window))
    reason = f"ops_capture_tier_repair:{parsed_window}"
    data: dict[str, Any] = {
        "window": parsed_window,
        "since_ms": since_ms,
        "limit": parsed_limit,
        "reason": reason,
        "dry_run": bool(dry_run),
        "execute": bool(execute),
    }
    if dry_run:
        rows = repos.registry.ranked_live_market_targets(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            since_ms=since_ms,
            limit=parsed_limit,
        )
        source_watermark_ms = _ops_capture_tier_rank_set_source_watermark_ms(rows)
        data["target_count"] = len(rows)
        data["payload_hash"] = token_capture_tier_rank_set_payload_hash(reason=reason, rows=rows)
        data["source_watermark_ms"] = source_watermark_ms
        data["would_enqueue"] = 1 if rows else 0
        data["enqueued"] = 0
        data["skipped"] = 0
        return data
    with repos.transaction():
        rows = repos.registry.ranked_live_market_targets(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            since_ms=since_ms,
            limit=parsed_limit,
        )
        source_watermark_ms = _ops_capture_tier_rank_set_source_watermark_ms(rows)
        data["target_count"] = len(rows)
        data["payload_hash"] = token_capture_tier_rank_set_payload_hash(reason=reason, rows=rows)
        data["source_watermark_ms"] = source_watermark_ms
        if not rows:
            data["enqueued"] = 0
            data["skipped"] = 1
            return data
        result = repos.token_capture_tier_dirty_targets.enqueue_rank_set(
            reason=reason,
            rows=rows,
            exited_rows=[],
            source_watermark_ms=source_watermark_ms,
            now_ms=now_ms,
        )
    enqueued = int(result.get("targets") or 0)
    data["enqueued"] = enqueued
    data["skipped"] = 0 if enqueued else 1
    return data


def _ops_capture_tier_rank_set_source_watermark_ms(rows: list[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    watermarks = [_ops_capture_tier_rank_row_source_watermark_ms(row) for row in rows]
    return max(watermarks)


def _ops_capture_tier_rank_row_source_watermark_ms(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_max_received_at_ms"]
    except KeyError as exc:
        raise ValueError("ops_capture_tier_rank_set_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("ops_capture_tier_rank_set_source_watermark_required")
    if value <= 0:
        raise ValueError("ops_capture_tier_rank_set_source_watermark_required")
    return int(value)


def _ops_window_ms(window: str) -> int:
    try:
        return WINDOW_MS[window]
    except KeyError as exc:
        raise ValueError(f"invalid ops window: {window}") from exc


def _rebuild_news_canonical_items(
    repos: object,
    *,
    limit: int,
    dry_run: bool,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    parsed_limit = require_positive_int(
        limit,
        error_code="ops_news_canonical_rebuild_limit_required",
    )
    data: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "dry_run": bool(dry_run),
        "execute": bool(execute),
    }
    if dry_run:
        rows = repos.news_items.list_news_items_for_canonical_rebuild(limit=parsed_limit)
        targets = _news_canonical_rebuild_targets(rows)
        data["matched_canonical_items"] = len(rows)
        data["would_enqueue"] = len(targets)
        data["enqueued"] = 0
        data["deleted_disabled_rows"] = 0
        return data
    with repos.transaction():
        rows = repos.news_items.list_news_items_for_canonical_rebuild(limit=parsed_limit)
        targets = _news_canonical_rebuild_targets(rows)
        data["matched_canonical_items"] = len(rows)
        data["would_enqueue"] = len(targets)
        deleted = repos.news_pages.delete_page_rows_without_enabled_observation_edges()
        enqueued = repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason="ops_news_canonical_rebuild",
            now_ms=now_ms,
        )
    data["enqueued"] = int(enqueued)
    data["deleted_disabled_rows"] = int(deleted)
    return data


def _news_canonical_rebuild_targets(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    story_watermarks: dict[str, int] = {}
    story_order: list[str] = []
    for row in rows:
        news_item_id = _required_news_canonical_rebuild_text(row, "news_item_id")
        source_watermark_ms = _required_news_canonical_rebuild_watermark(row)
        targets.append(
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": news_item_id,
                "source_watermark_ms": source_watermark_ms,
            }
        )
        story_key = _required_news_canonical_rebuild_text(row, "story_key")
        if story_key not in story_watermarks:
            story_order.append(story_key)
        story_watermarks[story_key] = max(story_watermarks.get(story_key, 0), source_watermark_ms)
    targets.extend(
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": story_key,
            "source_watermark_ms": story_watermarks[story_key],
        }
        for story_key in story_order
    )
    return targets


def _required_news_canonical_rebuild_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError(f"ops_news_canonical_rebuild_{field_name}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"ops_news_canonical_rebuild_{field_name}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"ops_news_canonical_rebuild_{field_name}_required")
    return text


def _required_news_canonical_rebuild_watermark(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("ops_news_canonical_rebuild_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("ops_news_canonical_rebuild_source_watermark_required")
    if value <= 0:
        raise ValueError("ops_news_canonical_rebuild_source_watermark_required")
    return int(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _audit_token_intent(repos: object, *, event_id: str | None, intent_id: str | None) -> dict:
    if intent_id:
        intents = [repos.token_intents.get(intent_id)]
        intents = [item for item in intents if item]
    else:
        intents = repos.token_intents.intents_for_event(str(event_id))
    intent_ids = [str(item["intent_id"]) for item in intents]
    evidence = []
    resolutions = []
    for current_intent_id in intent_ids:
        evidence.extend(repos.token_intents.evidence_links_for_intent(current_intent_id))
        resolution = repos.intent_resolutions.active_resolution_for_intent(current_intent_id)
        if resolution:
            resolutions.append(resolution)
    return {
        "event_id": event_id,
        "intent_id": intent_id,
        "intents": intents,
        "intent_evidence": evidence,
        "active_resolutions": resolutions,
    }


def _audit_token_radar(repos: object, *, window: str, scope: str, limit: int, now_ms: int) -> dict:
    rows = repos.token_radar.latest_current_rows(
        window=window,
        scope=scope,
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        limit=limit,
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
    )
    source_current_window_rows = token_radar_source_count(
        repos.conn,
        since_ms=now_ms - WINDOW_MS[window],
        scope=scope,
        resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    )
    source_max_resolution_ms = token_radar_max_resolution_ms(repos.conn)
    source_max_market_tick_observed_at_ms = token_radar_max_market_tick_observed_at_ms(repos.conn)
    return {
        "window": window,
        "scope": scope,
        "limit": limit,
        **_audit_token_radar_current_rows(
            rows,
            now_ms=now_ms,
            source_current_window_rows=source_current_window_rows,
            source_max_resolution_ms=source_max_resolution_ms,
            source_max_market_tick_observed_at_ms=source_max_market_tick_observed_at_ms,
        ),
    }


def _audit_token_radar_current_rows(
    rows: list[dict],
    *,
    now_ms: int,
    source_current_window_rows: int,
    source_max_resolution_ms: int | None,
    source_max_market_tick_observed_at_ms: int | None,
) -> dict:
    violations: list[dict] = []
    required = set(TOKEN_RADAR_FACTOR_FAMILIES)
    required_blocks = ("gates", "data_health", "normalization", "composite")
    if not rows and source_current_window_rows:
        violations.append({"code": "empty_projection_rows"})
    for index, row in enumerate(rows):
        projection_version = row.get("projection_version")
        if projection_version != TOKEN_RADAR_PROJECTION_VERSION:
            violations.append({"row": index, "code": "wrong_projection_version", "value": projection_version})
        factor_version = row.get("factor_version")
        if factor_version != TOKEN_FACTOR_SNAPSHOT_VERSION:
            violations.append({"row": index, "code": "wrong_factor_version", "value": factor_version})
        factor_snapshot = row.get("factor_snapshot_json") if isinstance(row.get("factor_snapshot_json"), dict) else {}
        if not factor_snapshot:
            violations.append({"row": index, "code": "missing_factor_snapshot"})
        elif factor_snapshot.get("schema_version") != TOKEN_FACTOR_SNAPSHOT_VERSION:
            violations.append(
                {
                    "row": index,
                    "code": "wrong_factor_snapshot_version",
                    "value": factor_snapshot.get("schema_version"),
                }
            )
        else:
            try:
                require_token_factor_snapshot(factor_snapshot, field_name="factor_snapshot_json")
            except ValueError as exc:
                violations.append(
                    {
                        "row": index,
                        "code": "invalid_factor_snapshot_contract",
                        "error": str(exc),
                    }
                )
        families = factor_snapshot.get("families") if isinstance(factor_snapshot.get("families"), dict) else {}
        missing = sorted(required - set(families))
        extra = sorted(set(families) - required)
        if missing:
            violations.append({"row": index, "code": "missing_factor_families", "families": missing})
        if extra:
            violations.append({"row": index, "code": "extra_factor_families", "families": extra})
        violations.extend(
            {"row": index, "code": "missing_factor_snapshot_block", "block": block_name}
            for block_name in required_blocks
            if not isinstance(factor_snapshot.get(block_name), dict)
        )
        for family in sorted(required & set(families)):
            block = families.get(family) if isinstance(families.get(family), dict) else {}
            if "score" not in block:
                violations.append({"row": index, "family": family, "code": "missing_family_score"})
            if not block.get("data_health"):
                violations.append({"row": index, "family": family, "code": "missing_family_data_health"})
            if not isinstance(block.get("facts"), dict):
                violations.append({"row": index, "family": family, "code": "missing_family_facts"})
            if not isinstance(block.get("factors"), dict):
                violations.append({"row": index, "family": family, "code": "missing_family_factors"})
        composite = factor_snapshot.get("composite") if isinstance(factor_snapshot.get("composite"), dict) else {}
        if "rank_score" not in composite:
            violations.append({"row": index, "code": "missing_composite_rank_score"})
        recommended_decision = composite.get("recommended_decision")
        if not recommended_decision:
            violations.append({"row": index, "code": "missing_composite_decision"})
        elif row.get("decision") and row.get("decision") != recommended_decision:
            violations.append(
                {
                    "row": index,
                    "code": "decision_mismatch",
                    "row_decision": row.get("decision"),
                    "factor_decision": recommended_decision,
                }
            )
        gates = factor_snapshot.get("gates") if isinstance(factor_snapshot.get("gates"), dict) else {}
        if row.get("decision") == "high_alert" and gates.get("eligible_for_high_alert") is not True:
            violations.append({"row": index, "code": "high_alert_without_gate_eligibility"})
    social_lag_ms = max(0, int(now_ms) - int(source_max_resolution_ms)) if source_max_resolution_ms else None
    market_lag_ms = None
    if source_max_market_tick_observed_at_ms:
        market_lag_ms = max(0, int(now_ms) - int(source_max_market_tick_observed_at_ms))
    return {
        "ok": not violations,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "row_count": len(rows),
        "violations": violations,
        "source_current_window_rows": source_current_window_rows,
        "source_max_resolution_ms": source_max_resolution_ms,
        "source_max_market_tick_observed_at_ms": source_max_market_tick_observed_at_ms,
        "social_lag_ms": social_lag_ms,
        "market_lag_ms": market_lag_ms,
    }


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
