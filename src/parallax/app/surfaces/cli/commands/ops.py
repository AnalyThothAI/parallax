from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from parallax.app.runtime.bootstrap import bootstrap
from parallax.app.runtime.db_pool_bundle import DBPoolBundle
from parallax.app.runtime.ops_cli_queries import (
    market_tick_current_rebuild_estimate,
    token_profile_image_repair_targets,
    token_radar_max_market_tick_observed_at_ms,
    token_radar_max_resolution_ms,
    token_radar_source_count,
)
from parallax.app.runtime.projection_dirty_targets import enqueue_projection_dirty_targets
from parallax.app.runtime.providers_wiring import wire_asset_market_providers
from parallax.app.runtime.telemetry import TelemetryRegistry
from parallax.app.runtime.worker_status import workers_status_payload
from parallax.app.surfaces.cli.commands import queue_ops
from parallax.app.surfaces.cli.dependencies import repositories
from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from parallax.domains.account_quality.services.account_quality_backfill_service import AccountQualityBackfillService
from parallax.domains.asset_market.repositories.token_capture_tier_dirty_target_repository import (
    token_capture_tier_rank_set_payload_hash,
)
from parallax.domains.asset_market.runtime.asset_profile_refresh_worker import AssetProfileRefreshWorker
from parallax.domains.asset_market.runtime.resolution_refresh_worker import ResolutionRefreshWorker
from parallax.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from parallax.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from parallax.domains.asset_market.services.asset_market_sync import sync_binance_usdt_perp_routes
from parallax.domains.asset_market.services.cex_token_profile_sync import sync_cex_token_profiles
from parallax.domains.asset_market.services.market_tick_current_rebuild import (
    MarketTickCurrentRebuildService,
)
from parallax.domains.asset_market.services.us_equity_symbol_sync import (
    NasdaqTraderSymbolClient,
    sync_us_equity_symbols,
)
from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    require_token_factor_snapshot,
)
from parallax.domains.token_intel.repositories.projection_repository import ProjectionRepository
from parallax.domains.token_intel.runtime.token_intent_rebuild import rebuild_recent_token_intents
from parallax.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from parallax.domains.token_intel.scoring.factor_diagnostics import factor_distribution_report
from parallax.domains.token_intel.services.token_factor_evaluation import settle_token_factor_scores
from parallax.domains.token_intel.services.token_radar_projection import WINDOW_MS
from parallax.domains.token_intel.services.token_resolution_refresh import reprocess_recent_token_intents
from parallax.integrations.binance.cex_profile_client import BinanceCexProfileClient
from parallax.integrations.binance.usdm_futures_client import BinanceUsdmFuturesClient
from parallax.integrations.gmgn.directory_client import GmgnDirectoryClient, GmgnDirectoryError
from parallax.platform.config.settings import load_settings
from parallax.platform.db.postgres_audit import ProjectionValidationAudit

LEGACY_FACTOR_GATE_KEY = "_".join(("hard", "gates"))
LEGACY_FACTOR_GATE_PRESENT_CODE = f"{LEGACY_FACTOR_GATE_KEY}_present"


