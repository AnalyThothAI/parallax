from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-intel")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("serve", help="run the collector service")

    init = subcommands.add_parser("init", help="create ~/.gmgn-twitter-intel/config.yaml")
    init.add_argument("--force", action="store_true", help="overwrite existing config.yaml")

    subcommands.add_parser("config", help="print effective runtime configuration")

    pulse = subcommands.add_parser("pulse", help="Signal Pulse diagnostics")
    pulse_subcommands = pulse.add_subparsers(dest="pulse_command", required=True)
    pulse_health = pulse_subcommands.add_parser("health", help="print Signal Pulse evidence-chain health")
    pulse_health.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    pulse_health.add_argument("--scope", choices=("all", "matched"), default="all")
    pulse_health.add_argument("--since-hours", type=int, default=4)
    pulse_replay = pulse_subcommands.add_parser("replay-eval", help="run Signal Pulse replay evaluation smoke checks")
    pulse_replay.add_argument("--fixture", default="smoke")
    pulse_replay.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    pulse_replay.add_argument("--scope", choices=("all", "matched"), default="all")
    pulse_replay.add_argument("--since-hours", type=int, default=4)

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

    social_events = subcommands.add_parser("social-events", help="print social-event extraction read model")
    social_events.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="1h")
    social_events.add_argument("--limit", type=int, default=50)
    social_events.add_argument("--handles", default="")
    social_events.add_argument("--event-types", default="")

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
    backfill_enrichment_jobs = ops_subcommands.add_parser(
        "backfill-enrichment-jobs",
        help="enqueue social-event-v2 extraction jobs for existing watched events",
    )
    backfill_enrichment_jobs.add_argument("--limit", type=int, default=1000)
    ops_subcommands.add_parser("projection-status", help="print projection offsets and latest runs")
    ops_subcommands.add_parser("worker-status", help="print canonical worker runtime status")
    validate_projections = ops_subcommands.add_parser(
        "validate-projections",
        help="validate projection read models against PostgreSQL facts",
    )
    validate_projections.add_argument("--sample", type=int, default=100)
    sync_okx_cex = ops_subcommands.add_parser("sync-okx-cex-universe", help="sync OKX public CEX instruments")
    sync_okx_cex.add_argument("--inst-type", action="append", choices=("SPOT", "SWAP"), default=[])
    ops_subcommands.add_parser("sync-binance-cex-profiles", help="sync Binance CEX token profiles")
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
        help="refresh due DEX token profile facts",
    )
    refresh_asset_profiles.add_argument("--limit", type=int, default=50)
    rebuild_token_profiles = ops_subcommands.add_parser(
        "rebuild-token-profiles",
        help="rebuild canonical token profile current facts",
    )
    rebuild_token_profiles.add_argument("--limit", type=int, default=500)
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
    rebuild_narrative_intel = ops_subcommands.add_parser(
        "rebuild-narrative-intel",
        help="rebuild and drain Narrative Intelligence read models",
    )
    rebuild_narrative_intel.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    rebuild_narrative_intel.add_argument("--scope", choices=("all", "matched"), default="matched")
    rebuild_narrative_intel.add_argument("--semantic-limit", type=int, default=50)
    rebuild_narrative_intel.add_argument("--digest-limit", type=int, default=25)
    rebuild_narrative_intel.add_argument("--cycles", type=int, default=1)
    rebuild_narrative_intel.add_argument("--drain", action="store_true")
    audit_token_radar = ops_subcommands.add_parser(
        "audit-token-radar",
        help="audit token radar rows for scoring and market-readiness regressions",
    )
    audit_token_radar.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="5m")
    audit_token_radar.add_argument("--limit", type=int, default=100)
    audit_token_radar.add_argument("--scope", choices=("all", "matched"), default="all")
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
