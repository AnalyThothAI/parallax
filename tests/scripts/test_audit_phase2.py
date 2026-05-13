from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.audit_dedup.phase2_dedup import Phase2Config, run_phase2
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    prepare_postgres_database()


def _setup_troll(conn) -> None:
    rows = [
        ("asset:dex:solana:a", 100, "AAA", 52267, 3_100_000.0, 51_000_000.0),
        ("asset:dex:solana:b", 200, "BBB", 134, 22_883.0, 94_741_531.0),
        ("asset:dex:solana:c", 300, "CCC", 151, 25_896.0, 61_445_341.0),
    ]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, holders, liq, mcap in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
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
                   VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)""",
                (f"snap:{asset_id}", asset_id, venue_id, 1000, holders, liq, mcap, 1000),
            )
    conn.commit()


class _StubArbiter:
    def arbitrate(self, *, chain, symbol, candidates):
        raise AssertionError("external arbiter should not be called in this fixture")


def test_phase2_dry_run_picks_in_db_winner_without_mutation() -> None:
    conn = connect_postgres_test()
    _setup_troll(conn)

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_StubArbiter(),
        apply=False,
    )

    assert summary.assets_kept == 1
    assert summary.assets_dropped == 2
    assert summary.in_db_winners == 1
    decision = summary.decisions[0]
    assert decision.winner_id == "asset:dex:solana:a"
    assert set(decision.loser_ids) == {"asset:dex:solana:b", "asset:dex:solana:c"}

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 3  # not mutated


def test_phase2_apply_drops_losers() -> None:
    conn = connect_postgres_test()
    _setup_troll(conn)

    run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_StubArbiter(),
        apply=True,
    )

    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='TROLL' ORDER BY asset_id")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:a"]
        cur.execute("SELECT COUNT(*) FROM asset_venues WHERE asset_id IN ('asset:dex:solana:b','asset:dex:solana:c')")
        assert cur.fetchone()[0] == 0  # CASCADE
        cur.execute(
            "SELECT COUNT(*) FROM asset_market_snapshots WHERE asset_id IN ('asset:dex:solana:b','asset:dex:solana:c')"
        )
        assert cur.fetchone()[0] == 0  # CASCADE


@dataclass(frozen=True, slots=True)
class _ArbiterResultStub:
    winner_id: str | None
    source: str
    external_address: str | None


class _ArbiterHittingOkx:
    def arbitrate(self, *, chain, symbol, candidates):
        return _ArbiterResultStub(winner_id="asset:dex:solana:b", source="okx_dex", external_address="BBB")


def test_phase2_apply_uses_external_when_threshold_fails() -> None:
    conn = connect_postgres_test()
    rows = [
        ("asset:dex:solana:a", 100, "AAA", 50, 100.0, 1.0),
        ("asset:dex:solana:b", 200, "BBB", 30, 50.0, 1.0),
    ]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, holders, liq, mcap in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'NOPE', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
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
                   VALUES (%s, %s, %s, 'okx_dex', %s, %s, %s, %s, %s)""",
                (f"snap:{asset_id}", asset_id, venue_id, 1000, holders, liq, mcap, 1000),
            )
    conn.commit()

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_ArbiterHittingOkx(),
        apply=True,
    )

    assert summary.external_winners == 1
    assert summary.external_okx_hits == 1
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets WHERE canonical_symbol='NOPE'")
        assert [r[0] for r in cur.fetchall()] == ["asset:dex:solana:b"]


class _ArbiterNoHit:
    def arbitrate(self, *, chain, symbol, candidates):
        return _ArbiterResultStub(winner_id=None, source="none", external_address=None)


def test_phase2_apply_group_drops_when_external_no_hit() -> None:
    conn = connect_postgres_test()
    rows = [("asset:dex:bsc:a", 100, "AAA", 50, 100.0)]
    with conn.cursor() as cur:
        for asset_id, first_seen, addr, _holders, _liq in rows:
            cur.execute(
                """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
                   confidence, primary_source, first_seen_at_ms, updated_at_ms)
                   VALUES (%s, 'dex_token', 'TROLL', 'resolved', 0.95, 'test', %s, %s)""",
                (asset_id, first_seen, first_seen),
            )
            venue_id = f"venue:dex:bsc:{addr.lower()}"
            cur.execute(
                """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
                   is_active, confidence, created_at_ms, updated_at_ms)
                   VALUES (%s, %s, 'dex', 'okx_dex', 'bsc', %s, true, 0.9, 0, 0)""",
                (venue_id, asset_id, addr),
            )
        # need a second asset to form a duplicate group
        cur.execute(
            """INSERT INTO assets (asset_id, asset_type, canonical_symbol, identity_status,
               confidence, primary_source, first_seen_at_ms, updated_at_ms)
               VALUES ('asset:dex:bsc:b', 'dex_token', 'TROLL', 'resolved', 0.95, 'test', 200, 200)"""
        )
        cur.execute(
            """INSERT INTO asset_venues (venue_id, asset_id, venue_type, provider, chain, address,
               is_active, confidence, created_at_ms, updated_at_ms)
               VALUES ('venue:dex:bsc:bbb', 'asset:dex:bsc:b', 'dex', 'okx_dex', 'bsc', 'BBB', true, 0.9, 0, 0)"""
        )
    conn.commit()

    summary = run_phase2(
        conn,
        config=Phase2Config(threshold_holders=200, threshold_liq_usd=5000.0),
        external_arbiter=_ArbiterNoHit(),
        apply=True,
    )

    assert summary.no_real_token_groups == 1
    assert summary.assets_kept == 0
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM assets WHERE canonical_symbol='TROLL'")
        assert cur.fetchone()[0] == 0
