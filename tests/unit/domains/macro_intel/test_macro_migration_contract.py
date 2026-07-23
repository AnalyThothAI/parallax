from pathlib import Path

from parallax.domains.macro_intel import _constants

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = (
    ROOT
    / "src"
    / "parallax"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260521_0080_macro_concept_key_hard_cut.py"
)
RUNTIME_DB_PERFORMANCE_HARD_CUT_MIGRATION = (
    ROOT
    / "src"
    / "parallax"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260527_0114_runtime_db_performance_hard_cut.py"
)
NEXT_RUNTIME_LIFECYCLE_HARD_CUT_MIGRATION = (
    ROOT
    / "src"
    / "parallax"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260527_0115_next_runtime_lifecycle_hard_cut.py"
)
MACRO_SYNC_FRESHNESS_CLAIM_ORDER_MIGRATION = (
    ROOT
    / "src"
    / "parallax"
    / "platform"
    / "db"
    / "alembic"
    / "versions"
    / "20260608_0153_macro_sync_freshness_claim_order.py"
)


def test_macro_concept_key_migration_backfills_historical_stooq_rows_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    expected_historical_stooq = {
        "stooq:spy.us": "asset:spy",
        "stooq:qqq.us": "asset:qqq",
        "stooq:iwm.us": "asset:iwm",
        "stooq:tlt.us": "asset:tlt",
        "stooq:hyg.us": "asset:hyg",
        "stooq:lqd.us": "asset:lqd",
        "stooq:gld.us": "asset:gld",
        "stooq:uso.us": "asset:uso",
        "stooq:btc.us": "crypto:btc",
        "stooq:eth.us": "crypto:eth",
        "stooq:dxy.us": "fx:dxy",
    }
    for historical_key, concept_key in expected_historical_stooq.items():
        assert f"WHEN '{historical_key}' THEN '{concept_key}'" in source

    assert "source_name = 'stooq'" in source
    assert "THEN 10" in source


def test_macro_hard_cut_constants_remove_legacy_projection_and_rule_catalogs() -> None:
    assert _constants.MACRO_EVIDENCE_PROJECTION_VERSION == "macro_evidence_v1"
    assert _constants.MACRO_MIN_CHART_POINTS == 2
    assert not hasattr(_constants, "MACRO_VIEW_PROJECTION_VERSION")
    assert not hasattr(_constants, "MACRO_MODULE_VIEW_VERSION")
    assert not hasattr(_constants, "MACRO_MODULE_IDS")
    assert not hasattr(_constants, "MACRO_REQUIRED_DELTA_POINTS")
    assert not hasattr(_constants, "MACRO_REQUIRED_STAT_POINTS")
    assert not hasattr(_constants, "MACRO_HISTORY_REQUIRED_CONCEPTS")
    assert not hasattr(_constants, "MACRO_HISTORY_REQUIRED_POINTS_BY_CONCEPT")
    assert not hasattr(_constants, "MACRO_CONCEPT_METADATA")
    assert not hasattr(_constants, "MACRO_CORE_CONCEPTS")


def test_macro_constants_map_sloos_credit_supply_and_demand_concepts() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRTSCILM"] == "credit:sloos_ci_large_tightening"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRTSCIS"] == "credit:sloos_ci_small_tightening"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRSDCILM"] == "credit:sloos_ci_large_demand"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRSDCIS"] == "credit:sloos_ci_small_demand"


def test_macro_constants_map_loan_quality_credit_concepts() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRBLACBS"] == "credit:business_delinquency"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:DRCLACBS"] == "credit:consumer_delinquency"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:CORBLACBS"] == "credit:business_charge_off"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:CORCACBS"] == "credit:consumer_charge_off"


def test_macro_constants_map_gdpnow_nowcast_concept() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:GDPNOW"] == "economy:gdp_nowcast"


def test_macro_constants_map_nyfed_repo_depth_concepts() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:BGCR"] == "liquidity:bgcr"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:TGCR"] == "liquidity:tgcr"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:SOFR_VOLUME"] == "liquidity:sofr_volume"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:BGCR_VOLUME"] == "liquidity:bgcr_volume"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:TGCR_VOLUME"] == "liquidity:tgcr_volume"


