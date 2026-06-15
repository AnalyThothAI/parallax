from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
ALEMBIC_VERSIONS = SRC / "platform" / "db" / "alembic" / "versions"

FORBIDDEN_MACRO_COMPATIBILITY_TOKENS = (
    "macro_regime_v3",
    "macro_module_view_v1",
    "macro_module_view_v2",
    "macro_observation_series_active_generation",
    "macro_observation_series_generations",
    "macro_view_snapshots_compact",
    "macro_view_snapshot_generations",
    "macro_regime_snapshots",
)

RETIRED_CEX_RUN_SERVING_DOC_TOKENS = (
    "CREATE TABLE IF NOT EXISTS cex_oi_radar_runs",
    "Write `cex_oi_radar_runs`",
    "写 `cex_oi_radar_runs`",
    "Replace rows for a `run_id`",
    "按 `run_id` 重建",
)


def test_runtime_source_does_not_reference_retired_macro_serving_contracts() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if ALEMBIC_VERSIONS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains {token}"
            for token in FORBIDDEN_MACRO_COMPATIBILITY_TOKENS
            if token in text
        )

    assert offenders == []


def test_canonical_docs_do_not_republish_retired_cex_run_serving_instructions() -> None:
    docs = (
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "WORKERS.md",
        ROOT / "docs" / "CONTRACTS.md",
        ROOT / "docs" / "references" / "POSTGRES_PERFORMANCE.md",
    )
    offenders: list[str] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains retired CEX run-serving instruction {token!r}"
            for token in RETIRED_CEX_RUN_SERVING_DOC_TOKENS
            if token in text
        )

    assert offenders == []


