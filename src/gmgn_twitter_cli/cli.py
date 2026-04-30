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
from .service_control import DEFAULT_INSTALL_DIR, MacLaunchAgentService, ServicePaths
from .settings import load_settings
from .store.sqlite import EventStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmgn-twitter-cli")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="run the collector service")
    serve.add_argument("--host", default=None, help="override API bind host")
    serve.add_argument("--port", type=int, default=None, help="override API bind port")

    recent = subcommands.add_parser("recent", help="print recent stored events")
    recent.add_argument("--db", type=Path, default=None, help="override SQLite event store path")
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--handles", default="")

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

    if command == "recent":
        handles = {item.strip().lstrip("@").lower() for item in args.handles.split(",") if item.strip()}
        db_path = args.db or load_settings().event_db_path
        store = EventStore(db_path)
        try:
            events = store.recent_events(limit=args.limit, handles=handles)
        finally:
            store.close()
        _emit({"ok": True, "data": {"events": events}}, stdout)
        return 0

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
