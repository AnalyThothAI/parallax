from __future__ import annotations

import argparse
import json
import secrets
import sys
from contextlib import contextmanager
from typing import TextIO

import uvicorn

from .api.app import create_app
from .logging_setup import setup_logging
from .market.okx_cex_client import OkxCexClient
from .market.okx_dex_client import OkxDexClient
from .pipeline.asset_market_sync import sync_okx_cex_universe
from .pipeline.asset_resolution_worker import AssetResolutionWorker
from .pipeline.harness_ops import attribute_harness_credits, settle_harness_snapshots, update_harness_weights
from .pipeline.token_signal_settlement import settle_token_signal_snapshots
from .retrieval.account_alert_service import AccountAlertService
from .retrieval.account_quality_service import AccountQualityService
from .retrieval.asset_flow_service import AssetFlowService
from .retrieval.asset_search_service import AssetSearchService
from .retrieval.harness_service import HarnessService
from .retrieval.token_signal_evaluation_service import TokenSignalEvaluationService
from .settings import load_settings, write_default_config
from .storage.account_quality_repository import AccountQualityRepository
from .storage.asset_repository import AssetRepository
from .storage.enrichment_repository import EnrichmentRepository
from .storage.entity_repository import EntityRepository
from .storage.evidence_repository import EvidenceRepository
from .storage.harness_repository import HarnessRepository
from .storage.market_observation_repository import MarketObservationRepository
from .storage.notification_repository import NotificationRepository
from .storage.postgres_audit import PostgresOperationalAudit, PostgresQueryAudit, ProjectionValidationAudit
from .storage.postgres_client import connect_postgres, postgres_health_check, with_password_from_file
from .storage.postgres_migrations import upgrade_head
from .storage.projection_repository import ProjectionRepository
from .storage.signal_repository import SignalRepository
from .storage.token_repository import TokenRepository
from .storage.token_signal_repository import TokenSignalRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-intel")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("serve", help="run the collector service")

    init = subcommands.add_parser("init", help="create ~/.gmgn-twitter-intel/config.yaml")
    init.add_argument("--force", action="store_true", help="overwrite existing config.yaml")

    subcommands.add_parser("config", help="print effective runtime configuration")

    db = subcommands.add_parser("db", help="database lifecycle commands")
    db_subcommands = db.add_subparsers(dest="db_command", required=True)
    db_subcommands.add_parser("migrate", help="apply PostgreSQL migrations")
    db_subcommands.add_parser("health", help="check PostgreSQL liveness and migration version")
    db_subcommands.add_parser("audit", help="run PostgreSQL count, FK, and projection schema audit")
    query_audit = db_subcommands.add_parser("query-audit", help="explain PostgreSQL hot read paths")
    query_audit.add_argument("--analyze", action="store_true", help="run EXPLAIN ANALYZE with buffers")

    recent = subcommands.add_parser("recent", help="print recent stored events")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--handles", default="")
    recent.add_argument("--ca", default="", help="filter by token contract address")
    recent.add_argument("--chain", default="", help="chain for contract address filters")
    recent.add_argument("--symbol", default="", help="filter by cashtag symbol")
    recent.add_argument("--scope", choices=("all", "matched"), default="matched")

    search = subcommands.add_parser("search", help="search stored tweets by CA, symbol, handle, or text")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--symbol", default="", help="search by token symbol without shell cashtag escaping")
    search.add_argument("--ca", default="", help="search by token contract address")
    search.add_argument("--chain", default="", help="chain for --ca")
    search.add_argument("--handle", default="", help="search by Twitter handle")
    search.add_argument("--scope", choices=("all", "matched"), default="all")

    asset_flow = subcommands.add_parser("asset-flow", help="rank resolved assets and unresolved attention candidates")
    asset_flow.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    asset_flow.add_argument("--limit", type=int, default=20)
    asset_flow.add_argument("--scope", choices=("all", "matched"), default="all")

    token_signal_snapshots = subcommands.add_parser(
        "token-signal-snapshots",
        help="print frozen token signal snapshots",
    )
    token_signal_snapshots.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="")
    token_signal_snapshots.add_argument("--limit", type=int, default=50)
    token_signal_snapshots.add_argument("--scope", choices=("all", "matched"), default="")
    token_signal_snapshots.add_argument("--token-id", default="")

    token_signal_outcomes = subcommands.add_parser("token-signal-outcomes", help="print token signal outcomes")
    token_signal_outcomes.add_argument("--horizon", choices=("6h", "24h"), default="")
    token_signal_outcomes.add_argument("--status", default="")
    token_signal_outcomes.add_argument("--limit", type=int, default=50)

    token_signal_evaluations = subcommands.add_parser(
        "token-signal-evaluations",
        help="evaluate frozen token signal score buckets",
    )
    token_signal_evaluations.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    token_signal_evaluations.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="5m")
    token_signal_evaluations.add_argument("--scope", choices=("all", "matched"), default="all")

    account_alerts = subcommands.add_parser("account-alerts", help="print watched-account token alerts")
    account_alerts.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    account_alerts.add_argument("--limit", type=int, default=50)
    account_alerts.add_argument("--handles", default="")
    account_alerts.add_argument(
        "--alert-type",
        choices=("account_token", "token"),
        default=None,
    )

    account_quality = subcommands.add_parser("account-quality", help="print account quality profiles")
    account_quality.add_argument("--handles", default="", help="comma separated account handles")

    social_events = subcommands.add_parser("social-events", help="print harness social event read model")
    social_events.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    social_events.add_argument("--limit", type=int, default=50)
    social_events.add_argument("--handles", default="")
    social_events.add_argument("--event-types", default="")

    attention_seeds = subcommands.add_parser("attention-seeds", help="print harness attention seeds")
    attention_seeds.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    attention_seeds.add_argument("--limit", type=int, default=50)
    attention_seeds.add_argument("--handles", default="")

    harness_snapshots = subcommands.add_parser("harness-snapshots", help="print harness snapshots")
    harness_snapshots.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    harness_snapshots.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    harness_snapshots.add_argument("--limit", type=int, default=50)
    harness_snapshots.add_argument("--asset", default="")

    harness_outcomes = subcommands.add_parser("harness-outcomes", help="print harness outcomes")
    harness_outcomes.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    harness_outcomes.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    harness_outcomes.add_argument("--limit", type=int, default=50)
    harness_outcomes.add_argument("--asset", default="")

    harness_credits = subcommands.add_parser("harness-credits", help="print harness credits")
    harness_credits.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    harness_credits.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    harness_credits.add_argument("--limit", type=int, default=80)
    harness_credits.add_argument("--asset", default="")

    harness_weights = subcommands.add_parser("harness-weights", help="print harness weights")
    harness_weights.add_argument("--horizon", choices=("6h", "24h"), default="")
    harness_weights.add_argument("--limit", type=int, default=100)

    harness_score_buckets = subcommands.add_parser("harness-score-buckets", help="print harness score bucket report")
    harness_score_buckets.add_argument("--horizon", choices=("6h", "24h"), default="")

    subcommands.add_parser("harness-health", help="print harness health summary")

    enrichment_jobs = subcommands.add_parser("enrichment-jobs", help="inspect LLM enrichment job backlog")
    enrichment_jobs.add_argument("--status", choices=("pending", "running", "failed", "dead", "done"), default=None)
    enrichment_jobs.add_argument("--limit", type=int, default=50)

    market_observations = subcommands.add_parser("market-observations", help="inspect token market observation backlog")
    market_observations.add_argument(
        "--status",
        choices=(
            "pending",
            "running",
            "ready",
            "cached",
            "provider_not_configured",
            "provider_not_found",
            "provider_error",
            "rate_limited",
            "dead",
        ),
        default=None,
    )
    market_observations.add_argument("--limit", type=int, default=50)

    notification_deliveries = subcommands.add_parser(
        "notification-deliveries",
        help="inspect notification external delivery audit rows",
    )
    notification_deliveries.add_argument(
        "--status",
        choices=("pending", "running", "failed", "dead", "delivered"),
        default=None,
    )
    notification_deliveries.add_argument("--limit", type=int, default=50)

    ops = subcommands.add_parser("ops", help="maintenance commands")
    ops_subcommands = ops.add_subparsers(dest="ops_command", required=True)
    backfill_account_quality = ops_subcommands.add_parser(
        "backfill-account-quality",
        help="backfill account token-call stats and quality snapshots",
    )
    backfill_account_quality.add_argument("--limit", type=int, default=1000)
    backfill_market_observations = ops_subcommands.add_parser(
        "backfill-market-observations",
        help="enqueue missing market observations for existing direct/selected token attributions",
    )
    backfill_market_observations.add_argument("--limit", type=int, default=1000)
    backfill_harness_jobs = ops_subcommands.add_parser(
        "backfill-harness-jobs",
        help="enqueue social-event-v2 extraction jobs for existing watched events",
    )
    backfill_harness_jobs.add_argument("--limit", type=int, default=1000)
    settle_harness = ops_subcommands.add_parser(
        "settle-harness",
        help="settle due harness snapshots from local market snapshots",
    )
    settle_harness.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    settle_harness.add_argument("--limit", type=int, default=100)
    settle_harness.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)
    attribute_harness = ops_subcommands.add_parser(
        "attribute-harness-credits",
        help="assign event credit for settled harness snapshots",
    )
    attribute_harness.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    attribute_harness.add_argument("--limit", type=int, default=100)
    update_weights = ops_subcommands.add_parser("update-harness-weights", help="rebuild report-only harness weights")
    update_weights.add_argument("--limit", type=int, default=1000)
    settle_token_signals = ops_subcommands.add_parser(
        "settle-token-signals",
        help="settle due frozen token signal snapshots",
    )
    settle_token_signals.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    settle_token_signals.add_argument("--limit", type=int, default=500)
    ops_subcommands.add_parser("projection-status", help="print projection offsets and latest runs")
    validate_projections = ops_subcommands.add_parser(
        "validate-projections",
        help="validate projection read models against PostgreSQL facts",
    )
    validate_projections.add_argument("--sample", type=int, default=100)
    sync_okx_cex = ops_subcommands.add_parser("sync-okx-cex-universe", help="sync OKX public CEX instruments")
    sync_okx_cex.add_argument("--inst-type", action="append", choices=("SPOT", "SWAP"), default=[])
    process_asset_resolution = ops_subcommands.add_parser(
        "process-asset-resolution-jobs",
        help="claim and process queued OKX DEX asset-resolution jobs",
    )
    process_asset_resolution.add_argument("--limit", type=int, default=50)
    resolve_asset_symbol = ops_subcommands.add_parser("resolve-asset-symbol", help="resolve or queue an asset symbol")
    resolve_asset_symbol.add_argument("--symbol", required=True)
    asset_resolution_health = ops_subcommands.add_parser(
        "asset-resolution-health",
        help="inspect asset resolution health",
    )
    asset_resolution_health.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    audit_asset_attribution = ops_subcommands.add_parser("audit-asset-attribution", help="inspect asset attributions")
    audit_asset_attribution.add_argument("--event-id", required=True)
    rebuild_asset_flow = ops_subcommands.add_parser("rebuild-asset-flow", help="compute asset flow read model")
    rebuild_asset_flow.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    rebuild_asset_flow.add_argument("--limit", type=int, default=50)
    rebuild_asset_flow.add_argument("--scope", choices=("all", "matched"), default="all")
    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    command = args.command or "serve"

    if command == "init":
        from .runtime_paths import config_path

        existed = config_path().exists()
        path = write_default_config(force=args.force)
        password_path = _ensure_postgres_password_file(path.parent)
        _emit(
            {
                "ok": True,
                "data": {
                    "config_path": str(path),
                    "app_home": str(path.parent),
                    "postgres_password_file": str(password_path),
                    "created": args.force or not existed,
                },
            },
            stdout,
        )
        return 0

    if command == "serve":
        settings = load_settings()
        setup_logging(settings.log_file)
        uvicorn.run(
            create_app(settings=settings),
            host=settings.api_host,
            port=settings.api_port,
            log_config=None,
            ws_ping_interval=settings.ws_heartbeat_interval,
            ws_ping_timeout=settings.ws_heartbeat_interval * 2,
        )
        return 0

    if command == "config":
        settings = load_settings(require_ws_token=False)
        _emit(
            {
                "ok": True,
                "data": {
                    "handles": list(settings.handles),
                    "handle_count": len(settings.handles),
                    "config_path": str(settings.app_home / "config.yaml"),
                    "api": {
                        "host": settings.api_host,
                        "port": settings.api_port,
                        "replay_limit": settings.replay_limit,
                        "ws_token_configured": bool(settings.ws_token),
                    },
                    "store": {
                        "app_home": str(settings.app_home),
                        "engine": "postgresql",
                        "postgres_dsn": _redacted_postgres_dsn(settings.postgres_dsn),
                        "postgres_password_file": (
                            str(settings.postgres_password_file) if settings.postgres_password_file else None
                        ),
                        "pool_min_size": settings.postgres_pool_min_size,
                        "pool_max_size": settings.postgres_pool_max_size,
                        "log_file": str(settings.log_file),
                    },
                    "upstream": {
                        "channels": list(settings.upstream_channels),
                        "chains": list(settings.upstream_chains),
                    },
                    "enrichment": {
                        "llm_configured": settings.llm_configured,
                        "provider": settings.llm_provider,
                        "model": settings.llm_model,
                        "base_url": settings.llm_base_url,
                        "poll_interval": settings.enrichment_poll_interval,
                    },
                    "notifications": {
                        "enabled": settings.notifications.enabled,
                        "poll_interval_seconds": settings.notifications.poll_interval_seconds,
                        "token_flow_limit": settings.notifications.token_flow_limit,
                        "retention_days": settings.notifications.retention_days,
                        "rules": {
                            rule_id: rule.model_dump(mode="json")
                            for rule_id, rule in settings.notifications.rules.items()
                        },
                        "channels": {
                            channel_id: {
                                "enabled": channel.enabled,
                                "provider": channel.provider,
                                "url_configured": bool(channel.url),
                                "min_severity": channel.min_severity,
                                "max_attempts": channel.max_attempts,
                            }
                            for channel_id, channel in settings.notifications.channels.items()
                        },
                    },
                },
            },
            stdout,
        )
        return 0

    settings = load_settings(require_ws_token=False)
    if command == "db" and args.db_command == "migrate":
        upgrade_head(with_password_from_file(settings.postgres_dsn, settings.postgres_password_file))
        _emit({"ok": True, "data": {"migration": "head"}}, stdout)
        return 0
    if command == "db" and args.db_command == "health":
        with _postgres_connection(settings) as conn:
            health = postgres_health_check(conn)
        _emit({"ok": bool(health.get("ok")), "data": health}, stdout)
        return 0 if health.get("ok") else 1
    if command == "db" and args.db_command == "audit":
        with _postgres_connection(settings) as conn:
            audit = PostgresOperationalAudit(conn).run()
        _emit({"ok": bool(audit.get("ok")), "data": audit}, stdout)
        return 0 if audit.get("ok") else 1
    if command == "db" and args.db_command == "query-audit":
        with _postgres_connection(settings) as conn:
            audit = PostgresQueryAudit(conn).run(analyze=bool(args.analyze))
        _emit({"ok": bool(audit.get("ok")), "data": audit}, stdout)
        return 0 if audit.get("ok") else 1

    with _repositories(settings) as repos:
        (
            evidence,
            entities,
            signals,
            tokens,
            assets,
            market_observations,
            enrichment,
            harness,
            notifications,
            token_signals,
        ) = repos
        if command == "recent":
            handles = _handle_set(args.handles)
            events = evidence.recent_events(
                limit=args.limit,
                handles=handles,
                ca=args.ca or None,
                chain=args.chain or None,
                symbol=args.symbol or None,
                watched_only=args.scope == "matched",
            )
            _emit({"ok": True, "data": {"events": events}}, stdout)
            return 0

        if command == "search":
            query = _search_query(args)
            results = AssetSearchService(evidence=evidence, assets=assets).search(
                query,
                limit=args.limit,
                scope=args.scope,
            )
            _emit(
                {
                    "ok": results.ok,
                    "data": {
                        "query": results.query,
                        "total_count": results.total_count,
                        "returned_count": results.returned_count,
                        "has_more": results.has_more,
                        "resolution": results.resolution,
                        "candidates": results.candidates,
                        "items": results.items,
                    },
                    "error": results.error,
                },
                stdout,
            )
            return 0 if results.ok else 1

        if command == "asset-flow":
            data = AssetFlowService(assets=assets).asset_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
            )
            _emit({"ok": True, "data": {"window": args.window, "scope": args.scope, **data}}, stdout)
            return 0

        if command == "token-signal-snapshots":
            _emit(
                {
                    "ok": True,
                    "data": {
                        "items": token_signals.list_snapshots(
                            window=args.window or None,
                            scope=args.scope or None,
                            token_id=args.token_id or None,
                            limit=args.limit,
                        )
                    },
                },
                stdout,
            )
            return 0

        if command == "token-signal-outcomes":
            _emit(
                {
                    "ok": True,
                    "data": {
                        "items": token_signals.list_outcomes(
                            horizon=args.horizon or None,
                            status=args.status or None,
                            limit=args.limit,
                        )
                    },
                },
                stdout,
            )
            return 0

        if command == "token-signal-evaluations":
            _emit(
                {
                    "ok": True,
                    "data": TokenSignalEvaluationService(repository=token_signals).evaluate(
                        horizon=args.horizon,
                        window=args.window,
                        scope=args.scope,
                    ),
                },
                stdout,
            )
            return 0

        if command == "account-alerts":
            items = AccountAlertService(signals).account_alerts(
                window=args.window,
                limit=args.limit,
                handles=_handle_set(args.handles),
                alert_type=args.alert_type,
            )
            _emit({"ok": True, "data": {"window": args.window, "items": items}}, stdout)
            return 0

        if command == "account-quality":
            handles = sorted(_handle_set(args.handles))
            data = AccountQualityService(
                signals=signals,
                repository=AccountQualityRepository(signals.conn),
            ).account_quality_for_handles(handles)
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "social-events":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).social_events(
                        window=args.window,
                        limit=args.limit,
                        handles=_handle_set(args.handles),
                        event_types=_csv_set(args.event_types),
                    ),
                },
                stdout,
            )
            return 0

        if command == "attention-seeds":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).attention_seeds(
                        window=args.window,
                        limit=args.limit,
                        handles=_handle_set(args.handles),
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-snapshots":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).snapshots(
                        window=args.window,
                        horizon=args.horizon,
                        limit=args.limit,
                        asset=args.asset or None,
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-outcomes":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).outcomes(
                        window=args.window,
                        horizon=args.horizon,
                        limit=args.limit,
                        asset=args.asset or None,
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-credits":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).credits(
                        window=args.window,
                        horizon=args.horizon,
                        limit=args.limit,
                        asset=args.asset or None,
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-weights":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).weights(
                        horizon=args.horizon or None,
                        limit=args.limit,
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-health":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).health(
                        llm_configured=settings.llm_configured,
                        extractor_running=bool(settings.llm_configured),
                        pending_jobs=enrichment.job_counts().get("pending", 0),
                        schema_success_rate=None,
                    ),
                },
                stdout,
            )
            return 0

        if command == "harness-score-buckets":
            _emit(
                {
                    "ok": True,
                    "data": HarnessService(harness).score_buckets(horizon=args.horizon or None),
                },
                stdout,
            )
            return 0

        if command == "enrichment-jobs":
            items = enrichment.list_jobs(limit=args.limit, status=args.status)
            _emit(
                {
                    "ok": True,
                    "data": {
                        "items": items,
                        "counts": enrichment.job_counts(),
                    },
                },
                stdout,
            )
            return 0

        if command == "market-observations":
            _emit(
                {
                    "ok": True,
                    "data": {
                        "items": market_observations.list_observations(limit=args.limit, status=args.status),
                        "counts": market_observations.counts(),
                    },
                },
                stdout,
            )
            return 0

        if command == "notification-deliveries":
            _emit(
                {
                    "ok": True,
                    "data": {
                        "items": notifications.list_deliveries(limit=args.limit, status=args.status),
                    },
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "backfill-account-quality":
            data = AccountQualityService(
                signals=signals,
                repository=AccountQualityRepository(signals.conn),
            ).backfill_account_token_call_stats(limit=args.limit)
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "backfill-market-observations":
            rows = market_observations.pending_backfill_rows(limit=args.limit)
            enqueued = market_observations.enqueue_for_attributions(rows)
            _emit(
                {
                    "ok": True,
                    "data": {
                        "rows_scanned": len(rows),
                        "observations_enqueued": enqueued,
                        "counts": market_observations.counts(),
                    },
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "backfill-harness-jobs":
            _emit({"ok": True, "data": enrichment.enqueue_missing_watched_events(limit=args.limit)}, stdout)
            return 0

        if command == "ops" and args.ops_command == "settle-harness":
            _emit(
                {
                    "ok": True,
                    "data": settle_harness_snapshots(
                        harness=harness,
                        assets=assets,
                        horizon=args.horizon,
                        limit=args.limit,
                        now_ms=args.now_ms,
                    ),
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "attribute-harness-credits":
            _emit(
                {
                    "ok": True,
                    "data": attribute_harness_credits(
                        harness=harness,
                        horizon=args.horizon,
                        limit=args.limit,
                    ),
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "update-harness-weights":
            _emit(
                {
                    "ok": True,
                    "data": update_harness_weights(harness=harness, limit=args.limit),
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "settle-token-signals":
            _emit(
                {
                    "ok": True,
                    "data": settle_token_signal_snapshots(
                        repository=token_signals,
                        tokens=tokens,
                        horizon=args.horizon,
                        limit=args.limit,
                    ),
                },
                stdout,
            )
            return 0

        if command == "ops" and args.ops_command == "projection-status":
            _emit({"ok": True, "data": ProjectionRepository(signals.conn).status_summary()}, stdout)
            return 0

        if command == "ops" and args.ops_command == "validate-projections":
            data = ProjectionValidationAudit(signals.conn).run(sample=args.sample)
            _emit({"ok": bool(data.get("ok")), "data": data}, stdout)
            return 0 if data.get("ok") else 1

        if command == "ops" and args.ops_command == "sync-okx-cex-universe":
            inst_types = args.inst_type or ["SPOT", "SWAP"]
            client = OkxCexClient(
                base_url=settings.okx_cex_base_url,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            try:
                data = sync_okx_cex_universe(
                    assets=assets,
                    client=client,
                    inst_types=inst_types,
                    observed_at_ms=_now_ms(),
                )
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "process-asset-resolution-jobs":
            client = OkxDexClient(
                base_url=settings.okx_dex_base_url,
                api_key=settings.okx_dex_api_key,
                secret_key=settings.okx_dex_secret_key,
                passphrase=settings.okx_dex_passphrase,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            worker = AssetResolutionWorker(
                assets=assets,
                client=client,
                chain_indexes=settings.okx_dex_chain_indexes,
                poll_interval=0,
            )
            results = []
            try:
                for _ in range(max(0, int(args.limit))):
                    result = worker.process_one(now_ms=_now_ms())
                    results.append(result)
                    if not result.get("processed"):
                        break
            finally:
                worker.close()
            _emit({"ok": True, "data": {"items": results}}, stdout)
            return 0

        if command == "ops" and args.ops_command == "resolve-asset-symbol":
            symbol = args.symbol.strip().lstrip("$").upper()
            candidates = assets.candidates_for_symbol(symbol)
            if candidates:
                status = "resolved" if len({row["asset_id"] for row in candidates}) == 1 else "ambiguous"
            else:
                assets.upsert_unresolved_symbol(symbol, event_id=None, observed_at_ms=_now_ms(), commit=False)
                assets.queue_resolution_job(job_type="symbol_resolution", normalized_symbol=symbol, commit=False)
                assets.conn.commit()
                status = "queued"
                candidates = assets.candidates_for_symbol(symbol)
            _emit({"ok": True, "data": {"symbol": symbol, "status": status, "candidates": candidates}}, stdout)
            return 0

        if command == "ops" and args.ops_command == "asset-resolution-health":
            _emit({"ok": True, "data": _asset_resolution_health(assets.conn, window=args.window)}, stdout)
            return 0

        if command == "ops" and args.ops_command == "audit-asset-attribution":
            rows = assets.conn.execute(
                """
                SELECT asset_attributions.*, assets.canonical_symbol, assets.asset_type, asset_venues.venue_type,
                       asset_venues.exchange, asset_venues.chain, asset_venues.address, asset_venues.inst_id
                FROM asset_attributions
                JOIN assets ON assets.asset_id = asset_attributions.asset_id
                LEFT JOIN asset_venues ON asset_venues.venue_id = asset_attributions.venue_id
                WHERE asset_attributions.event_id = %s
                ORDER BY asset_attributions.created_at_ms DESC
                """,
                (args.event_id,),
            ).fetchall()
            _emit({"ok": True, "data": {"event_id": args.event_id, "items": [dict(row) for row in rows]}}, stdout)
            return 0

        if command == "ops" and args.ops_command == "rebuild-asset-flow":
            data = AssetFlowService(assets=assets).asset_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
            )
            _emit({"ok": True, "data": data}, stdout)
            return 0

    parser.error(f"unknown command: {command}")
    return 2


@contextmanager
def _postgres_connection(settings):
    dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
    conn = connect_postgres(dsn, connect_timeout_seconds=settings.postgres_connect_timeout_seconds)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _repositories(settings):
    with _postgres_connection(settings) as conn:
        yield (
            EvidenceRepository(conn),
            EntityRepository(conn),
            SignalRepository(conn),
            TokenRepository(conn),
            AssetRepository(conn),
            MarketObservationRepository(conn),
            EnrichmentRepository(conn),
            HarnessRepository(conn),
            NotificationRepository(conn),
            TokenSignalRepository(conn),
        )


def _emit(payload: dict, stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _ensure_postgres_password_file(app_home) -> object:
    path = app_home / "postgres_password"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        path.chmod(0o600)
    return path


def _redacted_postgres_dsn(dsn: str) -> str:
    from psycopg import conninfo

    try:
        parts = conninfo.conninfo_to_dict(dsn)
        if parts.get("password"):
            parts["password"] = "********"
        return conninfo.make_conninfo(**parts)
    except Exception:
        return dsn


def _search_query(args: argparse.Namespace) -> str:
    if args.ca:
        return args.ca
    if args.symbol:
        return f"${args.symbol.strip().lstrip('$')}"
    if args.handle:
        return f"@{args.handle.strip().lstrip('@')}"
    return args.query


def _handle_set(raw: str) -> set[str]:
    return {item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()}


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _asset_resolution_health(conn, *, window: str) -> dict:
    window_ms = {
        "5m": 5 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "24h": 24 * 60 * 60 * 1000,
    }[window]
    since_ms = _now_ms() - window_ms
    rows = conn.execute(
        """
        SELECT attribution_status, identity_status, COUNT(*) AS count
        FROM asset_attributions
        WHERE decision_time_ms >= %s
        GROUP BY attribution_status, identity_status
        ORDER BY count DESC
        """,
        (since_ms,),
    ).fetchall()
    top_unresolved = conn.execute(
        """
        SELECT assets.canonical_symbol AS symbol, COUNT(*) AS count
        FROM asset_attributions
        JOIN assets ON assets.asset_id = asset_attributions.asset_id
        WHERE asset_attributions.decision_time_ms >= %s
          AND asset_attributions.attribution_status IN ('unresolved', 'ambiguous')
        GROUP BY assets.canonical_symbol
        ORDER BY count DESC, assets.canonical_symbol ASC
        LIMIT 20
        """,
        (since_ms,),
    ).fetchall()
    return {
        "window": window,
        "status_counts": [dict(row) for row in rows],
        "top_unresolved": [dict(row) for row in top_unresolved],
    }


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