def test_cex_binance_hard_cut_cleanup_runtime_surface_is_removed() -> None:
    removed_paths = [
        SRC / "domains/asset_market/services/cex_binance_hard_cut_cleanup.py",
        SRC / "domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py",
        ROOT / "tests/unit/test_cex_binance_hard_cut_cleanup.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []

    forbidden_runtime_tokens = {
        "cex-binance-hard-cut-cleanup",
        "cleanup_cex_binance_hard_cut",
        "CexBinanceHardCutAbort",
        "cex_binance_hard_cut_cleanup_repository",
    }
    scanned_paths = [
        SRC / "app/surfaces/cli/parser.py",
        SRC / "app/surfaces/cli/commands/ops.py",
        ROOT / "Makefile",
        ROOT / "tests/architecture/test_token_radar_sql_surface_inventory_contract.py",
    ]
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in scanned_paths
        for token in forbidden_runtime_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_macrodata_quote_runtime_lane_is_removed() -> None:
    removed_paths = [
        SRC / "integrations/macrodata/quote_provider.py",
        SRC / "app/runtime/provider_wiring/macrodata.py",
        ROOT / "tests/unit/test_macrodata_quote_provider.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []

    scanned_paths = [
        SRC / "integrations/macrodata/__init__.py",
        SRC / "app/runtime/provider_wiring/__init__.py",
        SRC / "app/runtime/provider_wiring/types.py",
        SRC / "app/runtime/providers_wiring.py",
        SRC / "app/runtime/bootstrap.py",
        SRC / "platform/config/settings.py",
        SRC / "app/surfaces/cli/commands/config.py",
        ROOT / "config.example.yaml",
    ]
    forbidden_tokens = (
        "MacrodataQuoteProvider",
        "stock_quote_provider",
        "macrodata_quote_timeout_seconds",
        "macrodata_quote_cache_ttl_seconds",
        "quote_timeout_seconds",
        "quote_cache_ttl_seconds",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in scanned_paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_macro_assets_daily_brief_requires_repository_contract_without_optional_loader() -> None:
    route_source = (SRC / "app/surfaces/api/routes_macro.py").read_text()

    forbidden_tokens = (
        'getattr(repos.macro_intel, "latest_macro_daily_brief", None)',
        "if loader is None:",
    )

    assert [token for token in forbidden_tokens if token in route_source] == []
    assert "repos.macro_intel.latest_macro_daily_brief" in route_source


def test_macro_crypto_derivatives_cex_board_requires_repository_contract_without_optional_repo() -> None:
    route_source = (SRC / "app/surfaces/api/routes_macro.py").read_text()

    forbidden_tokens = (
        'getattr(repos, "cex_oi_radar", None)',
        "if board_repo is None:",
    )

    assert [token for token in forbidden_tokens if token in route_source] == []
    assert "repos.cex_oi_radar.latest_board" in route_source


def test_macrodata_bundle_import_requires_session_unit_of_work_without_conn_transaction_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macrodata_bundle_importer.py").read_text()

    forbidden_tokens = (
        "_unit_of_work",
        "_require_transaction",
        'getattr(repos, "unit_of_work", None)',
        'getattr(getattr(repos, "conn", None), "transaction", None)',
        'getattr(repos, "require_transaction", None)',
        "repository session does not expose a transaction",
    )

    assert "repos.unit_of_work()" in source
    assert "repos.require_transaction(" in source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macro_sync_queue_summary_requires_repository_contract_without_optional_probe() -> None:
    source = (SRC / "domains/macro_intel/services/macro_sync_service.py").read_text()
    enqueue_source = source.split("def enqueue_due_windows", 1)[1].split("def run_claimed_window_once", 1)[0]
    forbidden_tokens = (
        "def _call_queue_summary",
        'getattr(repos.macro_intel, "macro_sync_queue_summary", None)',
        "if not callable(queue_summary):",
        "return {}",
    )

    assert "repos.macro_intel.macro_sync_queue_summary" in enqueue_source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback() -> (
    None
):
    runner_source = (SRC / "integrations/macrodata/runner.py").read_text()
    sync_service_source = (SRC / "domains/macro_intel/services/macro_sync_service.py").read_text()
    combined = f"{runner_source}\n{sync_service_source}"
    forbidden_tokens = (
        'getattr(settings, "macrodata_fred_api_key_env", None)',
        'getattr(settings, "macrodata_fred_api_key", None)',
        'getattr(settings, "providers", None)',
        'getattr(providers, "macrodata", None)',
        'getattr(macrodata, "fred_api_key_env", None)',
        'getattr(macrodata, "fred_api_key", None)',
        'getattr(settings, "macrodata_timeout_seconds", None)',
        'getattr(macro_sync, "macrodata_timeout_seconds", None)',
        "value if value is not None else 240.0",
        "DEFAULT_FRED_API_KEY_ENV",
        "_DEFAULT_FRED_API_KEY_ENV",
    )
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "env_name = settings.macrodata_fred_api_key_env" in runner_source
    assert "value = settings.macrodata_fred_api_key" in runner_source
    assert "value = settings.workers.macro_sync.macrodata_timeout_seconds" in runner_source
    assert "macrodata_fred_api_key_env_settings_required" in runner_source
    assert "macrodata_fred_api_key_settings_required" in runner_source
    assert "macrodata_timeout_settings_required" in runner_source
    assert "env_name = settings.macrodata_fred_api_key_env" in sync_service_source
    assert "macrodata_fred_api_key_env_settings_required" in sync_service_source


def test_macro_observation_series_refresh_requires_connection_transaction_without_nullcontext() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()

    forbidden_tokens = (
        "nullcontext",
        'getattr(conn, "transaction", None)',
        'hasattr(conn, "transaction")',
        "conn.transaction()",
    )

    assert "with _transaction_context(self.conn):" in source
    assert "macro_observation_series_refresh_transaction_required" in source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macro_projection_dirty_target_writes_require_connection_transaction_without_manual_commit() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    dirty_target_source = source.split("def claim_macro_projection_dirty_targets", 1)[1].split(
        "def latest_observations", 1
    )[0]

    forbidden_tokens = (
        "nullcontext",
        'getattr(conn, "transaction", None)',
        'hasattr(conn, "transaction")',
        "conn.transaction()",
        "self.conn.commit()",
    )

    assert "_macro_projection_dirty_target_transaction_context" in source
    assert "macro_projection_dirty_target_transaction_required" in source
    assert "with _macro_projection_dirty_target_transaction_context(self.conn):" in dirty_target_source
    assert [token for token in forbidden_tokens if token in dirty_target_source] == []


def test_macro_repository_write_counts_require_real_cursor_rowcount_without_defaults() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    forbidden_tokens = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        'getattr(cursor, "rowcount", None)',
        "if rowcount is None",
        "return len(targets)",
        "return len(rows)",
        'return bool(dict(row or {}).get("changed", False))',
    )
    required_tokens = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "def _single_rowcount(cursor: Any) -> int:",
        "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:",
        "macro_intel_repository_rowcount_required",
        "macro_intel_repository_rowcount_invalid",
        "return _single_rowcount(cursor) > 0",
        "return _cursor_rowcount(cursor)",
        "return _single_returning_changed(cursor, row)",
        "if count != (1 if row is not None else 0):",
    )

    assert [token for token in forbidden_tokens if token in source] == []
    for token in required_tokens:
        assert token in source
    assert source.count("return _single_returning_changed(cursor, row)") >= 2


def test_macro_sync_window_returning_writes_require_cursor_rowcount_match() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    enqueue_source = source.split("def enqueue_macro_sync_window", 1)[1].split(
        "def claim_macro_sync_window",
        1,
    )[0]
    claim_source = source.split("def claim_macro_sync_window", 1)[1].split(
        "def record_macro_sync_run",
        1,
    )[0]
    sync_window_source = enqueue_source + claim_source
    forbidden_tokens = (
        'return str(dict(row or {})["sync_window_id"])',
        "return dict(row) if row is not None else None",
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden_tokens if token in sync_window_source] == []
    assert "def _required_returning_row(" in source
    assert "def _optional_returning_row(" in source
    assert "_required_returning_row(cursor, row)" in enqueue_source
    assert "_optional_returning_row(cursor, row)" in claim_source


def test_macro_view_projection_worker_uses_session_transaction_without_worker_commits() -> None:
    source = (SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py").read_text()
    claimed_source = source.split("def _run_claimed_once", 1)[1].split("def _repository_session", 1)[0]

    forbidden_tokens = (
        "commit=True",
        "repos.conn.commit()",
        "conn.commit()",
        "nullcontext",
        'getattr(repos, "transaction", None)',
        "conn.transaction()",
    )

    assert "repos.transaction()" in source
    assert 'repos.require_transaction(operation="macro_view_projection")' in source
    assert "wake_payload" in source
    assert source.index("repos.transaction()") < source.index("claim_macro_projection_dirty_targets")
    assert "notify_macro_view_snapshot_updated" not in claimed_source
    assert [token for token in forbidden_tokens if token in source] == []
