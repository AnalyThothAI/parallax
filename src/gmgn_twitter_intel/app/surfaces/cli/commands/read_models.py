from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.surfaces.cli.dependencies import repositories
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.account_quality.read_models.account_quality_service import AccountQualityService
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.token_intel.queries.search_events_query import SearchEventsQuery
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.read_models.search_service import SearchCursorError, SearchService
from gmgn_twitter_intel.platform.config.settings import load_settings

READ_MODEL_COMMANDS = frozenset(
    {
        "recent",
        "search",
        "asset-flow",
        "account-alerts",
        "account-quality",
        "social-events",
        "enrichment-jobs",
        "notification-deliveries",
    }
)


def handle_read_model(args: object) -> tuple[int, dict[str, Any]]:
    command = args.command
    settings = load_settings(require_ws_token=False)
    with repositories(settings) as repos:
        evidence = repos.evidence
        signals = repos.signals
        enrichment = repos.enrichment
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
            return 0, {"ok": True, "data": {"events": events}}

        if command == "search":
            try:
                results = SearchService(search_query=SearchEventsQuery(repos.conn)).search(
                    args.query,
                    limit=args.limit,
                    scope=args.scope,
                    cursor=args.cursor or None,
                )
            except SearchCursorError:
                return 1, {"ok": False, "error": "invalid_cursor"}
            return (
                0 if results.ok else 1,
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
            )

        if command == "asset-flow":
            data = AssetFlowService(
                token_radar=repos.token_radar,
                profiles=TokenProfileReadModel(token_profiles=repos.token_profiles),
            ).asset_flow(
                window=args.window,
                limit=args.limit,
                scope=args.scope,
                now_ms=_now_ms(),
            )
            return 0, {"ok": True, "data": {"window": args.window, "scope": args.scope, **data}}

        if command == "account-alerts":
            items = AccountAlertService(signals).account_alerts(
                window=args.window,
                limit=args.limit,
                handles=_handle_set(args.handles),
                alert_type=args.alert_type,
            )
            return 0, {"ok": True, "data": {"window": args.window, "items": items}}

        if command == "account-quality":
            handles = sorted(_handle_set(args.handles))
            data = AccountQualityService(
                signals=signals,
                repository=AccountQualityRepository(signals.conn),
            ).account_quality_for_handles(handles)
            return 0, {"ok": True, "data": data}

        if command == "social-events":
            return (
                0,
                {
                    "ok": True,
                    "data": repos.social_event_extractions.recent(
                        window=args.window,
                        limit=args.limit,
                        handles=_handle_set(args.handles),
                        event_types=_csv_set(args.event_types),
                    ),
                },
            )

        if command == "enrichment-jobs":
            items = enrichment.list_jobs(limit=args.limit, status=args.status)
            return (
                0,
                {
                    "ok": True,
                    "data": {
                        "items": items,
                        "counts": enrichment.job_counts(),
                    },
                },
            )

        if command == "notification-deliveries":
            return (
                0,
                {
                    "ok": True,
                    "data": {
                        "items": notifications.list_deliveries(limit=args.limit, status=args.status),
                    },
                },
            )

    return 2, {"ok": False, "error": f"unknown read model command: {command}"}


def _handle_set(raw: str) -> set[str]:
    return {item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()}


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
