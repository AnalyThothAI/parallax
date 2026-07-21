from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
API_VALIDATORS = SRC / "app" / "surfaces" / "api" / "validators.py"
CEX_ROUTES = SRC / "app" / "surfaces" / "api" / "routes_cex.py"
MACRO_ROUTES = SRC / "app" / "surfaces" / "api" / "routes_macro.py"
WS_ROUTES = SRC / "app" / "surfaces" / "api" / "ws.py"


def test_search_read_paths_do_not_reach_runtime_asset_market_providers() -> None:
    source = (SRC / "app/surfaces/api/routes_search.py").read_text()

    forbidden = (
        "runtime.providers",
        "cex_market",
        "dex_candle_market",
    )
    assert [token for token in forbidden if token in source] == []


def test_search_read_service_requires_explicit_query_boundaries_without_defaults() -> None:
    source = (SRC / "domains/token_intel/read_models/search_service.py").read_text()
    parser_source = (SRC / "app/surfaces/cli/parser.py").read_text()
    cli_source = (SRC / "app/surfaces/cli/commands/read_models.py").read_text()

    forbidden = (
        "limit: int =",
        "scope: str =",
        "window: str =",
        "WINDOW_MS.get(window",
        "max(0, int(limit))",
    )
    required = (
        "limit: int,",
        "scope: str,",
        "window: str,",
        "_watched_only(scope)",
        "WINDOW_MS[window]",
        "SearchScopeError",
        "SearchWindowError",
        "search_limit_required",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []
    assert 'search.add_argument("--window"' in parser_source
    assert "window=args.window" in cli_source


def test_search_event_query_limits_reject_runtime_int_repairs() -> None:
    query_source = (SRC / "domains/token_intel/queries/search_events_query.py").read_text()
    forbidden = (
        "max(0, int(route_limit))",
        "max(0, int(limit))",
    )
    required = (
        "search_events_route_limit_required",
        "search_events_target_limit_required",
        "search_events_target_page_limit_required",
    )

    assert [token for token in forbidden if token in query_source] == []
    assert [token for token in required if token not in query_source] == []


def test_api_limit_validators_reject_runtime_int_repairs() -> None:
    validators_source = API_VALIDATORS.read_text()
    search_routes_source = (SRC / "app/surfaces/api/routes_search.py").read_text()
    forbidden = (
        "max(0, min(int(value)",
        "max(1, _limit(posts_limit",
    )

    assert [token for token in forbidden if token in f"{validators_source}\n{search_routes_source}"] == []
    assert "invalid_limit" in validators_source
    assert '_positive_limit(posts_limit, maximum=50, field="posts_limit")' in search_routes_source


def test_news_page_query_limit_rejects_runtime_int_repairs() -> None:
    source = (SRC / "domains/news_intel/queries/news_page_query.py").read_text()

    assert "max(1, int(limit))" not in source
    assert "news_page_query_limit_required" in source


def test_search_or_symbol_resolution_uses_batched_keyset_sql() -> None:
    service_source = (SRC / "domains/token_intel/read_models/search_service.py").read_text()
    query_source = (SRC / "domains/token_intel/queries/search_events_query.py").read_text()

    forbidden_service = (
        "for symbol in or_symbols:",
        "self.search_query.resolve_targets(symbol_intent)",
    )
    required_service = (
        "self.search_query.resolve_symbols(or_symbols)",
        "return _dedupe_candidates(candidates)",
    )
    required_query = (
        "def resolve_symbols(self, symbols: list[str]) -> list[dict[str, Any]]:",
        "WITH input_symbols AS",
        "unnest(%s::text[]) WITH ORDINALITY",
        "distinct_symbols AS",
        "PARTITION BY distinct_symbols.symbol",
    )

    assert [token for token in forbidden_service if token in service_source] == []
    assert [token for token in required_service if token not in service_source] == []
    assert [token for token in required_query if token not in query_source] == []


def test_narrative_post_semantics_hydration_is_removed() -> None:
    repository_source = (SRC / "domains/narrative_intel/repositories/narrative_repository.py").read_text()
    read_model_source = (SRC / "domains/narrative_intel/read_models/narrative_read_model.py").read_text()
    route_source = (SRC / "app/surfaces/api/routes_search.py").read_text()

    forbidden = (
        "semantics_for_posts",
        "hydrate_target_posts",
        "token_mention_semantics",
    )

    assert [token for token in forbidden if token in repository_source] == []
    assert [token for token in forbidden if token in read_model_source] == []
    assert [token for token in forbidden if token in route_source] == []


def test_websocket_token_replay_uses_batched_keyset_sql() -> None:
    websocket_source = WS_ROUTES.read_text(encoding="utf-8")
    repository_source = (SRC / "domains/evidence/repositories/evidence_repository.py").read_text(encoding="utf-8")

    forbidden_ws = (
        "for chain, ca in client.cas:",
        "for symbol in client.symbols:",
        "recent_events(limit=per_filter_limit, ca=ca",
        "recent_events(limit=per_filter_limit, symbol=symbol",
    )
    required_ws = (
        "repos.evidence.recent_events_for_token_filters(",
        "per_filter_limit=per_filter_limit",
        "cas=client.cas",
        "symbols=client.symbols",
    )
    required_repository = (
        "def recent_events_for_token_filters(",
        "WITH input_filters AS",
        "unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY",
        "distinct_filters AS",
        "ROW_NUMBER() OVER",
        "PARTITION BY filters.filter_kind, filters.filter_chain, filters.filter_value",
        "event_rank <= %s",
    )

    assert [token for token in forbidden_ws if token in websocket_source] == []
    assert [token for token in required_ws if token not in websocket_source] == []
    assert [token for token in required_repository if token not in repository_source] == []


def test_token_target_read_services_require_valid_window_and_scope_without_fallbacks() -> None:
    service_paths = (
        SRC / "domains/token_intel/read_models/token_target_posts_service.py",
        SRC / "domains/token_intel/read_models/token_target_social_timeline_service.py",
    )

    for path in service_paths:
        source = path.read_text()
        forbidden = (
            "WINDOW_MS.get(window",
            'watched_only=scope == "matched"',
            "max(0, int(limit))",
        )
        required = (
            "_window_ms(window)",
            "_watched_only(scope)",
            "WINDOW_MS[window]",
            "WindowError",
            "ScopeError",
            "_required_nonnegative_int(limit,",
        )

        assert [token for token in forbidden if token in source] == []
        assert [token for token in required if token not in source] == []

    posts_source = (SRC / "domains/token_intel/read_models/token_target_posts_service.py").read_text()
    timeline_source = (SRC / "domains/token_intel/read_models/token_target_social_timeline_service.py").read_text()
    assert "token_target_posts_limit_required" in posts_source
    assert "token_target_social_timeline_limit_required" in timeline_source


def test_event_token_projection_requires_formal_resolution_fields_without_json_defaults() -> None:
    source = (SRC / "domains/token_intel/queries/event_token_projection_query.py").read_text()
    forbidden = (
        "import json",
        "_loads(",
        'str(row.get("resolution_id") or "")',
        'str(row.get("intent_id") or "")',
        'str(row.get("event_id") or "")',
        'str(row.get("resolution_status") or "")',
        '_loads(row.get("reason_codes_json"), [])',
        '_loads(row.get("candidate_ids_json"), [])',
        '_loads(row.get("lookup_keys_json"), [])',
    )
    required = (
        '_required_resolution_text(row, "resolution_id")',
        '_required_resolution_text(row, "intent_id")',
        '_required_resolution_text(row, "event_id")',
        '_required_resolution_text(row, "resolution_status")',
        '_required_resolution_list(row, "reason_codes_json")',
        '_required_resolution_list(row, "candidate_ids_json")',
        '_required_resolution_list(row, "lookup_keys_json")',
        "event_token_projection_required",
        "event_token_projection_invalid",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_watchlist_handle_overview_bounds_source_sample_without_repository_defaults() -> None:
    repository_source = (SRC / "domains/watchlist_intel/repositories/watchlist_intel_repository.py").read_text()
    service_source = (SRC / "domains/watchlist_intel/services/watchlist_read_service.py").read_text()
    route_source = (SRC / "app/surfaces/api/routes_watchlist.py").read_text()

    forbidden = (
        "limit: int = 500",
        "config: WatchlistReadWindowConfig | None = None",
        "config or WatchlistReadWindowConfig()",
        "def _handle_overview_counts",
        "MAX(events.received_at_ms)",
        "source_limit=max(1, int(self.config.overview_source_limit))",
        "cluster_limit=max(1, int(self.config.overview_cluster_limit))",
        "max(0, int(source_limit))",
        "max(0, int(cluster_limit))",
        "max(0, int(limit))",
    )
    required_repository = (
        "source_limit: int,",
        "cluster_limit: int,",
        "COUNT(*) AS source_event_count",
        "LIMIT %s",
        "parsed_source_limit + 1",
        "WITH input_handles AS",
        "WITH ORDINALITY",
        "latest_by_handle AS",
        "LEFT JOIN LATERAL",
        "ORDER BY events.received_at_ms DESC, events.event_id DESC",
        "recent_counts AS",
    )
    required_service = (
        "overview_source_limit: int",
        "overview_cluster_limit: int",
        "watchlist_window_days_required",
        "watchlist_overview_source_limit_required",
        "watchlist_overview_cluster_limit_required",
    )
    required_limit_contracts = (
        "watchlist_timeline_limit_required",
        "watchlist_source_limit_required",
        "watchlist_cluster_limit_required",
    )

    assert [token for token in forbidden if token in repository_source + service_source] == []
    assert [token for token in required_repository if token not in repository_source] == []
    assert [token for token in required_service if token not in service_source] == []
    assert [token for token in required_limit_contracts if token not in repository_source] == []
    assert "overview_source_limit=500" in route_source
    assert "overview_cluster_limit=500" in route_source


def test_api_scope_validator_rejects_invalid_scope_without_matched_fallback() -> None:
    source = API_VALIDATORS.read_text()
    forbidden = (
        'return value if value in SCOPES else "matched"',
        'else "matched"',
    )
    required = (
        "def _scope(value: str) -> str:",
        'raise ApiBadRequest("invalid_scope", field="scope")',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_cex_detail_api_requires_formal_query_identity_without_truthy_fallbacks() -> None:
    source = CEX_ROUTES.read_text(encoding="utf-8")
    route_body = source.split("def cex_detail(", maxsplit=1)[1].split("\n\ndef _cex_detail_target_query", maxsplit=1)[0]
    forbidden = (
        "if target_type and target_id:",
        "elif symbol:",
        "latest_snapshot(target_type=target_type",
        "latest_snapshot_by_market(\n                exchange=exchange",
        "native_market_id=symbol,",
    )
    required = (
        "target_query = _cex_detail_target_query(",
        "market_query = _cex_detail_market_query(",
        'raise ApiBadRequest("invalid_cex_detail_query", field="target_type")',
        'raise ApiBadRequest("invalid_cex_detail_query", field="target_id")',
        'raise ApiBadRequest("invalid_cex_detail_query", field="exchange")',
        'raise ApiBadRequest("invalid_cex_detail_query", field="symbol")',
        'raise ApiBadRequest("invalid_cex_detail_query", field="query")',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []
    assert route_body.index('raise ApiBadRequest("invalid_cex_detail_query", field="query")') < route_body.index(
        "with runtime.repositories() as repos:"
    )


def test_cex_radar_board_api_requires_formal_repository_payload_without_defaults() -> None:
    source = CEX_ROUTES.read_text(encoding="utf-8")
    forbidden = (
        'board.get("rows") or []',
        'payload.pop("score_components_json", None)',
        "components or {}",
    )
    required = (
        "_required_board_rows(board)",
        "_required_score_components_json(row)",
        "cex_oi_radar_board_rows_required",
        "cex_oi_radar_score_components_required",
        "cex_oi_radar_score_components_invalid",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_macro_api_public_snapshot_requires_formal_sections_without_defaults() -> None:
    source = MACRO_ROUTES.read_text(encoding="utf-8")
    forbidden = (
        '"panels": snapshot.get("panels_json") or {}',
        '"indicators": snapshot.get("indicators_json") or {}',
        '"triggers": snapshot.get("triggers_json") or []',
        '"data_gaps": snapshot.get("data_gaps_json") or []',
        '"source_coverage": snapshot.get("source_coverage_json") or {}',
        '"features": snapshot.get("features_json") or {}',
        '"chain": snapshot.get("chain_json") or {}',
        '"scenario": snapshot.get("scenario_json") or {}',
        '"scorecard": snapshot.get("scorecard_json") or {}',
    )
    required = (
        '_required_snapshot_mapping(snapshot, "panels_json")',
        '_required_snapshot_mapping(snapshot, "indicators_json")',
        '_required_snapshot_mapping(snapshot, "source_coverage_json")',
        '_required_snapshot_mapping(snapshot, "features_json")',
        '_required_snapshot_mapping(snapshot, "chain_json")',
        '_required_snapshot_mapping(snapshot, "scenario_json")',
        '_required_snapshot_mapping(snapshot, "scorecard_json")',
        '_required_snapshot_list(snapshot, "triggers_json")',
        '_required_snapshot_list(snapshot, "data_gaps_json")',
        "macro_view_snapshot_section_required",
        "macro_view_snapshot_section_invalid",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_ops_diagnostics_payload_requires_explicit_query_boundaries_without_defaults() -> None:
    source = (SRC / "app/runtime/ops_diagnostics.py").read_text()
    route_source = (SRC / "app/surfaces/api/routes_ops.py").read_text()
    payload_source = source.split("def ops_diagnostics_payload", 1)[1].split(
        "\n\ndef ops_queue_payload",
        1,
    )[0]
    forbidden = ("since_hours", "window", "scope")
    required = ("runtime: Any,", "now_ms: int | None = None,")

    assert [token for token in forbidden if token in payload_source] == []
    assert [token for token in required if token not in payload_source] == []
    assert "def ops_diagnostics(\n    request: Request,\n)" in route_source
    assert "ops_diagnostics_payload(\n        runtime,\n        now_ms=_now_ms(),\n    )" in route_source


def test_market_candles_read_model_has_no_provider_io() -> None:
    source = (SRC / "domains/asset_market/read_models/market_candles_service.py").read_text()

    forbidden = (
        "providers import MarketCandle",
        ".candles(",
        "token_candles(",
        "cex_market",
        "dex_candle_market",
    )
    assert [token for token in forbidden if token in source] == []


def test_stocks_radar_api_is_provider_free() -> None:
    route_source = (SRC / "app/surfaces/api/routes_radar.py").read_text()
    service_source = (SRC / "domains/token_intel/read_models/stocks_radar_service.py").read_text()

    assert "runtime.stock_quote_provider" not in route_source
    assert "quote_provider" not in service_source
    assert ".quote(" not in service_source
    assert "ThreadPoolExecutor" not in service_source
    assert "max(0, int(limit))" not in service_source
    assert "stocks_radar_limit_required" in service_source


def test_token_radar_route_does_not_synthesize_target_identity_for_narrative_hydration() -> None:
    route_source = (SRC / "app/surfaces/api/routes_radar.py").read_text()
    narrative_source = (SRC / "domains/narrative_intel/read_models/narrative_read_model.py").read_text()

    forbidden_route_tokens = (
        "_with_top_level_targets",
        "_row_with_top_level_target",
        "_strip_synthetic_targets",
        "_strip_synthetic_target",
        "_synthetic_target_type",
        "_synthetic_target_id",
    )
    required_narrative_tokens = (
        "def _target_identity(row: dict[str, Any]) -> tuple[str, str]:",
        'target = _dict(row.get("target"))',
        'str(target.get("target_type") or "")',
        'str(target.get("target_id") or "")',
    )

    assert [token for token in forbidden_route_tokens if token in route_source] == []
    assert [token for token in required_narrative_tokens if token not in narrative_source] == []
    assert 'row.get("target_type")' not in narrative_source
    assert 'row.get("target_id")' not in narrative_source


def test_stocks_radar_source_event_ids_are_bounded_in_sql_read_path() -> None:
    query_source = (SRC / "domains/token_intel/queries/stocks_radar_query.py").read_text()

    assert "ranked_mentions AS MATERIALIZED" in query_source
    assert "FILTER (WHERE event_rank <= %s)" in query_source
    assert "ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids" not in query_source


def test_macro_api_routes_do_not_reach_macrodata_providers() -> None:
    route_source = (SRC / "app/surfaces/api/routes_macro.py").read_text()

    forbidden = (
        "MacrodataBundleRunner",
        "history_bundle",
        "providers.macrodata",
        "runtime.provider_wiring.macrodata",
    )
    assert [token for token in forbidden if token in route_source] == []


def test_stocks_radar_docs_do_not_describe_request_time_quote_provider() -> None:
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text()
    contracts = (ROOT / "docs/CONTRACTS.md").read_text()

    forbidden = (
        "runtime stock_quote_provider",
        "runtime `stock_quote_provider`",
        "request-time `quote` snapshot",
        "quote_provider_unavailable",
    )
    combined = "\n".join((architecture, contracts))
    assert [token for token in forbidden if token in combined] == []


def test_backend_public_read_paths_do_not_import_network_clients() -> None:
    public_read_roots = (
        SRC / "app/surfaces/api",
        SRC / "domains",
    )
    read_path_parts = {
        ("app", "surfaces", "api"),
        ("read_models",),
        ("queries",),
    }
    forbidden = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "import aiohttp",
        "from aiohttp",
        "urllib.request",
    )

    violations: list[str] = []
    for root in public_read_roots:
        for path in root.rglob("*.py"):
            rel_parts = path.relative_to(SRC).parts
            if not any(_contains_parts(rel_parts, parts) for parts in read_path_parts):
                continue
            source = path.read_text()
            hits = [token for token in forbidden if token in source]
            if hits:
                violations.append(f"{path.relative_to(ROOT)} imports network clients: {hits}")

    assert violations == []


def test_backend_public_read_paths_do_not_import_provider_wiring() -> None:
    public_read_roots = (
        SRC / "app/surfaces/api",
        SRC / "domains",
    )
    read_path_parts = {
        ("app", "surfaces", "api"),
        ("read_models",),
        ("queries",),
    }
    forbidden = (
        "parallax.integrations",
        "provider_wiring",
        "wire_providers",
        "runtime.providers",
        'getattr(runtime, "providers"',
        "stock_quote_provider",
    )

    violations: list[str] = []
    for root in public_read_roots:
        for path in root.rglob("*.py"):
            rel_parts = path.relative_to(SRC).parts
            if not any(_contains_parts(rel_parts, parts) for parts in read_path_parts):
                continue
            source = path.read_text()
            hits = [token for token in forbidden if token in source]
            if hits:
                violations.append(f"{path.relative_to(ROOT)} reaches provider wiring: {hits}")

    assert violations == []


def test_account_quality_read_model_service_has_no_backfill_write_path() -> None:
    source = (SRC / "domains/account_quality/read_models/account_quality_service.py").read_text()

    forbidden = (
        "def backfill_",
        ".upsert_",
        ".insert_",
        "insert_quality_snapshot",
        ".commit(",
    )
    assert [token for token in forbidden if token in source] == []


def test_domain_read_model_modules_do_not_own_write_or_maintenance_paths() -> None:
    forbidden = (
        "def backfill_",
        "def rebuild_",
        "def repair_",
        "def sync_",
        "def prune_",
        "def cleanup_",
        ".upsert_",
        ".insert_",
        ".delete_",
        ".commit(",
        ".rollback(",
        "conn.execute(",
        "FOR UPDATE",
        "SKIP LOCKED",
        "pg_notify",
        "NOTIFY ",
    )

    violations: list[str] = []
    for path in (SRC / "domains").glob("*/read_models/*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text()
        hits = [token for token in forbidden if token in source]
        if hits:
            violations.append(f"{path.relative_to(ROOT)} owns write/maintenance tokens: {hits}")

    assert violations == []


def test_account_quality_public_read_paths_use_read_service_not_repository() -> None:
    paths = (
        SRC / "app/surfaces/api/routes_events.py",
        SRC / "app/surfaces/api/routes_notifications.py",
        SRC / "app/surfaces/cli/commands/read_models.py",
    )

    violations: list[str] = []
    for path in paths:
        source = path.read_text()
        hits = [
            token
            for token in (
                "parallax.domains.account_quality.repositories",
                "AccountQualityRepository",
                "profiles_by_handles",
            )
            if token in source
        ]
        if hits:
            violations.append(f"{path.relative_to(ROOT)} bypasses account-quality read service: {hits}")

    assert violations == []


def test_account_quality_multi_handle_reads_use_batched_keyset_sql() -> None:
    service_source = (SRC / "domains/account_quality/read_models/account_quality_service.py").read_text()
    repository_source = (SRC / "domains/account_quality/repositories/account_quality_repository.py").read_text()

    forbidden = (
        "for handle in unique_handles]",
        "return [self.account_quality(handle) for handle in handles]",
    )
    required_service = (
        "self.repository.accounts_quality(unique_handles)",
        "def _unique_handles(handles: list[str]) -> list[str]:",
    )
    required_repository = (
        "def accounts_quality(self, handles: list[str]) -> list[dict[str, Any]]:",
        "WITH input_handles AS",
        "WITH ORDINALITY",
        "ROW_NUMBER() OVER (",
        "PARTITION BY stats.handle",
        "stat_rank <= 50",
        "PARTITION BY snapshots.handle",
        "snapshot_rank <= 20",
    )

    assert [token for token in forbidden if token in service_source or token in repository_source] == []
    assert [token for token in required_service if token not in service_source] == []
    assert [token for token in required_repository if token not in repository_source] == []


def test_account_quality_architecture_declares_read_write_boundary() -> None:
    source = (SRC / "domains/account_quality/ARCHITECTURE.md").read_text()
    global_architecture = (ROOT / "docs/ARCHITECTURE.md").read_text()

    required = (
        "AccountQualityBackfillService",
        "AccountQualityService",
        "account_profiles",
        "account_token_call_stats",
        "account_quality_snapshots",
        "ops-only",
        "There is no long-running Account Quality worker today.",
        "must not expose backfill, repair, upsert, insert, or commit paths",
    )
    assert [token for token in required if token not in source] == []
    assert "src/parallax/domains/account_quality/ARCHITECTURE.md" in global_architecture


def test_account_quality_backfill_uses_connection_transaction_without_manual_commit_fallback() -> None:
    source = (SRC / "domains/account_quality/services/account_quality_backfill_service.py").read_text()

    forbidden = (
        "self.repository.conn.commit()",
        "nullcontext",
        'getattr(self.repository.conn, "transaction", None)',
        'getattr(conn, "transaction", None)',
    )
    assert [token for token in forbidden if token in source] == []
    assert "limit: int =" not in source
    assert "with _transaction(self.repository.conn):" in source
    assert "account_quality_backfill_transaction_required" in source


def test_account_alert_read_service_requires_explicit_window_and_limit_without_defaults() -> None:
    source = (SRC / "domains/account_quality/read_models/account_alert_service.py").read_text()
    forbidden = (
        'window: str = "24h"',
        "window: str =",
        "limit: int = 50",
        "limit: int =",
    )

    assert [token for token in forbidden if token in source] == []
    assert "window: str," in source
    assert "limit: int," in source


def test_account_quality_repository_writes_use_connection_transaction_without_manual_commit_fallback() -> None:
    source = (SRC / "domains/account_quality/repositories/account_quality_repository.py").read_text()

    forbidden = (
        "self.conn.commit()",
        'getattr(self.conn, "transaction", None)',
        "return nullcontext()",
    )
    assert "def _run_repository_write" in source
    assert "account_quality_repository_transaction_required" in source
    assert source.count("_run_repository_write(self.conn, commit,") == 4
    assert [token for token in forbidden if token in source] == []


def test_news_source_status_uses_static_provider_contract_not_runtime_provider_object() -> None:
    source = (SRC / "app/surfaces/api/routes_news.py").read_text()

    forbidden = (
        'getattr(runtime, "providers"',
        "runtime.providers",
        "_registry",
        "feed_client",
    )
    required = (
        "RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES",
        "_provider_capabilities(",
        "_source_hygiene(",
    )
    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def _contains_parts(path_parts: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    width = len(needle)
    return any(path_parts[index : index + width] == needle for index in range(len(path_parts) - width + 1))
