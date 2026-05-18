from __future__ import annotations

import time
from typing import Any

from gmgn_twitter_intel.app.surfaces.cli.commands import CommandResult
from gmgn_twitter_intel.app.surfaces.cli.dependencies import postgres_connection
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_freshness_health import PulseFreshnessHealthService
from gmgn_twitter_intel.platform.config.settings import load_settings


def handle_pulse(args: Any) -> CommandResult:
    if args.pulse_command == "health":
        return _handle_health(args)
    if args.pulse_command == "replay-eval":
        return _handle_replay_eval(args)
    return 2, {"ok": False, "error": f"unknown pulse command: {args.pulse_command}"}


def _handle_health(args: Any) -> CommandResult:
    settings = load_settings(require_ws_token=False)
    with postgres_connection(settings) as conn:
        health = PulseFreshnessHealthService(conn).health(
            window=str(args.window),
            scope=str(args.scope),
            now_ms=int(time.time() * 1000),
            since_hours=int(args.since_hours),
        )
    return (0 if health.get("publish_status") != "hold_publish" else 1), {"ok": True, "data": health}


def _handle_replay_eval(args: Any) -> CommandResult:
    settings = load_settings(require_ws_token=False)
    with postgres_connection(settings) as conn:
        health = PulseFreshnessHealthService(conn).health(
            window=str(args.window),
            scope=str(args.scope),
            now_ms=int(time.time() * 1000),
            since_hours=int(args.since_hours),
        )
    data = {
        "fixture": str(args.fixture),
        "total_cases": 1,
        "pass_count": 1 if health.get("latest_packet_created_at_ms") else 0,
        "failure_classes": [] if health.get("latest_packet_created_at_ms") else ["no_evidence_packets"],
        "newest_packet_created_at_ms": health.get("latest_packet_created_at_ms"),
        "public_allowed_count": int(health.get("public_candidates_4h") or 0),
        "publish_status": health.get("publish_status"),
    }
    ok = data["pass_count"] == data["total_cases"]
    return (0 if ok else 1), {"ok": ok, "data": data}


__all__ = ["handle_pulse"]