def test_macro_constants_map_nyfed_unsecured_funding_concepts() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:EFFR"] == "fed:effr"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:OBFR"] == "fed:obfr"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:EFFR_VOLUME"] == "fed:effr_volume"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["nyfed:OBFR_VOLUME"] == "fed:obfr_volume"
    assert (
        _constants.MACRO_PROVIDER_SERIES_SOURCE_PRIORITY["nyfed:EFFR"]
        > (_constants.MACRO_PROVIDER_SERIES_SOURCE_PRIORITY["fred:EFFR"])
    )


def test_macro_constants_map_bls_calendar_event_concepts() -> None:
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["official_calendar:bls_cpi_next"] == ("event:bls_cpi_next")
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["official_calendar:bls_employment_next"] == (
        "event:bls_employment_next"
    )
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["official_calendar:bls_ppi_next"] == ("event:bls_ppi_next")

    assert "event:bls_cpi_next" in _constants.MACRO_EVENT_CONCEPTS
    assert "event:bls_employment_next" in _constants.MACRO_EVENT_CONCEPTS
    assert "event:bls_ppi_next" in _constants.MACRO_EVENT_CONCEPTS


def test_macro_constants_map_treasury_auction_calendar_event_concepts() -> None:
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["treasury_auction:2y_next_auction_days"] == (
        "event:treasury_auction_2y_next"
    )
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["treasury_auction:10y_next_auction_days"] == (
        "event:treasury_auction_10y_next"
    )
    assert _constants.MACRO_EVENT_PROVIDER_SERIES_TO_CONCEPT["treasury_auction:30y_next_auction_days"] == (
        "event:treasury_auction_30y_next"
    )

    assert "event:treasury_auction_2y_next" in _constants.MACRO_EVENT_CONCEPTS
    assert "event:treasury_auction_10y_next" in _constants.MACRO_EVENT_CONCEPTS
    assert "event:treasury_auction_30y_next" in _constants.MACRO_EVENT_CONCEPTS


def test_macro_constants_map_mid_term_vix_futures_proxy() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["yahoo:VIXM"] == "asset:vixm"


def test_macro_constants_map_move_rates_volatility_proxy() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["yahoo:^MOVE"] == "vol:move"


def test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["cboe:VIX1D"] == "vol:vix1d"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["cboe:VIX9D"] == "vol:vix9d"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["cboe:VVIX"] == "vol:vvix"
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["cboe:SKEW"] == "vol:skew"


def test_macro_constants_map_average_hourly_earnings_labor_concept() -> None:
    assert _constants.MACRO_PROVIDER_SERIES_TO_CONCEPT["fred:CES0500000003"] == "labor:avg_hourly_earnings"


def test_macro_observation_series_contract_is_current_only_after_hard_cut() -> None:
    migration_sql = RUNTIME_DB_PERFORMANCE_HARD_CUT_MIGRATION.read_text(encoding="utf-8")

    assert "macro_observation_series_rows_compact" in migration_sql
    assert "observed_at TIMESTAMPTZ NOT NULL" in migration_sql
    assert "value_numeric DOUBLE PRECISION NOT NULL" in migration_sql
    assert "macro_observation_series_rows_compact_pkey" in migration_sql
    assert "PRIMARY KEY (projection_version, concept_key, observed_at)" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS macro_observation_series_publication_state" in migration_sql
    assert "DROP TABLE IF EXISTS macro_observation_series_active_generation" in migration_sql
    assert "DROP TABLE IF EXISTS macro_observation_series_generations" in migration_sql


