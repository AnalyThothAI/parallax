from __future__ import annotations

import argparse
import json
import secrets
import sys
from contextlib import contextmanager
from typing import TextIO

import uvicorn

from gmgn_twitter_intel.app.runtime.app import create_app
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.integrations.gmgn.directory_client import GmgnDirectoryClient, GmgnDirectoryError
from gmgn_twitter_intel.integrations.okx.cex_client import OkxCexClient
from gmgn_twitter_intel.integrations.okx.dex_client import OkxDexClient
from gmgn_twitter_intel.pipeline.asset_market_sync import sync_okx_cex_universe
from gmgn_twitter_intel.pipeline.harness_ops import (
    attribute_harness_credits,
    settle_harness_snapshots,
    update_harness_weights,
)
from gmgn_twitter_intel.pipeline.token_discovery_worker import run_token_discovery_once
from gmgn_twitter_intel.pipeline.token_intent_rebuild import rebuild_recent_token_intents
from gmgn_twitter_intel.pipeline.token_radar_contract import (
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_REQUIRED_ATTENTION_FIELDS,
    TOKEN_RADAR_REQUIRED_HEAT_HEALTH_FIELDS,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    TOKEN_RADAR_SCORE_COMPONENTS,
)
from gmgn_twitter_intel.pipeline.token_radar_projection import WINDOW_MS, TokenRadarProjection
from gmgn_twitter_intel.pipeline.token_resolution_refresh import (
    rebuild_token_radar_windows,
    reprocess_recent_token_intents,
)
from gmgn_twitter_intel.platform.config.settings import load_settings, write_default_config
from gmgn_twitter_intel.platform.db.postgres_audit import (
    PostgresOperationalAudit,
    PostgresQueryAudit,
    ProjectionValidationAudit,
)
from gmgn_twitter_intel.platform.db.postgres_client import (
    connect_postgres,
    local_docker_host_dsn,
    postgres_health_check,
    with_password_from_file,
)
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version, upgrade_head
from gmgn_twitter_intel.platform.logging.setup import setup_logging
from gmgn_twitter_intel.platform.paths.runtime_paths import config_path
from gmgn_twitter_intel.retrieval.account_alert_service import AccountAlertService
from gmgn_twitter_intel.retrieval.account_quality_service import AccountQualityService
from gmgn_twitter_intel.retrieval.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.retrieval.asset_search_service import AssetSearchService
from gmgn_twitter_intel.retrieval.harness_service import HarnessService
from gmgn_twitter_intel.storage.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.storage.projection_repository import ProjectionRepository


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

    enrichment_jobs = subcommands.add_parser("enrichment-jobs", help="inspect social-event extraction job backlog")
    enrichment_jobs.add_argument("--status", choices=("pending", "running", "failed", "dead", "done"), default=None)
    enrichment_jobs.add_argument("--limit", type=int, default=50)

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
    ops_subcommands.add_parser("projection-status", help="print projection offsets and latest runs")
    validate_projections = ops_subcommands.add_parser(
        "validate-projections",
        help="validate projection read models against PostgreSQL facts",
    )
    validate_projections.add_argument("--sample", type=int, default=100)
    sync_okx_cex = ops_subcommands.add_parser("sync-okx-cex-universe", help="sync OKX public CEX instruments")
    sync_okx_cex.add_argument("--inst-type", action="append", choices=("SPOT", "SWAP"), default=[])
    sync_gmgn_directory = ops_subcommands.add_parser(
        "sync-gmgn-directory",
        help="one-shot sync of GMGN twitter directory into account_profiles",
    )
    sync_gmgn_directory.add_argument("--max-pages", type=int, default=200)
    run_token_discovery = ops_subcommands.add_parser(
        "run-token-discovery",
        help="refresh due token discovery results and reprocess recent intents",
    )
    run_token_discovery.add_argument("--limit", type=int, default=50)
    run_token_discovery.add_argument("--reprocess-limit", type=int, default=500)
    reprocess_token_intents = ops_subcommands.add_parser(
        "reprocess-token-intents",
        help="re-resolve recent unresolved token intents and rebuild token radar",
    )
    reprocess_token_intents.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    reprocess_token_intents.add_argument("--limit", type=int, default=500)
    reprocess_token_intents.add_argument("--projection-limit", type=int, default=100)
    reprocess_token_intents.add_argument("--lookup-key", action="append", default=[])
    rebuild_token_intents = ops_subcommands.add_parser(
        "rebuild-token-intents",
        help="rebuild recent token evidence, intents, resolutions, lookup keys, and token radar",
    )
    rebuild_token_intents.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    rebuild_token_intents.add_argument("--limit", type=int, default=500)
    rebuild_token_intents.add_argument("--projection-limit", type=int, default=100)
    audit_token_intent = ops_subcommands.add_parser(
        "audit-token-intent",
        help="inspect token intent evidence and resolution",
    )
    audit_token_intent.add_argument("--event-id", default="")
    audit_token_intent.add_argument("--intent-id", default="")
    rebuild_token_radar = ops_subcommands.add_parser(
        "rebuild-token-radar",
        help="write the current token radar read model",
    )
    rebuild_token_radar.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    rebuild_token_radar.add_argument("--limit", type=int, default=50)
    rebuild_token_radar.add_argument("--scope", choices=("all", "matched"), default="all")
    audit_token_radar = ops_subcommands.add_parser(
        "audit-token-radar",
        help="audit token radar rows for scoring and market-readiness regressions",
    )
    audit_token_radar.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="5m")
    audit_token_radar.add_argument("--limit", type=int, default=100)
    audit_token_radar.add_argument("--scope", choices=("all", "matched"), default="all")
    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    command = args.command or "serve"

    if command == "init":
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
                        "concurrency": settings.enrichment_concurrency,
                        "backend": "openai_agents_sdk",
                        "trace_enabled": settings.llm_trace_enabled,
                        "trace_export_configured": settings.llm_trace_export_configured,
                        "trace_include_sensitive_data": settings.llm_trace_include_sensitive_data,
                    },
                    "providers": {
                        "okx": {
                            "cex_base_url": settings.okx_cex_base_url,
                            "cex_sync_enabled": settings.okx_cex_sync_enabled,
                            "cex_sync_interval_seconds": settings.okx_cex_sync_interval_seconds,
                            "cex_inst_types": list(settings.okx_cex_inst_types),
                            "dex_base_url": settings.okx_dex_base_url,
                            "dex_chain_indexes": list(settings.okx_dex_chain_indexes),
                            "dex_configured": settings.okx_dex_configured,
                        }
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
        dsn = local_docker_host_dsn(with_password_from_file(settings.postgres_dsn, settings.postgres_password_file))
        upgrade_head(dsn)
        _emit({"ok": True, "data": {"migration": "head"}}, stdout)
        return 0
    if command == "db" and args.db_command == "health":
        with _postgres_connection(settings) as conn:
            health = postgres_health_check(conn, expected_migration_version=latest_migration_version())
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
        evidence = repos.evidence
        signals = repos.signals
        assets = repos.assets
        enrichment = repos.enrichment
        harness = repos.harness
        notifications = repos.notifications
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
            data = AssetFlowService(token_radar=repos.token_radar).asset_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
            )
            _emit({"ok": True, "data": {"window": args.window, "scope": args.scope, **data}}, stdout)
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
                    registry=repos.registry,
                    price_observations=repos.price_observations,
                    client=client,
                    inst_types=inst_types,
                    observed_at_ms=_now_ms(),
                )
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "sync-gmgn-directory":
            client = GmgnDirectoryClient()
            try:
                data = _run_sync_gmgn_directory(
                    client=client,
                    repository=AccountQualityRepository(signals.conn),
                    now_ms=_now_ms(),
                    max_pages=args.max_pages,
                )
            except GmgnDirectoryError as exc:
                _emit({"ok": False, "error": str(exc)}, stdout)
                return 1
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "run-token-discovery":
            client = OkxDexClient(
                base_url=settings.okx_dex_base_url,
                api_key=settings.okx_dex_api_key,
                secret_key=settings.okx_dex_secret_key,
                passphrase=settings.okx_dex_passphrase,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            try:
                data = run_token_discovery_once(
                    repos=repos,
                    dex_client=client,
                    chain_indexes=settings.okx_dex_chain_indexes,
                    now_ms=_now_ms(),
                    lookup_limit=args.limit,
                    reprocess_limit=args.reprocess_limit,
                )
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "reprocess-token-intents":
            now_ms = _now_ms()
            reprocess = reprocess_recent_token_intents(
                repos=repos,
                now_ms=now_ms,
                window=args.window,
                limit=args.limit,
                lookup_keys=args.lookup_key or None,
            )
            projection = rebuild_token_radar_windows(
                repos=repos,
                now_ms=now_ms,
                limit=args.projection_limit,
            )
            _emit({"ok": True, "data": {"reprocess": reprocess, "projection": projection}}, stdout)
            return 0

        if command == "ops" and args.ops_command == "rebuild-token-intents":
            data = rebuild_recent_token_intents(
                repos=repos,
                now_ms=_now_ms(),
                window=args.window,
                limit=args.limit,
                projection_limit=args.projection_limit,
            )
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "audit-token-intent":
            if not args.event_id and not args.intent_id:
                parser.error("audit-token-intent requires --event-id or --intent-id")
            data = _audit_token_intent(repos, event_id=args.event_id or None, intent_id=args.intent_id or None)
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "rebuild-token-radar":
            data = TokenRadarProjection(repos=repos).rebuild(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
            )
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "audit-token-radar":
            data = _audit_token_radar(
                repos,
                window=args.window,
                scope=args.scope,
                limit=args.limit,
                now_ms=_now_ms(),
            )
            _emit({"ok": data["ok"], "data": data}, stdout)
            return 0 if data["ok"] else 1

    parser.error(f"unknown command: {command}")
    return 2


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
        yield repositories_for_connection(conn)


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
        if args.chain:
            return f"{args.chain.strip()}:{args.ca}"
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


def _audit_token_intent(repos, *, event_id: str | None, intent_id: str | None) -> dict:
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


def _audit_token_radar(repos, *, window: str, scope: str, limit: int, now_ms: int) -> dict:
    rows = repos.token_radar.latest_rows(
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
    source_max_resolution_ms = _max_scalar(
        repos.conn,
        "SELECT MAX(decision_time_ms) AS value FROM token_intent_resolutions WHERE is_current = true",
    )
    source_max_price_observed_at_ms = _max_scalar(
        repos.conn,
        "SELECT MAX(observed_at_ms) AS value FROM price_observations",
    )
    return {
        "window": window,
        "scope": scope,
        "limit": limit,
        **_audit_token_radar_rows(
            rows,
            now_ms=now_ms,
            source_current_window_rows=source_current_window_rows,
            source_max_resolution_ms=source_max_resolution_ms,
            source_max_price_observed_at_ms=source_max_price_observed_at_ms,
        ),
    }


def _audit_token_radar_rows(
    rows: list[dict],
    *,
    now_ms: int,
    source_current_window_rows: int,
    source_max_resolution_ms: int | None,
    source_max_price_observed_at_ms: int | None,
) -> dict:
    violations: list[dict] = []
    required = set(TOKEN_RADAR_SCORE_COMPONENTS)
    if not rows and source_current_window_rows:
        violations.append({"code": "empty_projection_rows"})
    for index, row in enumerate(rows):
        projection_version = row.get("projection_version")
        if projection_version != TOKEN_RADAR_PROJECTION_VERSION:
            violations.append({"row": index, "code": "wrong_projection_version", "value": projection_version})
        attention = row.get("attention_json") if isinstance(row.get("attention_json"), dict) else {}
        missing_attention = sorted(set(TOKEN_RADAR_REQUIRED_ATTENTION_FIELDS) - set(attention))
        if missing_attention:
            violations.append({"row": index, "code": "missing_attention_fields", "fields": missing_attention})
        score = row.get("score_json") if isinstance(row.get("score_json"), dict) else {}
        if "price_health" in score:
            violations.append({"row": index, "code": "legacy_price_health"})
        missing = sorted(required - set(score))
        if missing:
            violations.append({"row": index, "code": "missing_score_components", "components": missing})
        for component in sorted(required & set(score)):
            block = score.get(component) if isinstance(score.get(component), dict) else {}
            if not block.get("score_version"):
                violations.append({"row": index, "component": component, "code": "missing_score_version"})
            if not block.get("contributions"):
                violations.append({"row": index, "component": component, "code": "empty_contributions"})
            data_health = block.get("data_health") if isinstance(block.get("data_health"), dict) else {}
            if not data_health:
                violations.append({"row": index, "component": component, "code": "missing_data_health"})
            if component == "heat":
                missing_heat_health = sorted(set(TOKEN_RADAR_REQUIRED_HEAT_HEALTH_FIELDS) - set(data_health))
                if missing_heat_health:
                    violations.append(
                        {
                            "row": index,
                            "component": component,
                            "code": "missing_heat_data_health_fields",
                            "fields": missing_heat_health,
                        }
                    )
                if (
                    "baseline_status" in attention
                    and "baseline_status" in data_health
                    and attention["baseline_status"] != data_health["baseline_status"]
                ):
                    violations.append(
                        {
                            "row": index,
                            "component": component,
                            "code": "baseline_status_mismatch",
                            "attention": attention["baseline_status"],
                            "score": data_health["baseline_status"],
                        }
                    )
        market = row.get("market_json") if isinstance(row.get("market_json"), dict) else {}
        if row.get("decision") == "driver" and str(market.get("market_observation_status") or "") != "ready":
            violations.append({"row": index, "code": "driver_without_ready_market"})
    social_lag_ms = max(0, int(now_ms) - int(source_max_resolution_ms)) if source_max_resolution_ms else None
    market_lag_ms = (
        max(0, int(now_ms) - int(source_max_price_observed_at_ms))
        if source_max_price_observed_at_ms
        else None
    )
    return {
        "ok": not violations,
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "row_count": len(rows),
        "violations": violations,
        "source_current_window_rows": source_current_window_rows,
        "source_max_resolution_ms": source_max_resolution_ms,
        "source_max_price_observed_at_ms": source_max_price_observed_at_ms,
        "social_lag_ms": social_lag_ms,
        "market_lag_ms": market_lag_ms,
    }


def _token_radar_source_count(conn, *, since_ms: int, scope: str) -> int:
    watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM token_intents
        JOIN token_intent_resolutions
          ON token_intent_resolutions.intent_id = token_intents.intent_id
         AND token_intent_resolutions.is_current = true
         AND token_intent_resolutions.resolver_policy_version = %s
        JOIN events ON events.event_id = token_intents.event_id
        WHERE events.received_at_ms >= %s {watched_clause}
        """,
        (TOKEN_RADAR_RESOLVER_POLICY_VERSION, since_ms),
    ).fetchone()
    return int(row["value"] or 0) if row else 0


def _max_scalar(conn, sql: str) -> int | None:
    row = conn.execute(sql).fetchone()
    value = row["value"] if row else None
    return int(value) if value is not None else None


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
