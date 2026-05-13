from __future__ import annotations

import argparse
import json
import secrets
import sys
from contextlib import contextmanager
from decimal import Decimal
from typing import TextIO

import uvicorn

from gmgn_twitter_intel.app.runtime.app import create_app
from gmgn_twitter_intel.app.runtime.providers_wiring import (
    GmgnDexMarketProvider,
    OkxCexMarketProvider,
    OkxDexDiscoveryProvider,
    okx_chain_indexes_to_chain_ids,
    wire_providers,
)
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.account_quality.read_models.account_quality_service import AccountQualityService
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import run_resolution_refresh_once
from gmgn_twitter_intel.domains.asset_market.services.asset_market_sync import sync_cex_routes
from gmgn_twitter_intel.domains.asset_market.services.asset_profile_refresh import refresh_asset_profiles_once
from gmgn_twitter_intel.domains.asset_market.services.us_equity_symbol_sync import (
    NasdaqTraderSymbolClient,
    sync_us_equity_symbols,
)
from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessService
from gmgn_twitter_intel.domains.closed_loop_harness.services.harness_ops import (
    attribute_harness_credits,
    settle_harness_snapshots,
    update_harness_weights,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
    require_token_factor_snapshot,
)
from gmgn_twitter_intel.domains.token_intel.queries.search_events_query import SearchEventsQuery
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_source_query import TokenRadarSourceQuery
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.read_models.search_service import SearchCursorError, SearchService
from gmgn_twitter_intel.domains.token_intel.repositories.projection_repository import ProjectionRepository
from gmgn_twitter_intel.domains.token_intel.runtime.token_intent_rebuild import rebuild_recent_token_intents
from gmgn_twitter_intel.domains.token_intel.runtime.token_resolution_refresh import (
    rebuild_token_radar_windows,
    reprocess_recent_token_intents,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_diagnostics import factor_distribution_report
from gmgn_twitter_intel.domains.token_intel.services.token_factor_evaluation import settle_token_factor_scores
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import WINDOW_MS, TokenRadarProjection
from gmgn_twitter_intel.integrations.gmgn.directory_client import GmgnDirectoryClient, GmgnDirectoryError
from gmgn_twitter_intel.integrations.gmgn.openapi_client import GmgnOpenApiClient
from gmgn_twitter_intel.integrations.okx.cex_client import OkxCexClient
from gmgn_twitter_intel.integrations.okx.dex_client import OkxDexClient
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

LEGACY_FACTOR_GATE_KEY = "_".join(("hard", "gates"))
LEGACY_FACTOR_GATE_PRESENT_CODE = f"{LEGACY_FACTOR_GATE_KEY}_present"


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

    search = subcommands.add_parser("search", help="search stored tweets by query text")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--scope", choices=("all", "matched"), default="all")
    search.add_argument("--cursor", default="", help="opaque cursor returned by a prior search page")

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
    ops_subcommands.add_parser("sync-us-equity-symbols", help="sync Nasdaq Trader US equity symbols")
    sync_gmgn_directory = ops_subcommands.add_parser(
        "sync-gmgn-directory",
        help="one-shot sync of GMGN twitter directory into account_profiles",
    )
    sync_gmgn_directory.add_argument("--max-pages", type=int, default=200)
    run_resolution_refresh = ops_subcommands.add_parser(
        "run-resolution-refresh",
        help="refresh due token resolution lookups and reprocess recent intents",
    )
    run_resolution_refresh.add_argument("--limit", type=int, default=50)
    run_resolution_refresh.add_argument("--reprocess-limit", type=int, default=500)
    refresh_asset_profiles = ops_subcommands.add_parser(
        "refresh-asset-profiles",
        help="refresh due GMGN token profile facts",
    )
    refresh_asset_profiles.add_argument("--limit", type=int, default=50)
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
    backfill_price_baselines = ops_subcommands.add_parser(
        "backfill-token-price-baselines",
        help="backfill token radar event price baselines from message observations",
    )
    backfill_price_baselines.add_argument("--limit", type=int, default=1000)
    factor_diagnostics = ops_subcommands.add_parser(
        "factor-diagnostics",
        help="inspect token factor distribution health for latest radar rows",
    )
    factor_diagnostics.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    factor_diagnostics.add_argument("--scope", choices=("all", "matched"), default="all")
    factor_diagnostics.add_argument("--limit", type=int, default=200)
    settle_token_factors = ops_subcommands.add_parser(
        "settle-token-factors",
        help="settle token factor scores against later price observations",
    )
    settle_token_factors.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    settle_token_factors.add_argument("--scope", choices=("all", "matched"), default="all")
    settle_token_factors.add_argument("--horizon", choices=("15m", "1h", "6h", "24h"), default="1h")
    settle_token_factors.add_argument("--limit", type=int, default=1000)
    settle_token_factors.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)
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
            audit = PostgresQueryAudit(
                conn,
                token_radar_projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                token_factor_version=TOKEN_FACTOR_SNAPSHOT_VERSION,
            ).run(analyze=bool(args.analyze))
        _emit({"ok": bool(audit.get("ok")), "data": audit}, stdout)
        return 0 if audit.get("ok") else 1

    with _repositories(settings) as repos:
        if command == "ops" and args.ops_command == "factor-diagnostics":
            rows = repos.token_radar.latest_rows(
                window=args.window,
                scope=args.scope,
                limit=args.limit,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            )
            data = factor_distribution_report(rows)
            _emit({"ok": data["ok"], "data": data}, stdout)
            return 0 if data["ok"] else 1

        if command == "ops" and args.ops_command == "settle-token-factors":
            data = settle_token_factor_scores(
                repos=repos,
                horizon=args.horizon,
                window=args.window,
                scope=args.scope,
                generated_at_ms=args.now_ms if args.now_ms is not None else _now_ms(),
                limit=args.limit,
            )
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "backfill-token-price-baselines":
            data = repos.price_observations.backfill_token_price_baselines(limit=args.limit)
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "refresh-asset-profiles":
            providers = wire_providers(settings, start_collector=True)
            dex_profile_market = providers.asset_market.dex_profile_market
            try:
                data = refresh_asset_profiles_once(
                    repos=repos,
                    dex_profile_market=dex_profile_market,
                    now_ms=_now_ms(),
                    limit=args.limit,
                )
            finally:
                _close_asset_market_providers(providers.asset_market)
            _emit({"ok": True, "data": data}, stdout)
            return 0

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
            try:
                results = SearchService(search_query=SearchEventsQuery(repos.conn)).search(
                    args.query,
                    limit=args.limit,
                    scope=args.scope,
                    cursor=args.cursor or None,
                )
            except SearchCursorError:
                _emit({"ok": False, "error": "invalid_cursor"}, stdout)
                return 1
            _emit(
                {
                    "ok": results.ok,
                    "data": {
                        "query": results.query,
                        "page": results.page,
                        "target_candidates": results.target_candidates,
                        "items": results.items,
                    },
                    "error": results.error,
                },
                stdout,
            )
            return 0 if results.ok else 1

        if command == "asset-flow":
            data = AssetFlowService(
                token_radar=repos.token_radar,
                profiles=TokenProfileReadModel(asset_profiles=repos.asset_profiles),
            ).asset_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
                now_ms=_now_ms(),
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
                data = sync_cex_routes(
                    registry=repos.registry,
                    cex_market=OkxCexMarketProvider(client),
                    inst_types=inst_types,
                    observed_at_ms=_now_ms(),
                )
            finally:
                client.close()
            _emit({"ok": True, "data": data}, stdout)
            return 0

        if command == "ops" and args.ops_command == "sync-us-equity-symbols":
            client = NasdaqTraderSymbolClient(timeout_seconds=settings.okx_timeout_seconds)
            try:
                data = sync_us_equity_symbols(
                    registry=repos.registry,
                    client=client,
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

        if command == "ops" and args.ops_command == "run-resolution-refresh":
            okx_client = OkxDexClient(
                base_url=settings.okx_dex_base_url,
                api_key=settings.okx_dex_api_key,
                secret_key=settings.okx_dex_secret_key,
                passphrase=settings.okx_dex_passphrase,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            gmgn_client = (
                GmgnOpenApiClient(
                    api_key=settings.gmgn_api_key or "",
                    base_url=settings.gmgn_openapi_base_url,
                    timeout_seconds=settings.gmgn_timeout_seconds,
                    cache_ttl_seconds=settings.gmgn_token_info_cache_ttl_seconds,
                )
                if settings.gmgn_configured
                else None
            )
            try:
                data = run_resolution_refresh_once(
                    repos=repos,
                    dex_discovery_market=OkxDexDiscoveryProvider(okx_client),
                    dex_quote_market=GmgnDexMarketProvider(gmgn_client) if gmgn_client is not None else None,
                    chain_ids=okx_chain_indexes_to_chain_ids(settings.okx_dex_chain_indexes),
                    now_ms=_now_ms(),
                    lookup_limit=args.limit,
                    reprocess_limit=args.reprocess_limit,
                )
            finally:
                okx_client.close()
                if gmgn_client is not None:
                    gmgn_client.close()
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


def _close_asset_market_providers(asset_market: object) -> None:
    seen: set[int] = set()
    for name in (
        "sync_cex_market",
        "message_cex_market",
        "dex_discovery_market",
        "dex_quote_market",
        "dex_candle_market",
        "dex_profile_market",
        "stream_dex_market",
    ):
        provider = getattr(asset_market, name, None)
        if provider is None or id(provider) in seen:
            continue
        seen.add(id(provider))
        close = getattr(provider, "close", None)
        if close:
            close()


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
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n")


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


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
    _source_query = TokenRadarSourceQuery(repos.conn)
    source_current_window_rows = _source_query.source_count(
        since_ms=now_ms - WINDOW_MS[window],
        scope=scope,
    )
    source_max_resolution_ms = _source_query.max_resolution_ms()
    source_max_price_observed_at_ms = _source_query.max_price_observed_at_ms()
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
    market_lag_ms = (
        max(0, int(now_ms) - int(source_max_price_observed_at_ms)) if source_max_price_observed_at_ms else None
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


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
