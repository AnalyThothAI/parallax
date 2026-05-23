from __future__ import annotations

import asyncio
import inspect
import json
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.bootstrap import _cleanup_provider_roots_sync, bootstrap
from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.llm_gateway import LLMGateway
from gmgn_twitter_intel.app.runtime.provider_wiring.openai import build_agent_execution_gateway
from gmgn_twitter_intel.app.runtime.providers_wiring import wire_asset_market_providers, wire_providers
from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry
from gmgn_twitter_intel.app.runtime.worker_status import canonical_workers_status_payload
from gmgn_twitter_intel.app.surfaces.cli.dependencies import repositories
from gmgn_twitter_intel.domains.account_quality.read_models.account_quality_service import AccountQualityService
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker import AssetProfileRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import ResolutionRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import sync_binance_usdt_perp_routes
from gmgn_twitter_intel.domains.asset_market.services.cex_binance_hard_cut_cleanup import (
    CexBinanceHardCutAbort,
    cleanup_cex_binance_hard_cut,
)
from gmgn_twitter_intel.domains.asset_market.services.cex_token_profile_sync import sync_cex_token_profiles
from gmgn_twitter_intel.domains.asset_market.services.us_equity_symbol_sync import (
    NasdaqTraderSymbolClient,
    sync_us_equity_symbols,
)
from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.narrative_intel.queries import NarrativeBacklogHealthQuery
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import MentionSemanticsWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.narrative_admission_worker import NarrativeAdmissionWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    require_token_factor_snapshot,
)
from gmgn_twitter_intel.domains.token_intel.repositories.projection_repository import ProjectionRepository
from gmgn_twitter_intel.domains.token_intel.runtime.token_intent_rebuild import rebuild_recent_token_intents
from gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh import reprocess_recent_token_intents
from gmgn_twitter_intel.domains.token_intel.scoring.factor_diagnostics import factor_distribution_report
from gmgn_twitter_intel.domains.token_intel.services.token_factor_evaluation import settle_token_factor_scores
from gmgn_twitter_intel.domains.token_intel.services.token_radar_postgres_hard_reset import (
    drop_expired_postgres_partitions,
    ensure_postgres_partitions,
    reset_token_radar_postgres_hard_cut,
)
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import WINDOW_MS
from gmgn_twitter_intel.integrations.binance.cex_profile_client import BinanceCexProfileClient
from gmgn_twitter_intel.integrations.binance.usdm_futures_client import BinanceUsdmFuturesClient
from gmgn_twitter_intel.integrations.gmgn.directory_client import GmgnDirectoryClient, GmgnDirectoryError
from gmgn_twitter_intel.platform.config.settings import load_settings
from gmgn_twitter_intel.platform.db.postgres_audit import ProjectionValidationAudit

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
            source_limit=args.source_limit,
            now_ms=_now_ms(),
        )
        return 0, {"ok": True, "data": data}

    if args.ops_command == "run-resolution-refresh":
        data = _run_resolution_refresh_worker_once(
            settings,
            limit=args.limit,
            reprocess_limit=args.reprocess_limit,
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

    if args.ops_command == "rebuild-narrative-intel":
        if not settings.narrative_intel_configured:
            return 1, {"ok": False, "error": "narrative_intel_not_configured"}
        data = _run_narrative_intel_rebuild(
            settings,
            window=args.window,
            scope=args.scope,
            semantic_limit=max(1, int(args.semantic_limit)),
            digest_limit=max(1, int(args.digest_limit)),
            cycles=max(1, int(args.cycles)),
            drain=bool(args.drain),
            now_ms=_now_ms(),
        )
        return 0, {"ok": True, "data": data}

    with repositories(settings) as repos:
        if args.ops_command == "factor-diagnostics":
            rows = repos.token_radar.latest_current_rows(
                window=args.window,
                scope=args.scope,
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

        if args.ops_command == "reset-token-radar-postgres-hard-cut":
            data = reset_token_radar_postgres_hard_cut(
                repos.signals.conn,
                dry_run=bool(args.dry_run),
                execute=bool(args.execute),
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "ensure-postgres-partitions":
            data = ensure_postgres_partitions(
                repos.signals.conn,
                now_ms=_now_ms(),
                dry_run=False,
                execute=bool(args.execute),
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "drop-expired-postgres-partitions":
            data = drop_expired_postgres_partitions(
                repos.signals.conn,
                execute=bool(args.execute),
            )
            return 0, {"ok": True, "data": data}

        if args.ops_command == "backfill-watchlist-signal-stats":
            data = _backfill_watchlist_signal_stats(
                repos.watchlist_intel,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
                after_cursor=args.after_cursor,
                dry_run=bool(args.dry_run),
            )
            return 0, {"ok": True, "data": data}

        signals = repos.signals
        enrichment = repos.enrichment

        if args.ops_command == "backfill-account-quality":
            data = AccountQualityService(
                signals=signals,
                repository=AccountQualityRepository(signals.conn),
            ).backfill_account_token_call_stats(limit=args.limit)
            return 0, {"ok": True, "data": data}

        if args.ops_command == "backfill-enrichment-jobs":
            return 0, {"ok": True, "data": enrichment.enqueue_missing_watched_events(limit=args.limit)}

        if args.ops_command == "projection-status":
            return 0, {"ok": True, "data": ProjectionRepository(signals.conn).status_summary()}

        if args.ops_command == "validate-projections":
            data = ProjectionValidationAudit(signals.conn).run(sample=args.sample)
            return (0 if data.get("ok") else 1), {"ok": bool(data.get("ok")), "data": data}

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

        if args.ops_command == "cex-binance-hard-cut-cleanup":
            try:
                data = cleanup_cex_binance_hard_cut(
                    repos.registry,
                    dry_run=bool(args.dry_run),
                    execute=bool(args.execute),
                    min_binance_feeds=int(args.min_binance_feeds),
                    now_ms=_now_ms(),
                )
            except CexBinanceHardCutAbort as exc:
                return 1, {"ok": False, "error": str(exc)}
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


def _backfill_watchlist_signal_stats(
    repository: object,
    *,
    batch_size: int,
    max_batches: int,
    dry_run: bool,
    after_cursor: str = "",
) -> dict[str, Any]:
    parsed_batch_size = max(1, int(batch_size))
    parsed_max_batches = max(1, int(max_batches))
    parsed_cursor = _cursor_mapping(after_cursor)
    after_received_at_ms = _optional_int(parsed_cursor.get("received_at_ms"))
    after_event_id = str(parsed_cursor.get("event_id") or "") or None
    batches = 0
    processed = 0
    signal_events = 0
    normalized_handles = 0
    has_more = False
    for _ in range(parsed_max_batches):
        result = dict(
            _call_with_supported_kwargs(
                repository.backfill_signal_stats_batch,  # type: ignore[attr-defined]
                after_received_at_ms=after_received_at_ms,
                after_event_id=after_event_id,
                batch_size=parsed_batch_size,
                dry_run=dry_run,
                commit=not dry_run,
            )
        )
        batches += 1
        processed += int(result.get("processed") or 0)
        signal_events += int(result.get("signal_events") or 0)
        normalized_handles += int(result.get("normalized_handles") or 0)
        has_more = bool(result.get("has_more"))
        next_received_at_ms = _optional_int(result.get("last_received_at_ms"))
        next_event_id = str(result.get("last_event_id") or "") or None
        if next_received_at_ms is not None and next_event_id is not None:
            after_received_at_ms = next_received_at_ms
            after_event_id = next_event_id
        if not has_more or next_received_at_ms is None or next_event_id is None:
            break
    last_cursor = (
        {"received_at_ms": after_received_at_ms, "event_id": after_event_id}
        if after_received_at_ms is not None and after_event_id is not None
        else None
    )
    return {
        "processed": processed,
        "upserted": signal_events,
        "has_more": has_more,
        "last_cursor": last_cursor,
        "next_after_cursor": _cursor_json(last_cursor),
        "batches": batches,
        "signal_events": signal_events,
        "normalized_handles": normalized_handles,
        "last_received_at_ms": after_received_at_ms,
        "last_event_id": after_event_id,
        "dry_run": bool(dry_run),
    }


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


def _optional_int(value: object) -> int | None:
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
    for entry in client.iter_entries(max_pages=max_pages):
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
    # single transaction: all-or-nothing for the full directory sync
    repository.conn.commit()
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
        return {"workers": canonical_workers_status_payload(runtime)}
    finally:
        if runtime is not None:
            asyncio.run(runtime.aclose())


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


def _run_token_image_mirror_worker_once(settings: object, *, limit: int, source_limit: int, now_ms: int) -> dict:
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
                source_limit=source_limit,
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
            dex_quote_market=asset_market.dex_quote_market,
            chain_ids=asset_market.discovery_chain_ids or settings.workers.resolution_refresh.chain_ids,
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
            wake_bus=db.wake_emitter(),
            wake_waiter=db.wake_listener(worker_name, settings.workers.token_radar_projection.wakes_on),
        )
        try:
            lock_key = _effective_worker_advisory_lock_key(worker)
            advisory_lock = db.acquire_advisory_lock_connection(
                worker_name,
                lock_key,
            )
            return worker.rebuild_once(now_ms=now_ms, windows=windows, scopes=scopes, limit=limit)
        finally:
            if advisory_lock is not None:
                _release_advisory_lock_connection(advisory_lock)
    finally:
        if worker is not None:
            asyncio.run(worker.aclose())
        if db is not None:
            _close_db_bundle(db)


def _run_narrative_intel_rebuild(
    settings: object,
    *,
    window: str,
    scope: str,
    semantic_limit: int,
    digest_limit: int,
    cycles: int,
    drain: bool,
    now_ms: int,
) -> dict:
    telemetry = TelemetryRegistry()
    db = None
    llm_gateway = None
    agent_execution_gateway = None
    provider_resource = None
    workers: list[object] = []
    locks: list[object] = []
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        llm_gateway = LLMGateway.create(settings)
        agent_execution_gateway = build_agent_execution_gateway(settings, llm_gateway=llm_gateway)
        providers = wire_providers(
            settings,
            start_collector=False,
            agent_execution_gateway=agent_execution_gateway,
            db_pool=db.tool_pool,
        )
        provider = providers.narrative_intel.narrative_provider
        provider_resource = provider
        if provider is None:
            return {"cycles": 0, "error": "narrative_provider_not_configured"}
        admission = NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=_worker_settings_with_overrides(
                settings.workers.narrative_admission,
                windows=(window,),
                scopes=(scope,),
            ),
            db=db,
            telemetry=telemetry,
            wake_bus=db.wake_emitter(),
        )
        semantics = MentionSemanticsWorker(
            name="mention_semantics",
            settings=_worker_settings_with_overrides(
                settings.workers.mention_semantics,
                batch_size=semantic_limit,
                provider_batch_size=semantic_limit,
            ),
            db=db,
            telemetry=telemetry,
            provider=provider,
            wake_bus=db.wake_emitter(),
        )
        digest = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=_worker_settings_with_overrides(settings.workers.token_discussion_digest, batch_size=digest_limit),
            db=db,
            telemetry=telemetry,
            provider=provider,
        )
        workers = [admission, semantics, digest]
        locks.extend(
            [
                db.acquire_advisory_lock_connection(
                    str(getattr(worker, "name", worker.__class__.__name__)),
                    _effective_worker_advisory_lock_key(worker),
                )
                for worker in workers
            ]
        )
        results = []
        cleanup_totals: dict[str, int] = {}
        for cycle in range(max(1, int(cycles))):
            cycle_now_ms = int(now_ms) + cycle
            admission_result = asyncio.run(admission.run_once(now_ms=cycle_now_ms))
            cleanup = _cleanup_narrative_backlog(
                db,
                window=window,
                scope=scope,
                now_ms=cycle_now_ms,
                realtime_windows=tuple(getattr(settings.workers.token_discussion_digest, "windows", ("1h",))),
                realtime_scopes=tuple(getattr(settings.workers.token_discussion_digest, "scopes", ("all",))),
            )
            _merge_int_counts(cleanup_totals, cleanup)
            semantics_result = asyncio.run(semantics.run_once(now_ms=cycle_now_ms))
            digest_result = asyncio.run(digest.run_once(now_ms=cycle_now_ms))
            item = {
                "cycle": cycle + 1,
                "narrative_admission": _worker_result_payload(admission_result),
                "cleanup": cleanup,
                "mention_semantics": _worker_result_payload(semantics_result),
                "token_discussion_digest": _worker_result_payload(digest_result),
            }
            results.append(item)
            if not drain:
                break
            if admission_result.skipped and semantics_result.skipped and digest_result.skipped:
                break
        final_health = _narrative_backlog_health(
            db,
            now_ms=int(now_ms) + len(results),
            since_hours=4,
            worker_settings=settings.workers,
        )
        return {
            "window": window,
            "scope": scope,
            "drain": bool(drain),
            "cycles": len(results),
            "cleanup": cleanup_totals,
            "final_health": final_health,
            "results": results,
        }
    finally:
        for lock in reversed(locks):
            _release_advisory_lock_connection(lock)
        for worker in reversed(workers):
            asyncio.run(worker.aclose())
        _cleanup_provider_roots_sync(provider_resource, agent_execution_gateway, llm_gateway)
        if db is not None:
            _close_db_bundle(db)


def _worker_result_payload(result: object) -> dict[str, Any]:
    return {
        "processed": int(getattr(result, "processed", 0) or 0),
        "failed": int(getattr(result, "failed", 0) or 0),
        "dead": int(getattr(result, "dead", 0) or 0),
        "skipped": int(getattr(result, "skipped", 0) or 0),
        "notes": dict(getattr(result, "notes", {}) or {}),
    }


def _cleanup_narrative_backlog(
    db: object,
    *,
    window: str,
    scope: str,
    now_ms: int,
    realtime_windows: tuple[str, ...] = ("1h",),
    realtime_scopes: tuple[str, ...] = ("all",),
) -> dict[str, int]:
    with db.worker_session("rebuild_narrative_intel_cleanup") as repos:
        return dict(
            _call_with_supported_kwargs(
                repos.narratives.cleanup_narrative_current_hard_cut,
                schema_version=NARRATIVE_SCHEMA_VERSION,
                window=window,
                scope=scope,
                now_ms=now_ms,
                realtime_windows=realtime_windows,
                realtime_scopes=realtime_scopes,
            )
        )


def _narrative_backlog_health(
    db: object,
    *,
    now_ms: int,
    since_hours: int,
    worker_settings: object = None,
) -> dict[str, Any]:
    with db.worker_session("rebuild_narrative_intel_final_health") as repos:
        return dict(
            NarrativeBacklogHealthQuery(
                repos.conn,
                **_narrative_health_worker_kwargs(worker_settings),
            ).health(now_ms=now_ms, since_hours=since_hours)
        )


def _merge_int_counts(total: dict[str, int], item: dict[str, Any]) -> None:
    for key, value in item.items():
        try:
            total[key] = total.get(key, 0) + int(value or 0)
        except (TypeError, ValueError):
            continue


def _call_with_supported_kwargs(method: object, **kwargs: object) -> object:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(**kwargs)  # type: ignore[misc]
    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return method(**kwargs)  # type: ignore[misc]
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return method(**supported)  # type: ignore[misc]


def _narrative_health_worker_kwargs(workers: object) -> dict[str, Any]:
    mention = getattr(workers, "mention_semantics", None)
    digest = getattr(workers, "token_discussion_digest", None)
    return {
        "realtime_windows": tuple(getattr(digest, "windows", ("1h",)) or ("1h",)),
        "realtime_scopes": tuple(getattr(digest, "scopes", ("all",)) or ("all",)),
        "semantics_rows_per_cycle": min(
            _positive_int(getattr(mention, "batch_size", 10), default=10),
            _positive_int(getattr(mention, "provider_batch_size", 10), default=10),
        ),
        "semantics_interval_seconds": _nonnegative_int(getattr(mention, "interval_seconds", 60), default=60),
        "digest_calls_per_cycle": max(
            1,
            _nonnegative_int(getattr(digest, "max_llm_calls_per_cycle", 3), default=3),
        ),
        "digest_interval_seconds": _nonnegative_int(getattr(digest, "interval_seconds", 120), default=120),
    }


def _positive_int(value: object, *, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def _nonnegative_int(value: object, *, default: int) -> int:
    try:
        return max(0, int(value if value is not None else default))
    except (TypeError, ValueError):
        return default


def _worker_settings_with_overrides(config: object, **overrides: object) -> SimpleNamespace:
    dump = getattr(config, "model_dump", None)
    values = dict(dump()) if dump is not None else dict(vars(config))
    values.update(overrides)
    return SimpleNamespace(**values)


def _close_db_bundle(db: object) -> None:
    for name in ("api_pool", "worker_pool", "lock_pool", "tool_pool", "wake_pool"):
        pool = getattr(db, name, None)
        close = getattr(pool, "close", None)
        if close:
            close()


def _release_advisory_lock_connection(connection: object) -> None:
    release = getattr(connection, "release", None)
    close = getattr(connection, "close", None)
    releaser = release or close
    if releaser is not None:
        releaser()


def _close_runtime_resource(resource: object) -> None:
    close = getattr(resource, "close", None)
    aclose = getattr(resource, "aclose", None)
    if close is not None:
        close()
    elif aclose is not None:
        asyncio.run(aclose())


def _effective_worker_advisory_lock_key(worker: object) -> int:
    resolve = getattr(worker, "_advisory_lock_key", None)
    key = resolve() if callable(resolve) else getattr(worker, "SINGLE_WRITER_KEY", None)
    if key is None:
        raise RuntimeError(f"{getattr(worker, 'name', worker.__class__.__name__)} advisory lock key is required")
    return int(key)


def _close_asset_market_providers(asset_market: object) -> None:
    seen: set[int] = set()
    for name in (
        "cex_market",
        "dex_discovery_market",
        "dex_quote_market",
        "dex_candle_market",
        "stream_dex_market",
    ):
        provider = getattr(asset_market, name, None)
        if provider is None or id(provider) in seen:
            continue
        seen.add(id(provider))
        close = getattr(provider, "close", None)
        if close:
            close()
    for source in tuple(getattr(asset_market, "dex_profile_sources", ()) or ()):
        provider = getattr(source, "market", None)
        if provider is None or id(provider) in seen:
            continue
        seen.add(id(provider))
        close = getattr(provider, "close", None)
        if close:
            close()


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
        limit=limit,
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
    )
    source_current_window_rows = _token_radar_source_count(
        repos.conn,
        since_ms=now_ms - WINDOW_MS[window],
        scope=scope,
    )
    source_max_resolution_ms = _token_radar_max_resolution_ms(repos.conn)
    source_max_market_tick_observed_at_ms = _token_radar_max_market_tick_observed_at_ms(repos.conn)
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


def _token_radar_source_count(conn: object, *, since_ms: int, scope: str) -> int:
    watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM token_intents
        JOIN token_intent_resolutions
          ON token_intent_resolutions.intent_id = token_intents.intent_id
         AND token_intent_resolutions.is_current = true
         AND token_intent_resolutions.resolver_policy_version = %s
         AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
         AND token_intent_resolutions.target_id IS NOT NULL
        JOIN events ON events.event_id = token_intents.event_id
        WHERE events.received_at_ms >= %s {watched_clause}
        """,
        (TOKEN_RADAR_RESOLVER_POLICY_VERSION, int(since_ms)),
    ).fetchone()
    return int(row["value"] or 0) if row else 0


def _token_radar_max_resolution_ms(conn: object) -> int | None:
    row = conn.execute(
        """
        SELECT MAX(decision_time_ms) AS value
        FROM token_intent_resolutions
        WHERE is_current = true
          AND target_type IN ('Asset', 'CexToken')
          AND target_id IS NOT NULL
        """
    ).fetchone()
    value = row["value"] if row else None
    return int(value) if value is not None else None


def _token_radar_max_market_tick_observed_at_ms(conn: object) -> int | None:
    row = conn.execute("SELECT MAX(tick_observed_at_ms) AS value FROM market_tick_current").fetchone()
    value = row["value"] if row else None
    return int(value) if value is not None else None


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
        for field in ("attention_json", "market_json", "price_json", "score_json"):
            payload = row.get(field) if isinstance(row.get(field), dict) else {}
            if payload:
                violations.append({"row": index, "code": "legacy_runtime_payload", "field": field})
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
