from __future__ import annotations

import pytest

from scripts.audit_dedup.candidates import (
    AssetCandidate,  # noqa: F401 - imported to verify public API exists
    fetch_duplicate_groups,
)
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _insert_asset(cur, asset_id: str, symbol: str, first_seen_ms: int) -> None:
    cur.execute(
        """
        INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status, confidence,
                            primary_source, first_seen_at_ms, updated_at_ms)
        VALUES (%s, 'dex_token', %s, 'resolved', 0.95, 'test', %s, %s)
        """,
        (asset_id, symbol, first_seen_ms, first_seen_ms),
    )


def _insert_venue(cur, asset_id: str, venue_id: str, chain: str, address: str) -> None:
    cur.execute(
        """
        INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                                  is_active, confidence, created_at_ms, updated_at_ms)
        VALUES (%s, %s, 'dex', 'okx_dex', %s, %s, true, 0.9, 0, 0)
        """,
        (venue_id, asset_id, chain, address),
    )


def _insert_snapshot(
    cur, asset_id: str, venue_id: str, observed_ms: int, *, holders: int | None, liq: float | None, mcap: float | None
) -> None:
    cur.execute(
        """
        INSERT INTO asset_market_snapshots (snapshot_id, asset_id, venue_id, provider, observed_at_ms,
                                            holders, liquidity_usd, market_cap_usd, created_at_ms)
        VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)
        """,
        (f"snap:{asset_id}:{observed_ms}", asset_id, venue_id, observed_ms, holders, liq, mcap, observed_ms),
    )


def test_fetch_duplicate_groups_returns_only_duplicates_per_chain() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        _insert_asset(cur, "asset:dex:solana:a", "TROLL", 100)
        _insert_asset(cur, "asset:dex:solana:b", "TROLL", 200)
        _insert_asset(cur, "asset:dex:solana:c", "UNIQUE", 300)
        _insert_venue(cur, "asset:dex:solana:a", "venue:dex:solana:a", "solana", "AAA")
        _insert_venue(cur, "asset:dex:solana:b", "venue:dex:solana:b", "solana", "BBB")
        _insert_venue(cur, "asset:dex:solana:c", "venue:dex:solana:c", "solana", "CCC")
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 1000, holders=500, liq=10000.0, mcap=1.0e6)
        _insert_snapshot(cur, "asset:dex:solana:b", "venue:dex:solana:b", 1100, holders=100, liq=2000.0, mcap=5.0e5)
        conn.commit()

    groups = fetch_duplicate_groups(conn)

    assert len(groups) == 1
    (group,) = groups
    assert group.chain == "solana"
    assert group.symbol == "TROLL"
    assert sorted(c.asset_id for c in group.candidates) == [
        "asset:dex:solana:a",
        "asset:dex:solana:b",
    ]
    by_id = {c.asset_id: c for c in group.candidates}
    assert by_id["asset:dex:solana:a"].holders == 500
    assert by_id["asset:dex:solana:b"].holders == 100


def test_fetch_duplicate_groups_picks_latest_snapshot_per_asset() -> None:
    conn = connect_postgres_test()
    with conn.cursor() as cur:
        _insert_asset(cur, "asset:dex:solana:a", "TROLL", 100)
        _insert_asset(cur, "asset:dex:solana:b", "TROLL", 200)
        _insert_venue(cur, "asset:dex:solana:a", "venue:dex:solana:a", "solana", "AAA")
        _insert_venue(cur, "asset:dex:solana:b", "venue:dex:solana:b", "solana", "BBB")
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 1000, holders=10, liq=1.0, mcap=1.0)
        _insert_snapshot(cur, "asset:dex:solana:a", "venue:dex:solana:a", 2000, holders=999, liq=999.0, mcap=999.0)
        _insert_snapshot(cur, "asset:dex:solana:b", "venue:dex:solana:b", 1500, holders=1, liq=1.0, mcap=1.0)
        conn.commit()

    groups = fetch_duplicate_groups(conn)

    by_id = {c.asset_id: c for c in groups[0].candidates}
    assert by_id["asset:dex:solana:a"].holders == 999  # latest snapshot wins
