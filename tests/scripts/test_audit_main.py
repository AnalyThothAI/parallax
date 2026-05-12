from __future__ import annotations

from pathlib import Path

import pytest

import scripts.audit_duplicate_tokens as cli
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _seed_troll(conn) -> None:
    rows = [
        ("asset:dex:solana:keep", "KKK", 52267, 3_100_000.0),
        ("asset:dex:solana:drop", "DDD", 134, 22_883.0),
    ]
    with conn.cursor() as cur:
        for asset_id, addr, holders, liq in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', 0, 0)""",
                (asset_id,),
            )
            venue_id = f"venue:dex:solana:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'solana', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
            cur.execute(
                """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
                   observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
                   VALUES (%s, %s, %s, 'okx_dex', 1000, %s, %s, 1.0, 1000)""",
                (f"snap:{asset_id}", asset_id, venue_id, holders, liq),
            )
    conn.commit()


def test_main_dry_run_writes_report_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = connect_postgres_test()
    _seed_troll(conn)

    monkeypatch.setattr(cli, "_open_connection", lambda: conn)
    monkeypatch.setattr(cli, "_build_external_arbiter", lambda *args, **kwargs: _FailingArbiter())

    report_path = tmp_path / "report.md"
    rc = cli.main([
        "--dry-run", "--report", str(report_path),
        "--threshold-holders", "200", "--threshold-liq-usd", "5000",
        "--no-external",
    ])

    assert rc == 0
    text = report_path.read_text(encoding="utf-8")
    assert "solana / TROLL" in text
    assert "KEEP" in text and "asset:dex:solana:keep" in text

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 2  # untouched


def test_main_apply_drops_losers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = connect_postgres_test()
    _seed_troll(conn)

    monkeypatch.setattr(cli, "_open_connection", lambda: conn)

    rc = cli.main([
        "--apply", "--report", str(tmp_path / "report.md"),
        "--no-external",
    ])

    assert rc == 0
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='TROLL'")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:keep"]


class _FailingArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        raise AssertionError("should not be reached with --no-external")
