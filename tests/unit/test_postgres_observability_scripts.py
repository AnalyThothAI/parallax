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
