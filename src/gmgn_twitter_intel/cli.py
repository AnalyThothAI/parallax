from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from typing import TextIO

import uvicorn

from .api.app import create_app
from .logging_setup import setup_logging
from .retrieval.account_alert_service import AccountAlertService
from .retrieval.search_service import SearchService
from .retrieval.token_flow_service import TokenFlowService
from .settings import load_settings
from .storage.entity_repository import EntityRepository
from .storage.evidence_repository import EvidenceRepository
from .storage.signal_repository import SignalRepository
from .storage.sqlite_client import connect_sqlite
from .storage.sqlite_schema import migrate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-intel")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="run the collector service")
    serve.add_argument("--host", default=None, help="override API bind host")
    serve.add_argument("--port", type=int, default=None, help="override API bind port")

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

    keyword_flow = subcommands.add_parser("keyword-flow", help="rank keyword activity windows")
    keyword_flow.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="1h")
    keyword_flow.add_argument("--limit", type=int, default=20)

    account_alerts = subcommands.add_parser("account-alerts", help="print watched-account token/keyword alerts")
    account_alerts.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="24h")
    account_alerts.add_argument("--limit", type=int, default=50)
    account_alerts.add_argument("--handles", default="")
    account_alerts.add_argument(
        "--alert-type",
        choices=("account_token", "account_keyword", "token", "keyword"),
        default=None,
    )

    ops = subcommands.add_parser("ops", help="maintenance commands")
    ops_subcommands = ops.add_subparsers(dest="ops_command", required=True)
    rebuild_windows = ops_subcommands.add_parser("rebuild-windows", help="rebuild materialized windows from entities")
    rebuild_windows.add_argument("--window", choices=("1m", "5m", "1h", "24h"), default="5m")

    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    command = args.command or "serve"

    if command == "serve":
        settings = load_settings()
        setup_logging(settings.log_file)
        host = args.host or settings.api_host
        port = args.port or settings.api_port
        uvicorn.run(
            create_app(settings=settings),
            host=host,
            port=port,
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
                    "watch_keywords": list(settings.watch_keywords),
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
                },
            },
            stdout,
        )
        return 0

    settings = load_settings(require_ws_token=False)
    with _repositories(settings.sqlite_path) as repos:
        evidence, entities, signals = repos
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
            results = SearchService(evidence=evidence, entities=entities).search(
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
            items = TokenFlowService(signals).token_flow(window=args.window, limit=args.limit)
            _emit(
                {"ok": True, "data": {"window": args.window, "items": items}},
                stdout,
            )
            return 0

        if command == "keyword-flow":
            items = signals.keyword_flow(window=args.window, limit=args.limit)
            _emit(
                {"ok": True, "data": {"window": args.window, "items": items}},
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

        if command == "ops" and args.ops_command == "rebuild-windows":
            rebuilt = signals.rebuild_windows(window=args.window)
            _emit({"ok": True, "data": {"window": args.window, "rebuilt": rebuilt}}, stdout)
            return 0

    parser.error(f"unknown command: {command}")
    return 2


@contextmanager
def _repositories(sqlite_path):
    conn = connect_sqlite(sqlite_path, read_only=False)
    try:
        migrate(conn)
        yield EvidenceRepository(conn), EntityRepository(conn), SignalRepository(conn)
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
