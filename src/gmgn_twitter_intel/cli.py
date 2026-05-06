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
from .pipeline.harness_ops import attribute_harness_credits, settle_harness_snapshots, update_harness_weights
from .pipeline.token_attribution import TokenAttributionBuilder
from .pipeline.token_signal_settlement import settle_token_signal_snapshots
from .retrieval.account_alert_service import AccountAlertService
from .retrieval.account_quality_service import AccountQualityService
from .retrieval.harness_service import HarnessService
from .retrieval.search_service import SearchService
from .retrieval.token_flow_service import TokenFlowService
from .retrieval.token_signal_evaluation_service import TokenSignalEvaluationService
from .retrieval.token_signal_snapshot_service import TokenSignalSnapshotService
from .settings import load_settings, write_default_config
from .storage.account_quality_repository import AccountQualityRepository
from .storage.enrichment_repository import EnrichmentRepository
from .storage.entity_repository import EntityRepository
from .storage.evidence_repository import EvidenceRepository
from .storage.harness_repository import HarnessRepository
from .storage.market_observation_repository import MarketObservationRepository
from .storage.notification_repository import NotificationRepository
from .storage.postgres_client import connect_postgres, postgres_health_check, with_password_from_file
from .storage.postgres_migrations import upgrade_head
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

    token_flow = subcommands.add_parser("token-flow", help="rank token activity windows")
    token_flow.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="5m")
    token_flow.add_argument("--limit", type=int, default=20)
    token_flow.add_argument("--scope", choices=("all", "matched"), default="all")

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
    rebuild_attributions = ops_subcommands.add_parser(
        "rebuild-attributions",
        help="rebuild explicit token attributions from existing token mentions",
    )
    rebuild_attributions.add_argument("--symbol", default="", help="limit rebuild to one token symbol")
    rebuild_attributions.add_argument("--limit", type=int, default=0, help="optional max raw mentions per phase")
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
    freeze_token_signals = ops_subcommands.add_parser(
        "freeze-token-signals",
        help="freeze ranked token-flow items as token signal snapshots",
    )
    freeze_token_signals.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="5m")
    freeze_token_signals.add_argument("--limit", type=int, default=200)
    freeze_token_signals.add_argument("--scope", choices=("all", "matched"), default="all")
    settle_token_signals = ops_subcommands.add_parser(
        "settle-token-signals",
        help="settle due frozen token signal snapshots",
    )
    settle_token_signals.add_argument("--horizon", choices=("6h", "24h"), default="6h")
    settle_token_signals.add_argument("--limit", type=int, default=500)
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

    with _repositories(settings) as repos:
        (
            evidence,
            entities,
            signals,
            tokens,
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
            results = SearchService(evidence=evidence, signals=signals, tokens=tokens).search(
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
                        "candidates": results.candidates,
                        "items": results.items,
                    },
                    "error": results.error,
                },
                stdout,
            )
            return 0 if results.ok else 1

        if command == "token-flow":
            items = TokenFlowService(signals=signals, tokens=tokens, harness=harness).token_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
            )
            _emit(
                {"ok": True, "data": {"window": args.window, "scope": args.scope, "items": items}},
                stdout,
            )
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

        if command == "ops" and args.ops_command == "rebuild-attributions":
            symbol = args.symbol.strip().lstrip("$").upper() or None
            limit = int(args.limit) if int(args.limit) > 0 else None
            builder = TokenAttributionBuilder(signals=signals, tokens=tokens)
            direct_rows = signals.attribution_rebuild_rows(
                symbol=symbol,
                direct_only=True,
                limit=limit,
            )
            direct_count = signals.replace_token_attributions(
                mention_ids=[str(row["mention_id"]) for row in direct_rows],
                attributions=builder.build_for_rows(direct_rows),
                commit=False,
            )
            symbol_rows = signals.attribution_rebuild_rows(
                symbol=symbol,
                symbol_only=True,
                limit=limit,
            )
            symbol_count = signals.replace_token_attributions(
                mention_ids=[str(row["mention_id"]) for row in symbol_rows],
                attributions=builder.build_for_rows(symbol_rows),
                commit=False,
            )
            signals.conn.commit()
            _emit(
                {
                    "ok": True,
                    "data": {
                        "symbol": symbol or "ALL",
                        "direct_mentions_scanned": len(direct_rows),
                        "symbol_mentions_scanned": len(symbol_rows),
                        "direct_attributions_written": direct_count,
                        "symbol_attributions_written": symbol_count,
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
                        tokens=tokens,
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

        if command == "ops" and args.ops_command == "freeze-token-signals":
            _emit(
                {
                    "ok": True,
                    "data": TokenSignalSnapshotService(
                        token_flow=TokenFlowService(signals=signals, tokens=tokens, harness=harness),
                        repository=token_signals,
                    ).freeze(
                        window=args.window,
                        scope=args.scope,
                        limit=args.limit,
                    ),
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
