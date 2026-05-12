from __future__ import annotations

import pytest

from scripts.audit_dedup.phase1_chain_normalize import run_phase1
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _insert_eth_asset(conn, asset_id: str, address: str, symbol: str, first_seen: int) -> None:
    venue_id = f"venue:dex:eth:{address.lower()}"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)""",
            (asset_id, symbol, first_seen, first_seen),
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES (%s, %s, 'dex', 'okx_dex', 'eth', %s, true, 0.9, 0, 0)""",
            (venue_id, asset_id, address),
        )
        cur.execute(
            """INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider,
               observed_at_ms, holders, liquidity_usd, market_cap_usd, created_at_ms)
               VALUES (%s, %s, %s, 'okx_dex', 1000, 100, 100.0, 100.0, 1000)""",
            (f"snap:{asset_id}", asset_id, venue_id),
        )
    conn.commit()


def _insert_ethereum_asset(conn, asset_id: str, address: str, symbol: str, first_seen: int) -> None:
    venue_id = f"venue:dex:ethereum:{address.lower()}"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)""",
            (asset_id, symbol, first_seen, first_seen),
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES (%s, %s, 'dex', 'okx_dex', 'ethereum', %s, true, 0.9, 0, 0)""",
            (venue_id, asset_id, address),
        )
    conn.commit()


def test_phase1_renames_eth_when_no_conflict() -> None:
    conn = connect_postgres_test()
    addr = "0xdef0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "FOO", 100)

    result = run_phase1(conn, apply=True)

    assert result.venue_rows_normalized == 1
    assert result.assets_renamed == 1
    assert result.assets_merged == 0

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='FOO'")
        assert [r[0] for r in cur.fetchall()] == [f"asset:dex:ethereum:{addr}"]
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == "ethereum"
        cur.execute("SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == 1


def test_phase1_merges_eth_into_existing_ethereum() -> None:
    conn = connect_postgres_test()
    addr = "0xabc0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "FOO", 100)
    _insert_ethereum_asset(conn, f"asset:dex:ethereum:{addr}", addr, "FOO", 200)

    result = run_phase1(conn, apply=True)

    assert result.assets_merged == 1
    assert result.assets_renamed == 0

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='FOO' ORDER BY asset_id")
        assert [r[0] for r in cur.fetchall()] == [f"asset:dex:ethereum:{addr}"]
        # snapshot reassigned
        cur.execute("SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id=%s", (f"asset:dex:ethereum:{addr}",))
        assert cur.fetchone()[0] == 1
        # eth asset removed
        cur.execute("SELECT COUNT(*) FROM assets WHERE asset_id=%s", (f"asset:dex:eth:{addr}",))
        assert cur.fetchone()[0] == 0


def test_phase1_lists_orphan_chains() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES ('asset:evm:xyz', 'dex_token', 'WEIRD', 'resolved', 0.5, 'test', 0, 0)"""
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES ('venue:evm:xyz', 'asset:evm:xyz', 'dex', 'okx_dex', 'evm_unknown', '0xff', true, 0.5, 0, 0)"""
        )
    conn.commit()

    result = run_phase1(conn, apply=True)

    assert result.orphan_chains == {"evm_unknown": 1}
    # untouched
    with conn.cursor() as cur:
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id='asset:evm:xyz'")
        assert cur.fetchone()[0] == "evm_unknown"


def test_phase1_dry_run_does_not_mutate() -> None:
    conn = connect_postgres_test()
    addr = "0xfff0000000000000000000000000000000000000"
    _insert_eth_asset(conn, f"asset:dex:eth:{addr}", addr, "BAR", 100)

    result = run_phase1(conn, apply=False)

    assert result.venue_rows_normalized == 1
    assert result.assets_renamed == 1
    with conn.cursor() as cur:
        cur.execute("SELECT chain FROM asset_venues WHERE asset_id=%s", (f"asset:dex:eth:{addr}",))
        assert cur.fetchone()[0] == "eth"  # not mutated
