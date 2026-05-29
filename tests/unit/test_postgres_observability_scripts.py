from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_powa_configure_script_sets_bounded_history_and_does_not_print_secrets() -> None:
    script = (ROOT / "scripts" / "powa_configure.sh").read_text(encoding="utf-8")

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


def test_runtime_performance_check_prints_read_only_lifecycle_report() -> None:
    script = (ROOT / "scripts" / "runtime_performance_root_fix_check.sh").read_text(encoding="utf-8")

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