def handle_ops(args: object, parser: object) -> tuple[int, dict[str, Any]]:
    settings = load_settings(require_ws_token=False)

    if args.ops_command == "worker-status":
        return 0, {"ok": True, "data": _worker_status_payload(settings)}

    if args.ops_command == "refresh-asset-profiles":
        data = _run_asset_profile_refresh_worker_once(settings, limit=args.limit, now_ms=_now_ms())
        return 0, {"ok": True, "data": data}

    if args.ops_command == "rebuild-token-profiles":
        data = _run_token_profile_current_worker_once(settings, limit=args.limit, now_ms=_now_ms())
        return 0, {"ok": True, "data": data}

    if args.ops_command == "mirror-token-images":
        data = _run_token_image_mirror_worker_once(
            settings,
            limit=args.limit,
            now_ms=_now_ms(),
        )
        return 0, {"ok": True, "data": data}

    if args.ops_command == "repair-token-profile-images":
        data = _run_token_profile_image_repair_once(settings, limit=args.limit, now_ms=_now_ms())
        return 0, {"ok": True, "data": data}

    if args.ops_command == "run-resolution-refresh":
        data = _run_resolution_refresh_worker_once(
            settings,
            limit=args.limit,
            reprocess_limit=args.reprocess_limit,
            now_ms=_now_ms(),
        )
        return 0, {"ok": True, "data": data}

    if args.ops_command == "rebuild-market-tick-current":
        data = _run_market_tick_current_rebuild(
            settings,
            dry_run=bool(args.dry_run),
            execute=bool(args.execute),
            now_ms=_now_ms(),
        )
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
        projection = _run_token_radar_projection_worker_once(
            settings,
            limit=args.projection_limit,
            now_ms=now_ms,
        )
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
        data["projection"] = _run_token_radar_projection_worker_once(
            settings,
            limit=args.projection_limit,
            now_ms=now_ms,
        )
        return 0, {"ok": True, "data": data}

    if args.ops_command == "rebuild-token-radar":
        data = _run_token_radar_projection_worker_once(
            settings,
            windows=(args.window,),
            scopes=(args.scope,),
            limit=args.limit,
            now_ms=_now_ms(),
        )
        return 0, {"ok": True, "data": data}

    with repositories(settings) as repos:
        if args.ops_command == "news-dedup-diagnostics":
            window_hours = max(0.0, float(args.window_hours))
            return (
                0,
                {
                    "ok": True,
                    "data": repos.news.news_dedup_diagnostics(
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

        if args.ops_command == "reconcile-event-anchor-jobs":
            data = repos.event_anchor_jobs.reconcile_ready_historical_jobs(
                limit=args.limit,
                now_ms=_now_ms(),
                execute=bool(args.execute),
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

        if args.ops_command == "settle-token-factors":
            data = settle_token_factor_scores(
                repos=repos,
                horizon=args.horizon,
                window=args.window,
                scope=args.scope,
                generated_at_ms=args.now_ms if args.now_ms is not None else _now_ms(),
                limit=args.limit,
            )
            return 0, {"ok": True, "data": data}

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

        if args.ops_command == "backfill-account-quality":
            data = AccountQualityBackfillService(
                repository=AccountQualityRepository(signals.conn),
            ).backfill_account_token_call_stats(limit=args.limit)
            return 0, {"ok": True, "data": data}

        if args.ops_command == "projection-status":
            return 0, {"ok": True, "data": ProjectionRepository(signals.conn).status_summary()}

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

        if args.ops_command == "sync-binance-usdt-perp-universe":
            client = BinanceUsdmFuturesClient(
                base_url=settings.binance_usdm_futures_base_url,
                timeout_seconds=settings.binance_timeout_seconds,
            )
            try:
                data = sync_binance_usdt_perp_routes(
                    registry=repos.registry,
                    client=client,
                    observed_at_ms=_now_ms(),
                    dry_run=bool(args.dry_run),
                    execute=bool(args.execute),
                )
            finally:
                client.close()
            return 0, {"ok": True, "data": data}

        if args.ops_command == "sync-binance-cex-profiles":
            client = BinanceCexProfileClient(
                base_url=settings.binance_cex_profile_base_url,
                timeout_seconds=settings.binance_timeout_seconds,
            )
            try:
                data = sync_cex_token_profiles(
                    cex_token_profiles=repos.cex_token_profiles,
                    profile_source=client,
                    observed_at_ms=_now_ms(),
                )
            finally:
                client.close()
            return 0, {"ok": True, "data": data}

        if args.ops_command == "sync-us-equity-symbols":
            client = NasdaqTraderSymbolClient(timeout_seconds=settings.okx_timeout_seconds)
            try:
                data = sync_us_equity_symbols(
                    registry=repos.registry,
                    client=client,
                    observed_at_ms=_now_ms(),
                )
            finally:
                client.close()
            return 0, {"ok": True, "data": data}

        if args.ops_command == "sync-gmgn-directory":
            client = GmgnDirectoryClient()
            try:
                data = _run_sync_gmgn_directory(
                    client=client,
                    repository=AccountQualityRepository(signals.conn),
                    now_ms=_now_ms(),
                    max_pages=args.max_pages,
                )
            except GmgnDirectoryError as exc:
                return 1, {"ok": False, "error": str(exc)}
            finally:
                client.close()
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


def _run_market_tick_current_rebuild(
    settings: object,
    *,
    dry_run: bool,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    telemetry = TelemetryRegistry()
    db = None
    advisory_lock = None
    worker_name = "market_tick_current_projection"
    lock_key = _market_tick_current_projection_lock_key(settings)
    mode = "execute" if execute else "dry_run"
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        if execute:
            try:
                advisory_lock = db.acquire_advisory_lock_connection(worker_name, lock_key)
            except RuntimeError as exc:
                if "advisory_lock_unavailable" not in str(exc):
                    raise
                return {
                    "mode": mode,
                    "dry_run": bool(dry_run),
                    "execute": bool(execute),
                    "status": "skipped",
                    "skipped": 1,
                    "scanned": 0,
                    "changed": 0,
                    "estimated_rows": 0,
                    "counts_by_target_type": {},
                    "notes": {
                        "reason": "advisory_lock_unavailable",
                        "worker_name": worker_name,
                        "lock_key": lock_key,
                    },
                }
        worker_settings = settings.workers.market_tick_current_projection
        with db.worker_session(
            worker_name,
            statement_timeout_seconds=worker_settings.statement_timeout_seconds,
        ) as repos:
            estimate = market_tick_current_rebuild_estimate(repos.conn)
            if dry_run:
                return {
                    "mode": mode,
                    "dry_run": True,
                    "execute": False,
                    "scanned": int(estimate["scanned"]),
                    "estimated_rows": int(estimate["estimated_rows"]),
                    "changed": 0,
                    "counts_by_target_type": dict(estimate["counts_by_target_type"]),
                }
            result = MarketTickCurrentRebuildService(repos).rebuild_all(now_ms=now_ms)
            return {
                "mode": mode,
                "dry_run": False,
                "execute": True,
                "scanned": int(result.get("scanned") or 0),
                "changed": int(result.get("changed") or 0),
                "estimated_rows": int(estimate["estimated_rows"]),
                "counts_by_target_type": dict(estimate["counts_by_target_type"]),
            }
    finally:
        if advisory_lock is not None:
            _release_advisory_lock_connection(advisory_lock)
        if db is not None:
            _close_db_bundle(db)


def _market_tick_current_projection_lock_key(settings: object) -> int:
    return int(settings.workers.market_tick_current_projection.advisory_lock_key)


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
    parsed_since_ms = max(0, int(since_ms))
    parsed_limit = max(0, int(limit))
    data: dict[str, Any] = {
        "source": str(source),
        "since_ms": parsed_since_ms,
        "limit": parsed_limit,
        "dry_run": bool(dry_run),
        "execute": bool(execute),
    }
    if source == "events":
        repository = repos.token_radar_source_dirty_events
        candidates = repository.count_recent_resolved_event_candidates(
            since_ms=parsed_since_ms,
            now_ms=now_ms,
            limit=parsed_limit,
        )
        data["candidates"] = int(candidates)
        if dry_run:
            data["would_enqueue"] = int(candidates)
            return data
        with _transaction(repos.conn):
            rows = repository.list_recent_resolved_events(
                since_ms=parsed_since_ms,
                now_ms=now_ms,
                limit=parsed_limit,
            )
            data["enqueued"] = int(
                repository.enqueue_events(rows, reason="ops_events_repair", now_ms=now_ms, commit=False)
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
        with _transaction(repos.conn):
            data["enqueued"] = int(
                repository.enqueue_market_current_targets(
                    since_ms=parsed_since_ms,
                    now_ms=now_ms,
                    limit=parsed_limit,
                    reason="ops_market_current_repair",
                    commit=False,
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
    parsed_limit = max(0, int(limit))
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
    with _transaction(repos.conn):
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
            commit=False,
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
    data: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "dry_run": bool(dry_run),
        "execute": bool(execute),
    }
    if dry_run:
        news_item_ids = repos.news.list_news_item_ids_for_canonical_rebuild(limit=max(0, int(limit)))
        targets = [
            {"projection_name": projection_name, "target_kind": "news_item", "target_id": news_item_id}
            for news_item_id in news_item_ids
            for projection_name in ("page", "brief_input")
        ]
        data["matched_canonical_items"] = len(news_item_ids)
        data["would_enqueue"] = len(targets)
        data["enqueued"] = 0
        data["deleted_disabled_rows"] = 0
        return data
    with _transaction(repos.conn):
        news_item_ids = repos.news.list_news_item_ids_for_canonical_rebuild(limit=max(0, int(limit)))
        targets = [
            {"projection_name": projection_name, "target_kind": "news_item", "target_id": news_item_id}
            for news_item_id in news_item_ids
            for projection_name in ("page", "brief_input")
        ]
        data["matched_canonical_items"] = len(news_item_ids)
        data["would_enqueue"] = len(targets)
        deleted = repos.news.delete_page_rows_without_enabled_observation_edges(commit=False)
        enqueued = repos.news_projection_dirty_targets.enqueue_targets(
            targets,
            reason="ops_news_canonical_rebuild",
            now_ms=now_ms,
            commit=False,
        )
    data["enqueued"] = int(enqueued)
    data["deleted_disabled_rows"] = int(deleted)
    return data


def _cursor_mapping(raw: str) -> dict[str, Any]:
    if not str(raw or "").strip():
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("after-cursor must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("after-cursor must be a JSON object")
    return payload


def _cursor_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_sync_gmgn_directory(
    *,
    client: object,
    repository: object,
    now_ms: int,
    max_pages: int,
) -> dict:
    upserted = 0
    handles: list[str] = []
    entries = list(client.iter_entries(max_pages=max_pages))
    with _transaction(repository.conn):
        for entry in entries:
            repository.upsert_directory_entry(
                handle=entry.handle,
                gmgn_user_id=entry.gmgn_user_id,
                user_tags=entry.user_tags,
                platform_followers=entry.platform_followers,
                observed_at_ms=now_ms,
                commit=False,
            )
            upserted += 1
            handles.append(entry.handle)
    return {
        "upserted": upserted,
        "first_handles": handles[:5],
        "last_handles": handles[-5:],
        "observed_at_ms": now_ms,
    }


def _worker_status_payload(settings: object) -> dict[str, Any]:
    runtime = None
    try:
        runtime = bootstrap(settings, start_collector=False)
        return workers_status_payload(runtime)
    finally:
        if runtime is not None:
            asyncio.run(runtime.aclose())


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise RuntimeError("ops_command_transaction_required") from exc
    if not callable(transaction):
        raise RuntimeError("ops_command_transaction_required")
    return cast(AbstractContextManager[Any], transaction())


def _run_asset_profile_refresh_worker_once(settings: object, *, limit: int, now_ms: int) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    asset_market = None
    worker = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        asset_market = wire_asset_market_providers(settings, start_collector=True)
        worker = AssetProfileRefreshWorker(
            name="asset_profile_refresh",
            settings=_worker_settings_with_overrides(settings.workers.asset_profile_refresh, batch_size=limit),
            db=db,
            telemetry=telemetry,
            dex_profile_sources=asset_market.dex_profile_sources,
        )
        result = asyncio.run(worker.run_once(now_ms=now_ms))
        return dict(result.notes.get("result") or {})
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if asset_market is not None:
            _close_asset_market_providers(asset_market)
        if db is not None:
            _close_db_bundle(db)


def _run_token_profile_current_worker_once(settings: object, *, limit: int, now_ms: int) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    worker = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        worker = TokenProfileCurrentWorker(
            name="token_profile_current",
            settings=_worker_settings_with_overrides(settings.workers.token_profile_current, batch_size=limit),
            db=db,
            telemetry=telemetry,
        )
        result = asyncio.run(worker.run_once(now_ms=now_ms))
        return dict(result.notes.get("result") or {})
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if db is not None:
            _close_db_bundle(db)


def _run_token_image_mirror_worker_once(settings: object, *, limit: int, now_ms: int) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    worker = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        worker = TokenImageMirrorWorker(
            name="token_image_mirror",
            settings=_worker_settings_with_overrides(
                settings.workers.token_image_mirror,
                batch_size=limit,
            ),
            db=db,
            telemetry=telemetry,
            app_home=settings.app_home,
        )
        result = asyncio.run(worker.run_once(now_ms=now_ms))
        return dict(result.notes.get("result") or {})
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if db is not None:
            _close_db_bundle(db)


def _run_token_profile_image_repair_once(settings: object, *, limit: int, now_ms: int) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    worker = None
    bounded_limit = max(1, int(limit))
    profile_rebuild = {}
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        with db.worker_session("token_profile_image_repair") as repos, repos.transaction():
            targets = token_profile_image_repair_targets(repos.conn, limit=bounded_limit, now_ms=now_ms)
            enqueue_result = repos.token_profile_current_dirty_targets.enqueue_targets(
                targets,
                reason="token_profile_image_repair",
                now_ms=now_ms,
                commit=False,
            )

        worker = TokenProfileCurrentWorker(
            name="token_profile_current",
            settings=_worker_settings_with_overrides(settings.workers.token_profile_current, batch_size=bounded_limit),
            db=db,
            telemetry=telemetry,
        )
        worker_result = asyncio.run(worker.run_once(now_ms=now_ms))
        profile_rebuild = dict(worker_result.notes.get("result") or {})
        return {
            "selected_targets": len(targets),
            "profile_targets_enqueued": int(enqueue_result.get("targets", 0)),
            "profile_rebuild": profile_rebuild,
        }
    finally:
        try:
            if worker is not None:
                asyncio.run(worker.aclose())
        finally:
            if db is not None:
                _close_db_bundle(db)


def _run_resolution_refresh_worker_once(
    settings: object,
    *,
    limit: int,
    reprocess_limit: int,
    now_ms: int,
) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    asset_market = None
    worker = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        asset_market = wire_asset_market_providers(settings, start_collector=True)
        worker = ResolutionRefreshWorker(
            name="resolution_refresh",
            settings=_worker_settings_with_overrides(
                settings.workers.resolution_refresh,
                batch_size=limit,
                reprocess_limit=reprocess_limit,
            ),
            db=db,
            telemetry=telemetry,
            dex_discovery_market=asset_market.dex_discovery_market,
            wake_emitter=db.wake_emitter(),
        )
        result = asyncio.run(worker.run_once(now_ms=now_ms))
        return dict(result.notes.get("result") or {})
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if asset_market is not None:
            _close_asset_market_providers(asset_market)
        if db is not None:
            _close_db_bundle(db)


def _run_token_radar_projection_worker_once(
    settings: object,
    *,
    windows: tuple[str, ...] | None = None,
    scopes: tuple[str, ...] | None = None,
    limit: int,
    now_ms: int,
) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    worker = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        worker_name = "token_radar_projection"
        advisory_lock = None
        worker = TokenRadarProjectionWorker(
            name=worker_name,
            settings=_worker_settings_with_overrides(settings.workers.token_radar_projection, batch_size=limit),
            db=db,
            telemetry=telemetry,
            wake_emitter=db.wake_emitter(),
            wake_waiter=db.wake_listener(worker_name, settings.workers.token_radar_projection.wakes_on),
            enqueue_narrative_admission=bool(settings.workers.narrative_admission.enabled),
        )
        try:
            lock_key = _effective_worker_advisory_lock_key(worker)
            try:
                advisory_lock = db.acquire_advisory_lock_connection(
                    worker_name,
                    lock_key,
                )
            except RuntimeError as exc:
                if "advisory_lock_unavailable" not in str(exc):
                    raise
                return {
                    "status": "skipped",
                    "skipped": 1,
                    "rows_written": 0,
                    "source_rows": 0,
                    "claimed": 0,
                    "catch_up_enqueued": 0,
                    "windows": {},
                    "notes": {
                        "reason": "advisory_lock_unavailable",
                        "worker_name": worker_name,
                        "lock_key": lock_key,
                    },
                }
            return worker.rebuild_once(now_ms=now_ms, windows=windows, scopes=scopes, limit=limit)
        finally:
            if advisory_lock is not None:
                _release_advisory_lock_connection(advisory_lock)
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if db is not None:
            _close_db_bundle(db)


def _worker_settings_with_overrides(config: object, **overrides: object) -> object:
    try:
        model_copy = config.model_copy
    except AttributeError as exc:
        raise RuntimeError("ops_worker_settings_model_copy_required") from exc
    if not callable(model_copy):
        raise RuntimeError("ops_worker_settings_model_copy_required")
    return model_copy(update=overrides)


def _close_db_bundle(db: object) -> None:
    try:
        aclose = db.aclose
    except AttributeError as exc:
        raise RuntimeError("ops_db_bundle_aclose_required") from exc
    if not callable(aclose):
        raise RuntimeError("ops_db_bundle_aclose_required")
    asyncio.run(aclose())


def _release_advisory_lock_connection(connection: object) -> None:
    try:
        release = connection.release
    except AttributeError as exc:
        raise RuntimeError("ops_advisory_lock_release_required") from exc
    if not callable(release):
        raise RuntimeError("ops_advisory_lock_release_required")
    release()


def _effective_worker_advisory_lock_key(worker: object) -> int:
    try:
        resolve = worker._advisory_lock_key
    except AttributeError as exc:
        raise RuntimeError("ops_worker_advisory_lock_key_required") from exc
    if not callable(resolve):
        raise RuntimeError("ops_worker_advisory_lock_key_required")
    key = resolve()
    if key is None:
        raise RuntimeError("ops_worker_advisory_lock_key_required")
    return int(key)


def _close_asset_market_providers(asset_market: object) -> None:
    try:
        aclose = asset_market.aclose
    except AttributeError as exc:
        raise RuntimeError("ops_asset_market_providers_aclose_required") from exc
    if not callable(aclose):
        raise RuntimeError("ops_asset_market_providers_aclose_required")
    asyncio.run(aclose())


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
        if LEGACY_FACTOR_GATE_KEY in factor_snapshot:
            violations.append({"row": index, "code": LEGACY_FACTOR_GATE_PRESENT_CODE})
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
