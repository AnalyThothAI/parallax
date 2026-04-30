from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import TextIO

import uvicorn

from .api.app import create_app
from .logging_setup import setup_logging
from .pipeline.embedding import HashEmbeddingBackend, embed_pending_tweets
from .pipeline.llm_enrichment import LiteLlmJsonClient, LlmEnrichmentService
from .pipeline.token_registry import DexScreenerProvider, TokenResolver
from .retrieval.mindshare_service import MindshareService
from .retrieval.search_service import SearchService
from .service_control import DEFAULT_INSTALL_DIR, MacLaunchAgentService, ServicePaths
from .settings import load_settings
from .storage.index_maintenance import ensure_core_indexes
from .storage.lancedb_client import build_lancedb_client
from .storage.llm_repository import LlmRepository
from .storage.social_repository import SocialRepository
from .storage.token_registry_repository import TokenRegistryRepository
from .storage.tweet_repository import TweetRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-cli")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="run the collector service")
    serve.add_argument("--host", default=None, help="override API bind host")
    serve.add_argument("--port", type=int, default=None, help="override API bind port")

    subcommands.add_parser("config", help="print effective runtime configuration")

    recent = subcommands.add_parser("recent", help="print recent stored events")
    recent.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--handles", default="")
    recent.add_argument("--ca", default="", help="filter by token contract address")
    recent.add_argument("--chain", default="", help="chain for contract address filters")
    recent.add_argument("--symbol", default="", help="filter by cashtag symbol")

    search = subcommands.add_parser("search", help="search stored tweets by CA, symbol, handle, or text")
    search.add_argument("query")
    search.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument(
        "--scope",
        choices=("all", "matched"),
        default="all",
        help="search all stored events or matched events only",
    )

    embed = subcommands.add_parser("embed", help="process pending tweet embeddings")
    embed.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    embed.add_argument("--limit", type=int, default=100)

    mindshare = subcommands.add_parser("mindshare", help="compute token social mindshare")
    mindshare.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    mindshare.add_argument("--ca", default="", help="token contract address")
    mindshare.add_argument("--chain", default="", help="chain for contract address")
    mindshare.add_argument("--symbol", default="", help="cashtag symbol")
    mindshare.add_argument("--window", default="1h")

    enrich = subcommands.add_parser("enrich", help="run evidence-bound LLM enrichment")
    enrich.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    enrich.add_argument("--unresolved", action="store_true", help="enrich unresolved symbol tweets")
    enrich.add_argument("--ca", default="", help="token contract address")
    enrich.add_argument("--chain", default="", help="chain for contract address")
    enrich.add_argument("--limit", type=int, default=20)
    enrich.add_argument("--model", default="", help="LiteLLM model name")

    resolve_token = subcommands.add_parser("resolve-token", help="resolve and cache a token symbol or CA")
    resolve_token.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    resolve_token.add_argument("--symbol", default="", help="token symbol")
    resolve_token.add_argument("--ca", default="", help="token contract address")
    resolve_token.add_argument("--chain", default="", help="chain for contract address")
    resolve_token.add_argument("--timeout", type=float, default=5.0)

    ops = subcommands.add_parser("ops", help="maintenance commands")
    ops_subcommands = ops.add_subparsers(dest="ops_command", required=True)
    rebuild_indexes = ops_subcommands.add_parser("rebuild-indexes", help="rebuild LanceDB scalar indexes")
    rebuild_indexes.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    rebuild_indexes.add_argument("--replace", action="store_true")
    reprocess_entities = ops_subcommands.add_parser("reprocess-entities", help="re-run cheap entity extraction")
    reprocess_entities.add_argument("--store", type=Path, default=None, help="override LanceDB store path")
    reprocess_entities.add_argument("--limit", type=int, default=1000)

    service = subcommands.add_parser("service", help="manage the background service")
    service_subcommands = service.add_subparsers(dest="service_command", required=True)

    install = service_subcommands.add_parser("install", help="install the macOS LaunchAgent")
    install.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL_DIR)
    install.add_argument("--start", action="store_true", default=True)
    install.add_argument("--no-start", action="store_false", dest="start")

    service_subcommands.add_parser("start", help="start the macOS LaunchAgent")
    service_subcommands.add_parser("stop", help="stop the macOS LaunchAgent")
    service_subcommands.add_parser("restart", help="restart the macOS LaunchAgent")
    service_subcommands.add_parser("status", help="print launchd status")
    logs = service_subcommands.add_parser("logs", help="print recent launchd logs")
    logs.add_argument("--lines", type=int, default=80)
    uninstall = service_subcommands.add_parser("uninstall", help="remove the macOS LaunchAgent")
    uninstall.add_argument("--remove-files", action="store_true")

    return parser


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
        settings = load_settings()
        _emit(
            {
                "ok": True,
                "data": {
                    "handles": list(settings.handles),
                    "handle_count": len(settings.handles),
                    "api": {
                        "host": settings.api_host,
                        "port": settings.api_port,
                        "replay_limit": settings.replay_limit,
                        "ws_token_configured": bool(settings.ws_token),
                    },
                    "store": {
                        "lancedb_path": str(settings.lancedb_path),
                        "embedding_dim": settings.embedding_dim,
                    },
                    "providers": {
                        "embedding": "hash",
                        "sentiment": settings.sentiment_backend,
                        "llm_model_configured": bool(settings.llm_model),
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

    if command == "recent":
        handles = {item.strip().lstrip("@").lower() for item in args.handles.split(",") if item.strip()}
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        store = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            if args.symbol and not args.ca:
                candidates = store.symbol_ca_candidates(args.symbol)
                if len(candidates) > 1:
                    _emit({"ok": False, "error": "ambiguous_symbol", "data": {"candidates": candidates}}, stdout)
                    return 1
            events = store.recent_events(
                limit=args.limit,
                handles=handles,
                ca=args.ca or None,
                chain=args.chain or None,
                symbol=args.symbol or None,
            )
        finally:
            store.close()
        _emit({"ok": True, "data": {"events": events}}, stdout)
        return 0

    if command == "search":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            parsed = args.query.strip().lstrip("$").upper()
            if parsed and args.query.strip().startswith("$"):
                candidates = repo.symbol_ca_candidates(parsed)
                if len(candidates) > 1:
                    _emit({"ok": False, "error": "ambiguous_symbol", "data": {"candidates": candidates}}, stdout)
                    return 1
            results = SearchService(repo, HashEmbeddingBackend(dimension=repo.client.embedding_dim)).search(
                args.query,
                limit=args.limit,
                scope=args.scope,
            )
        finally:
            repo.close()
        _emit(
            {
                "ok": results.ok,
                "data": {
                    "query": results.query,
                    "result_count": len(results.items),
                    "items": results.items,
                    "candidates": results.candidates,
                },
                "error": results.error,
            },
            stdout,
        )
        return 0 if results.ok else 1

    if command == "embed":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            processed = embed_pending_tweets(
                repo,
                HashEmbeddingBackend(dimension=repo.client.embedding_dim),
                limit=args.limit,
            )
        finally:
            repo.close()
        _emit({"ok": True, "data": {"processed": processed}}, stdout)
        return 0

    if command == "mindshare":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        sentiment_backend = settings.sentiment_backend if settings else "none"
        repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            result = MindshareService(
                repo,
                SocialRepository(repo.client),
                sentiment_backend=sentiment_backend,
            ).mindshare(
                ca=args.ca or None,
                chain=args.chain or None,
                symbol=args.symbol or None,
                window=args.window,
            )
        finally:
            repo.close()
        _emit(result, stdout)
        return 0 if result.get("ok") else 1

    if command == "enrich":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        model = args.model or (settings.llm_model if settings else None)
        if not model:
            _emit({"ok": False, "error": "llm_not_configured", "data": {}}, stdout)
            return 1
        repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            if args.ca:
                events = repo.recent_events(limit=args.limit, ca=args.ca, chain=args.chain or None)
                scope = f"ca:{args.chain or ''}:{args.ca}"
            elif args.unresolved:
                rows = repo.client.query_where(
                    "twitter_events",
                    where="token_resolution_status = 'unresolved' AND matched_at_ms > 0",
                    order_by="received_at_ms",
                    descending=True,
                    limit=args.limit,
                )
                events = [repo.decode_event_row(row) for row in rows]
                scope = "unresolved"
            else:
                _emit({"ok": False, "error": "enrichment_scope_required", "data": {}}, stdout)
                return 1
            run = LlmEnrichmentService(
                LlmRepository(repo.client),
                LiteLlmJsonClient(model=model),
            ).enrich_events(events, scope=scope, model=model)
        finally:
            repo.close()
        _emit({"ok": run["status"] == "succeeded", "data": {"run": run}, "error": run.get("error")}, stdout)
        return 0 if run["status"] == "succeeded" else 1

    if command == "resolve-token":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        registry_repo = TokenRegistryRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            resolver = TokenResolver(registry_repo, DexScreenerProvider(timeout=args.timeout))
            if args.ca:
                result = resolver.resolve_ca(args.ca, chain=args.chain or None)
            elif args.symbol:
                result = resolver.resolve_symbol(args.symbol)
            else:
                _emit({"ok": False, "error": "token_query_required", "data": {}}, stdout)
                return 1
        finally:
            registry_repo.close()
        _emit({"ok": result["status"] == "resolved", "data": result, "error": None}, stdout)
        return 0 if result["status"] == "resolved" else 1

    if command == "ops":
        settings = None if args.store else load_settings()
        store_path = args.store or settings.lancedb_path
        embedding_dim = settings.embedding_dim if settings else None
        repo = TweetRepository(build_lancedb_client(store_path, embedding_dim=embedding_dim))
        try:
            if args.ops_command == "rebuild-indexes":
                statuses = ensure_core_indexes(repo.client, replace=args.replace)
                _emit({"ok": True, "data": {"indexes": statuses}}, stdout)
                return 0
            if args.ops_command == "reprocess-entities":
                processed = repo.reprocess_entities(limit=args.limit)
                _emit({"ok": True, "data": {"processed": processed}}, stdout)
                return 0
        finally:
            repo.close()
        return 2

    if command == "service":
        return _run_service_command(args, stdout)

    parser.error(f"unknown command: {command}")
    return 2


def _emit(payload: dict, stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _run_service_command(args: argparse.Namespace, stdout: TextIO) -> int:
    if platform.system() != "Darwin":
        stdout.write("service commands currently support macOS launchd only\n")
        return 2

    install_dir = getattr(args, "install_dir", DEFAULT_INSTALL_DIR)
    service = MacLaunchAgentService(
        paths=ServicePaths(project_dir=Path.cwd(), install_dir=install_dir),
        stdout=stdout,
    )
    if args.service_command == "install":
        service.install(start=args.start)
        return 0
    if args.service_command == "start":
        service.start()
        return 0
    if args.service_command == "stop":
        service.stop()
        return 0
    if args.service_command == "restart":
        service.restart()
        return 0
    if args.service_command == "status":
        return service.status()
    if args.service_command == "logs":
        service.logs(lines=args.lines)
        return 0
    if args.service_command == "uninstall":
        service.uninstall(remove_files=args.remove_files)
        return 0
    return 2
