from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_powa_configure_script_sets_bounded_history_and_does_not_print_secrets() -> None:
    script = (ROOT / "scripts" / "powa_configure.sh").read_text(encoding="utf-8")

    assert "-d postgres" in script
    assert "CREATE DATABASE powa" in script
    assert "\\gexec" in script
    assert "CREATE EXTENSION IF NOT EXISTS powa CASCADE" in script
    assert "powa_servers" in script
    assert "ALTER SYSTEM SET powa.coalesce = '5'" in script
    assert "ALTER SYSTEM SET powa.frequency = '5min'" in script
    assert "pg_reload_conf()" in script
    assert "frequency = 300" in script
    assert "powa_coalesce = 5" in script
    assert "retention = interval '7 days'" in script
    assert "powa_take_snapshot(0)" in script
    assert "generate_series(1, :snapshot_count)" in script
    assert "powa_statements_history_current" in script
    assert "powa_statements_history" in script
    assert "RAISE EXCEPTION 'powa_statements_history has no coalesced local-server statement data'" in script
    assert "RAISE EXCEPTION 'PoWA has no local-server statement data'" in script
    assert "POSTGRES_PASSWORD" not in script
    assert "postgres_password" not in script
    assert "cat " not in script


def test_powa_postgres_image_bootstraps_required_database() -> None:
    dockerfile = (ROOT / "ops" / "postgres" / "Dockerfile").read_text(encoding="utf-8")
    bootstrap = (ROOT / "ops" / "postgres" / "init" / "01-powa.sql").read_text(encoding="utf-8")

    assert "COPY ops/postgres/init/ /docker-entrypoint-initdb.d/" in dockerfile
    assert "CREATE DATABASE powa" in bootstrap
    assert "WHERE datname = 'powa'" in bootstrap
    assert "\\connect powa" in bootstrap
    assert "CREATE EXTENSION IF NOT EXISTS powa CASCADE" in bootstrap
    assert "POSTGRES_PASSWORD" not in bootstrap
    assert "postgres_password" not in bootstrap


def test_runtime_performance_check_prints_read_only_lifecycle_report() -> None:
    script = (ROOT / "scripts" / "runtime_performance_root_fix_check.sh").read_text(encoding="utf-8")

    assert "== postgres observability extensions ==" in script
    assert "pg_extension" in script
    assert "pg_stat_statements" in script
    assert "pg_stat_kcache" in script
    assert "pg_qualstats" in script
    assert "pg_wait_sampling" in script
    assert "== postgres lifecycle report ==" in script
    assert "psql_cmd --csv -c" in script
    assert "pg_stat_user_tables" in script
    assert "pg_total_relation_size(relid)" in script
    assert "table_name" in script
    assert "total_bytes" in script
    assert "live_rows" in script
    assert "dead_rows" in script
    assert "last_analyze" in script
    assert "retention_class" in script
    assert "recommended_action" in script
    assert "raw_frames" in script
    assert "events" in script
    assert "enriched_events" in script
    assert "token_radar_rank_source_events" in script
    assert "token_radar_current_rows" in script
    assert "token_radar_publication_state" in script
    assert "token_radar_snapshot_audit_%" not in script
    assert "token_radar_rank_history_%" not in script
    assert "hot compact rank/read path" in script
    assert "selected-row hydrate" in script
    assert "cold audit/history" in script
    assert "DELETE FROM" not in script
    assert "DROP " not in script
    assert "DETACH" not in script
    assert "VACUUM" not in script
    assert "pg_stat_statements_reset" not in script
    assert "pg_stat_reset" not in script


def test_runtime_performance_check_hard_gates_runtime_sql_fingerprints() -> None:
    script = (ROOT / "scripts" / "runtime_performance_root_fix_check.sh").read_text(encoding="utf-8")

    assert "TOKEN_RADAR_EVENT_ID_POPULATE_MIN_CALLS" in script
    assert "source_event_ids_json" in script
    assert "requested_event_ids" in script
    assert "jsonb_array_elements_text" in script
    assert "token_intents.event_id = requested_event_ids.source_event_id" in script
    assert "INSERT INTO token_radar_rank_source_events" in script

    assert "OLD_TOKEN_RADAR_SOURCE_POPULATE_CALLS_BEFORE" in script
    assert "query NOT ILIKE '%source_event_ids_json%'" in script
    assert "query NOT ILIKE '%requested_event_ids%'" in script

    assert "source_payload_hash IS NULL" in script
    assert "query ILIKE '%count(*)%'" in script

    assert "PULSE_TARGET_WIDE_TIMELINE_CALLS_BEFORE" in script
    assert "pulse_candidate target-wide timeline_rows/WITH matched fingerprint" in script
    assert "FROM token_intent_resolutions tir" in script
    assert "JOIN events ON events.event_id = tir.event_id" in script
    assert "ORDER BY received_at_ms DESC, event_id DESC" in script
    assert "query NOT ILIKE '%requested_events%'" in script

    assert "assert_zero_new_or_cumulative_calls" in script
    assert 'stale equity fetch runs" "${stale_equity_fetch_runs}"' not in script
    assert "top sql token radar share percent" not in script


def test_testcontainers_use_observability_postgres_image() -> None:
    helper = (ROOT / "tests" / "postgres_observability_container.py").read_text(encoding="utf-8")

    assert "parallax-postgres-observability:18" in helper
    assert 'ops" / "postgres" / "Dockerfile' in helper
    assert "shared_preload_libraries=pg_stat_statements,pg_stat_kcache,pg_qualstats,pg_wait_sampling" in helper

    for path in (
        ROOT / "tests" / "integration" / "conftest.py",
        ROOT / "tests" / "e2e" / "conftest.py",
        ROOT / "tests" / "golden" / "conftest.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert "observability_postgres_container(PostgresContainer)" in text
        assert "postgres:16-alpine" not in text
