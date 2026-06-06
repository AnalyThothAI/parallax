from __future__ import annotations

import argparse

from parallax.app.runtime.projection_dirty_targets import DOMAIN_CHOICES, PROJECTION_CHOICES
from parallax.domains.pulse_lab.services.pulse_horizon_policy import SIGNAL_PULSE_WINDOWS


class _ExecuteMode(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)
        namespace.dry_run = False


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parallax")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("serve", help="run the collector service")

    init = subcommands.add_parser("init", help="create ~/.parallax/config.yaml")
    init.add_argument("--force", action="store_true", help="overwrite existing config.yaml")

    subcommands.add_parser("config", help="print effective runtime configuration")

    pulse = subcommands.add_parser("pulse", help="Signal Pulse diagnostics")
    pulse_subcommands = pulse.add_subparsers(dest="pulse_command", required=True)
    pulse_health = pulse_subcommands.add_parser("health", help="print Signal Pulse evidence-chain health")
    pulse_health.add_argument("--window", choices=SIGNAL_PULSE_WINDOWS, default="1h")
    pulse_health.add_argument("--scope", choices=("all", "matched"), default="all")
    pulse_health.add_argument("--since-hours", type=int, default=4)
    pulse_replay = pulse_subcommands.add_parser("replay-eval", help="run Signal Pulse replay evaluation smoke checks")
    pulse_replay.add_argument("--fixture", default="smoke")
    pulse_replay.add_argument("--window", choices=SIGNAL_PULSE_WINDOWS, default="1h")
    pulse_replay.add_argument("--scope", choices=("all", "matched"), default="all")
    pulse_replay.add_argument("--since-hours", type=int, default=4)

    db = subcommands.add_parser("db", help="database lifecycle commands")
    db_subcommands = db.add_subparsers(dest="db_command", required=True)
    db_subcommands.add_parser("migrate", help="apply PostgreSQL migrations")
    db_subcommands.add_parser("health", help="check PostgreSQL liveness and migration version")
    db_subcommands.add_parser("audit", help="run PostgreSQL count, FK, and projection schema audit")
    query_audit = db_subcommands.add_parser("query-audit", help="explain PostgreSQL hot read paths")
    query_audit.add_argument("--analyze", action="store_true", help="run EXPLAIN ANALYZE with buffers")

    macro = subcommands.add_parser("macro", help="Macro Intelligence commands")
    macro_subcommands = macro.add_subparsers(dest="macro_command", required=True)
    macro_import_bundle = macro_subcommands.add_parser("import-bundle", help="import a macrodata-cli bundle envelope")
    macro_import_bundle.add_argument("--file", default=None, help="path to macrodata-cli JSON envelope")
    macro_import_bundle.add_argument("--stdin", action="store_true", help="read macrodata-cli JSON envelope from stdin")
    macro_sync = macro_subcommands.add_parser("sync", help="fetch and import a macrodata-cli history bundle")
    macro_sync.add_argument("--bundle", required=True, help="macrodata bundle name")
    macro_sync.add_argument("--start", required=True, help="history start date (YYYY-MM-DD)")
    macro_sync.add_argument("--end", required=True, help="history end date (YYYY-MM-DD)")
    macro_subcommands.add_parser("status", help="print macro import and projection status")

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
    rebuild_market_tick_current = ops_subcommands.add_parser(
        "rebuild-market-tick-current",
        help="rebuild market_tick_current from append-only market_ticks",
    )
    rebuild_market_tick_current_mode = rebuild_market_tick_current.add_mutually_exclusive_group(required=True)
    rebuild_market_tick_current_mode.add_argument("--dry-run", action="store_true")
    rebuild_market_tick_current_mode.add_argument("--execute", action="store_true")
    enqueue_token_radar_dirty_targets = ops_subcommands.add_parser(
        "enqueue-token-radar-dirty-targets",
        help="enqueue Token Radar dirty targets from persisted facts",
    )
    enqueue_token_radar_dirty_targets.add_argument("--source", choices=("events", "market-current"), required=True)
    enqueue_token_radar_dirty_targets.add_argument("--since-ms", type=int, default=0)
    enqueue_token_radar_dirty_targets.add_argument("--limit", type=int, default=5000)
    enqueue_token_radar_dirty_targets_mode = enqueue_token_radar_dirty_targets.add_mutually_exclusive_group(
        required=True
    )
    enqueue_token_radar_dirty_targets_mode.add_argument("--dry-run", action="store_true")
    enqueue_token_radar_dirty_targets_mode.add_argument("--execute", action="store_true")
    enqueue_token_capture_tier_rank_set = ops_subcommands.add_parser(
        "enqueue-token-capture-tier-rank-set",
        help="enqueue Token Capture Tier repair from current Token Radar rank set",
    )
    enqueue_token_capture_tier_rank_set.add_argument("--window", choices=("5m", "1h", "4h", "24h"), default="24h")
    enqueue_token_capture_tier_rank_set.add_argument("--limit", type=int, default=500)
    enqueue_token_capture_tier_rank_set_mode = enqueue_token_capture_tier_rank_set.add_mutually_exclusive_group(
        required=True
    )
    enqueue_token_capture_tier_rank_set_mode.add_argument("--dry-run", action="store_true")
    enqueue_token_capture_tier_rank_set_mode.add_argument("--execute", action="store_true")
    ops_subcommands.add_parser("projection-status", help="print projection offsets and latest runs")
    ops_subcommands.add_parser("worker-status", help="print canonical worker runtime status")
    queue_inspect = ops_subcommands.add_parser("queue-inspect", help="inspect worker queue terminal evidence")
    queue_inspect.add_argument("--worker", default="")
    queue_inspect.add_argument("--source-table", default="")
    queue_inspect.add_argument("--status", choices=("terminal", "active"), default="terminal")
    queue_inspect.add_argument("--reason-bucket", default="")
    queue_inspect.add_argument("--limit", type=int, default=50)
    queue_resolve = ops_subcommands.add_parser("queue-resolve", help="resolve worker queue terminal evidence")
    queue_resolve.add_argument("--terminal-id", required=True)
    queue_resolve.add_argument("--action", choices=("retry", "quarantine", "archive"), required=True)
    queue_resolve.add_argument("--reason", required=True)
    queue_resolve.add_argument("--execute", action="store_true")
    reconcile_event_anchor = ops_subcommands.add_parser(
        "reconcile-event-anchor-jobs",
        help="one-shot reconcile of historical ready event-anchor backfill jobs",
    )
    reconcile_event_anchor.add_argument("--limit", type=int, default=1000)
    reconcile_event_anchor.add_argument("--execute", action="store_true")
    validate_projections = ops_subcommands.add_parser(
        "validate-projections",
        help="validate projection read models against PostgreSQL facts",
    )
    validate_projections.add_argument("--sample", type=int, default=100)
    enqueue_projection_dirty_targets = ops_subcommands.add_parser(
        "enqueue-projection-dirty-targets",
        help="enqueue dirty targets for rebuildable News projections",
    )
    enqueue_projection_dirty_targets.add_argument("--domain", choices=DOMAIN_CHOICES, default="all")
    enqueue_projection_dirty_targets.add_argument("--projection", choices=PROJECTION_CHOICES, default="all")
    enqueue_projection_dirty_targets.add_argument("--since-hours", type=float, default=None)
    enqueue_projection_dirty_targets_mode = enqueue_projection_dirty_targets.add_mutually_exclusive_group(required=True)
    enqueue_projection_dirty_targets_mode.add_argument("--dry-run", action="store_true")
    enqueue_projection_dirty_targets_mode.add_argument("--execute", action="store_true")
    news_dedup_diagnostics = ops_subcommands.add_parser(
        "news-dedup-diagnostics",
        help="print News canonical dedup and OpenNews sync diagnostics",
    )
    news_dedup_diagnostics.add_argument("--window-hours", type=float, default=8.0)
    news_dedup_diagnostics.add_argument("--score-threshold", type=int, default=80)
    cleanup_news_brief_input = ops_subcommands.add_parser(
        "cleanup-news-brief-input",
        help="delete stale News brief_input dirty targets whose persisted agent requirement is not required",
    )
    cleanup_news_brief_input_mode = cleanup_news_brief_input.add_mutually_exclusive_group(required=True)
    cleanup_news_brief_input_mode.add_argument("--dry-run", action="store_true")
    cleanup_news_brief_input_mode.add_argument("--execute", action="store_true")
    cleanup_news_intel_hard_cut = ops_subcommands.add_parser(
        "cleanup-news-intel-hard-cut",
        help="dry-run or execute the News Intel hard-cut artifact-only cleanup",
    )
    cleanup_news_intel_hard_cut_mode = cleanup_news_intel_hard_cut.add_mutually_exclusive_group(required=False)
    cleanup_news_intel_hard_cut_mode.add_argument("--dry-run", action="store_true")
    cleanup_news_intel_hard_cut_mode.add_argument("--execute", action="store_true")
    cleanup_news_intel_hard_cut.add_argument("--current-artifact-version-hash", default=None)
    rebuild_news_canonical_items = ops_subcommands.add_parser(
        "rebuild-news-canonical-items",
        help="enqueue a bounded rebuild of News canonical item derived projections",
    )
    rebuild_news_canonical_items.add_argument("--limit", type=int, default=5000)
    rebuild_news_canonical_items_mode = rebuild_news_canonical_items.add_mutually_exclusive_group(required=True)
    rebuild_news_canonical_items_mode.add_argument("--dry-run", action="store_true")
    rebuild_news_canonical_items_mode.add_argument("--execute", action="store_true")
    repair_news_duplicates_hard_cut = ops_subcommands.add_parser(
        "repair-news-duplicates-hard-cut",
        help="repair historical News duplicate rows under the current hard-cut identity policy",
    )
    repair_news_duplicates_hard_cut.add_argument("--limit", type=_positive_int, default=20000)
    repair_news_duplicates_hard_cut_mode = repair_news_duplicates_hard_cut.add_mutually_exclusive_group(required=True)
    repair_news_duplicates_hard_cut_mode.add_argument("--dry-run", action="store_true")
    repair_news_duplicates_hard_cut_mode.add_argument("--execute", action="store_true")
    repair_news_agent_market_admission = ops_subcommands.add_parser(
        "repair-news-agent-market-admission",
        help="recompute market-wide News agent admission and enqueue eligible brief work",
    )
    repair_news_agent_market_admission.add_argument("--since-ms", type=int, required=True)
    repair_news_agent_market_admission.add_argument("--until-ms", type=int, required=True)
    repair_news_agent_market_admission.add_argument("--min-provider-score", type=int, default=80)
    repair_news_agent_market_admission.add_argument("--limit", type=_positive_int, default=500)
    repair_news_agent_market_admission_mode = repair_news_agent_market_admission.add_mutually_exclusive_group()
    repair_news_agent_market_admission_mode.add_argument("--dry-run", action="store_true", default=True)
    repair_news_agent_market_admission_mode.add_argument("--execute", action=_ExecuteMode, default=False)
    sync_binance_universe = ops_subcommands.add_parser(
        "sync-binance-usdt-perp-universe",
        help="sync Binance USD-M USDT perpetual contracts into the CEX registry",
    )
    sync_binance_universe_mode = sync_binance_universe.add_mutually_exclusive_group(required=True)
    sync_binance_universe_mode.add_argument("--dry-run", action="store_true")
    sync_binance_universe_mode.add_argument("--execute", action="store_true")
    ops_subcommands.add_parser("sync-binance-cex-profiles", help="sync Binance CEX token profiles")
    cex_binance_cleanup = ops_subcommands.add_parser(
        "cex-binance-hard-cut-cleanup",
        help="clean old OKX CEX rows after Binance CEX registry sync",
    )
    cex_binance_cleanup.add_argument("--min-binance-feeds", type=int, default=400)
    cleanup_mode = cex_binance_cleanup.add_mutually_exclusive_group(required=True)
    cleanup_mode.add_argument("--dry-run", action="store_true")
    cleanup_mode.add_argument("--execute", action="store_true")
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
    mirror_token_images = ops_subcommands.add_parser(
        "mirror-token-images",
        help="mirror provider token images into the local cache",
    )
    mirror_token_images.add_argument("--limit", type=int, default=500)
    repair_token_profile_images = ops_subcommands.add_parser(
        "repair-token-profile-images",
        help="enqueue current profile targets so token image source admission can repair stuck icons",
    )
    repair_token_profile_images.add_argument("--limit", type=_positive_int, default=500)
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
    rebuild_narrative_intel.add_argument("--window", choices=("1h",), default="1h")
    rebuild_narrative_intel.add_argument("--scope", choices=("all",), default="all")
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