def test_next_runtime_lifecycle_migration_compacts_macro_view_snapshots_to_current_only() -> None:
    migration_sql = _migration_text(NEXT_RUNTIME_LIFECYCLE_HARD_CUT_MIGRATION)
    compact_table = _create_table_block(migration_sql, "macro_view_snapshots_compact")
    normalized_sql = " ".join(migration_sql.split())

    assert "CREATE TABLE IF NOT EXISTS macro_view_snapshots_compact" in migration_sql
    assert "payload_hash TEXT NOT NULL" in compact_table
    assert "'macro-view:' || projection_version || ':' || 'current'" in migration_sql
    assert "|| ':current'" not in migration_sql
    assert "row_number() OVER" in migration_sql
    assert "PARTITION BY projection_version" in migration_sql
    assert "ORDER BY computed_at_ms DESC" in migration_sql
    assert "WHERE snapshot_rank = 1" in migration_sql
    assert "DROP TABLE macro_view_snapshots" in migration_sql
    assert "ALTER TABLE macro_view_snapshots_compact RENAME TO macro_view_snapshots" in migration_sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_view_snapshots_current" in migration_sql
    assert "CREATE INDEX IF NOT EXISTS idx_macro_view_snapshots_latest_current" in migration_sql
    assert "ON macro_view_snapshots(projection_version, computed_at_ms DESC)" in normalized_sql


def test_next_runtime_lifecycle_migration_adds_macro_projection_dirty_targets_seed() -> None:
    migration_sql = _migration_text(NEXT_RUNTIME_LIFECYCLE_HARD_CUT_MIGRATION)
    dirty_targets_table = _create_table_block(migration_sql, "macro_projection_dirty_targets")
    normalized_sql = " ".join(migration_sql.split())

    for column in (
        "projection_name TEXT NOT NULL",
        "projection_version TEXT NOT NULL",
        "target_kind TEXT NOT NULL",
        "target_id TEXT NOT NULL",
        "payload_hash TEXT NOT NULL",
        "dirty_reason TEXT NOT NULL",
        "source_watermark_ms BIGINT NOT NULL DEFAULT 0",
        "priority INTEGER NOT NULL DEFAULT 100",
        "due_at_ms BIGINT NOT NULL",
        "leased_until_ms BIGINT",
        "lease_owner TEXT",
        "attempt_count INTEGER NOT NULL DEFAULT 0",
        "last_error TEXT",
        "created_at_ms BIGINT NOT NULL",
        "updated_at_ms BIGINT NOT NULL",
    ):
        assert column in dirty_targets_table
    assert "PRIMARY KEY (projection_name, projection_version, target_kind, target_id)" in dirty_targets_table
    assert "INSERT INTO macro_projection_dirty_targets" in migration_sql
    assert "'macro_view'" in migration_sql
    assert "'macro_regime_v4'" in migration_sql
    assert "'current'" in migration_sql
    assert "ON CONFLICT (projection_name, projection_version, target_kind, target_id) DO UPDATE" in normalized_sql


def test_macro_workerspace_root_fix_backfills_hashes_with_runtime_hash_functions() -> None:
    migration_sql = _migration_text(
        ROOT
        / "src"
        / "parallax"
        / "platform"
        / "db"
        / "alembic"
        / "versions"
        / "20260528_0116_macro_workerspace_root_fix.py"
    )

    assert "macro_observation_fact_payload_hash(" in migration_sql
    assert "macro_series_current_row_payload_hash(" in migration_sql
    assert "'md5:'" not in migration_sql
    assert "md5(" not in migration_sql


def test_macro_sync_freshness_migration_deletes_bucketed_overlap_queue_and_reindexes_due_order() -> None:
    migration_sql = _migration_text(MACRO_SYNC_FRESHNESS_CLAIM_ORDER_MIGRATION)
    normalized_sql = " ".join(migration_sql.split())

    assert "DELETE FROM macro_sync_windows" in migration_sql
    assert "trigger_reason LIKE 'steady_overlap:%'" in migration_sql
    assert "status IN ('pending', 'retryable')" in migration_sql
    assert "DROP INDEX IF EXISTS idx_macro_sync_windows_due" in migration_sql
    assert (
        "ON macro_sync_windows(priority ASC, window_end DESC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)"
        in normalized_sql
    )


def _migration_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _create_table_block(text: str, table_name: str) -> str:
    start = text.index(f"CREATE TABLE IF NOT EXISTS {table_name}")
    end = text.index('"""', start)
    return text[start:end]
