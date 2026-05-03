from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from typing import TextIO

import uvicorn

from .api.app import create_app
from .logging_setup import setup_logging
from .pipeline.narrative_token_linker import NarrativeTokenLinker
from .retrieval.account_alert_service import AccountAlertService
from .retrieval.narrative_link_service import NarrativeLinkService
from .retrieval.narrative_service import NarrativeService
from .retrieval.search_service import SearchService
from .retrieval.token_flow_service import TokenFlowService
from .settings import load_settings, write_default_config
from .storage.enrichment_repository import EnrichmentRepository
from .storage.entity_repository import EntityRepository
from .storage.evidence_repository import EvidenceRepository
from .storage.signal_repository import SignalRepository
from .storage.sqlite_client import connect_sqlite
from .storage.sqlite_schema import migrate
from .storage.token_repository import TokenRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-intel")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("serve", help="run the collector service")

    init = subcommands.add_parser("init", help="create ~/.gmgn-twitter-intel/config.yaml")
    init.add_argument("--force", action="store_true", help="overwrite existing config.yaml")

    subcommands.add_parser("config", help="print effective runtime configuration")

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
    token_flow.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="5m")
    token_flow.add_argument("--limit", type=int, default=20)

    narrative_flow = subcommands.add_parser("narrative-flow", help="rank LLM narrative activity windows")
    narrative_flow.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="1h")
    narrative_flow.add_argument("--limit", type=int, default=20)

    account_alerts = subcommands.add_parser("account-alerts", help="print watched-account token alerts")
    account_alerts.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="24h")
    account_alerts.add_argument("--limit", type=int, default=50)
    account_alerts.add_argument("--handles", default="")
    account_alerts.add_argument(
        "--alert-type",
        choices=("account_token", "token"),
        default=None,
    )

    account_narratives = subcommands.add_parser("account-narratives", help="print watched-account narrative alerts")
    account_narratives.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="24h")
    account_narratives.add_argument("--limit", type=int, default=50)
    account_narratives.add_argument("--handles", default="")

    enrichment_jobs = subcommands.add_parser("enrichment-jobs", help="inspect LLM enrichment job backlog")
    enrichment_jobs.add_argument("--status", choices=("pending", "running", "failed", "dead", "done"), default=None)
    enrichment_jobs.add_argument("--limit", type=int, default=50)

    narrative_seeds = subcommands.add_parser("narrative-seeds", help="print watched-handle narrative seeds")
    narrative_seeds.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="24h")
    narrative_seeds.add_argument("--limit", type=int, default=50)
    narrative_seeds.add_argument("--handles", default="")

    narrative_token_flow = subcommands.add_parser(
        "narrative-token-flow",
        help="print tokens linked to a watched-handle narrative seed",
    )
    narrative_token_flow.add_argument("--seed-id", required=True)
    narrative_token_flow.add_argument("--window", choices=("5m", "1h", "24h"), default="1h")
    narrative_token_flow.add_argument("--limit", type=int, default=20)

    attention_frontier = subcommands.add_parser(
        "attention-frontier",
        help="rank recent watched-handle narrative token links",
    )
    attention_frontier.add_argument("--window", choices=("5m", "1h", "24h"), default="1h")
    attention_frontier.add_argument("--limit", type=int, default=30)

    ops = subcommands.add_parser("ops", help="maintenance commands")
    ops_subcommands = ops.add_subparsers(dest="ops_command", required=True)
    rebuild_narrative_links = ops_subcommands.add_parser(
        "rebuild-narrative-links",
        help="rebuild watched-handle narrative token links from existing seeds",
    )
    rebuild_narrative_links.add_argument("--window", choices=("5m", "1h", "24h"), default="1h")
    rebuild_narrative_links.add_argument("--limit", type=int, default=1000)

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
        _emit(
            {
                "ok": True,
                "data": {
                    "config_path": str(path),
                    "app_home": str(path.parent),
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
                        "sqlite_path": str(settings.sqlite_path),
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
                },
            },
            stdout,
        )
        return 0

    settings = load_settings(require_ws_token=False)
    with _repositories(settings.sqlite_path) as repos:
        evidence, entities, signals, tokens, enrichment = repos
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
            results = SearchService(evidence=evidence, entities=entities, signals=signals).search(
                query,
                limit=args.limit,
                scope=args.scope,
            )
            _emit(
                {
                    "ok": results.ok,
                    "data": {
                        "query": results.query,
                        "result_count": len(results.items),
                        "items": results.items,
                    },
                    "error": results.error,
                },
                stdout,
            )
            return 0 if results.ok else 1

        if command == "token-flow":
            items = TokenFlowService(signals=signals, tokens=tokens, enrichment=enrichment).token_flow(
                window=args.window,
                limit=args.limit,
            )
            _emit(
                {"ok": True, "data": {"window": args.window, "items": items}},
                stdout,
            )
            return 0

        if command == "narrative-flow":
            items = NarrativeService(enrichment).narrative_flow(window=args.window, limit=args.limit)
            _emit({"ok": True, "data": {"window": args.window, "items": items}}, stdout)
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

        if command == "account-narratives":
            items = NarrativeService(enrichment).account_narratives(
                window=args.window,
                limit=args.limit,
                handles=_handle_set(args.handles),
            )
            _emit({"ok": True, "data": {"window": args.window, "items": items}}, stdout)
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

        if command == "narrative-seeds":
            items = NarrativeLinkService(enrichment=enrichment).narrative_seeds(
                window=args.window,
                limit=args.limit,
                handles=_handle_set(args.handles),
            )
            _emit({"ok": True, "data": {"window": args.window, "items": items}}, stdout)
            return 0

        if command == "narrative-token-flow":
            data = NarrativeLinkService(enrichment=enrichment).narrative_token_flow(
                seed_id=args.seed_id,
                window=args.window,
                limit=args.limit,
            )
            _emit({"ok": True, "data": data | {"window": args.window}}, stdout)
            return 0

        if command == "attention-frontier":
            items = NarrativeLinkService(enrichment=enrichment).attention_frontier(
                window=args.window,
                limit=args.limit,
            )
            _emit({"ok": True, "data": {"window": args.window, "items": items}}, stdout)
            return 0

        if command == "ops" and args.ops_command == "rebuild-narrative-links":
            seeds = _all_narrative_seeds(enrichment, limit=args.limit)
            linker = NarrativeTokenLinker(
                evidence=evidence,
                signals=signals,
                enrichment=enrichment,
                tokens=tokens,
            )
            links_upserted = 0
            for seed in seeds:
                links_upserted += len(linker.link_seed(seed=seed, window=args.window, commit=False))
            enrichment.conn.commit()
            _emit(
                {
                    "ok": True,
                    "data": {
                        "window": args.window,
                        "seeds_scanned": len(seeds),
                        "links_upserted": links_upserted,
                    },
                },
                stdout,
            )
            return 0

    parser.error(f"unknown command: {command}")
    return 2


@contextmanager
def _repositories(sqlite_path):
    conn = connect_sqlite(sqlite_path, read_only=False)
    try:
        migrate(conn)
        yield (
            EvidenceRepository(conn),
            EntityRepository(conn),
            SignalRepository(conn),
            TokenRepository(conn),
            EnrichmentRepository(conn),
        )
    finally:
        conn.close()


def _emit(payload: dict, stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


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


def _all_narrative_seeds(enrichment: EnrichmentRepository, *, limit: int) -> list[dict]:
    rows = enrichment.conn.execute(
        """
        SELECT seed_id FROM narrative_seeds
        ORDER BY received_at_ms DESC
        LIMIT ?
        """,
        (max(0, int(limit)),),
    ).fetchall()
    return [
        seed
        for row in rows
        if (seed := enrichment.narrative_seed(str(row["seed_id"]))) is not None
    ]
