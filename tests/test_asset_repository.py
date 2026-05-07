from __future__ import annotations

from gmgn_twitter_intel.storage.asset_repository import AssetRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def open_asset_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    return conn, AssetRepository(conn)


def test_upsert_cex_instrument_creates_asset_alias_and_venue(tmp_path):
    conn, repo = open_asset_repo(tmp_path)
    try:
        result = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-USDT",
            base_symbol="btc",
            quote_symbol="USDT",
            observed_at_ms=1_700_000_000_000,
            source_payload_hash="payload-hash",
        )
        candidates = repo.candidates_for_symbol("BTC")
    finally:
        conn.close()

    assert result.asset["asset_type"] == "cex_asset"
    assert result.asset["canonical_symbol"] == "BTC"
    assert result.venue is not None
    assert result.venue["venue_type"] == "cex"
    assert result.venue["exchange"] == "okx"
    assert result.venue["inst_id"] == "BTC-USDT"
    assert candidates[0]["asset_id"] == result.asset["asset_id"]
    assert candidates[0]["venue_id"] == result.venue["venue_id"]


def test_candidates_for_symbol_prefers_usdt_spot_cex_venue(tmp_path):
    conn, repo = open_asset_repo(tmp_path)
    try:
        repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-AED",
            base_symbol="BTC",
            quote_symbol="AED",
            observed_at_ms=1_700_000_000_000,
            commit=False,
        )
        usdt = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            observed_at_ms=1_700_000_000_001,
            commit=True,
        )
        candidates = repo.candidates_for_symbol("BTC")
    finally:
        conn.close()

    assert candidates[0]["venue_id"] == usdt.venue["venue_id"]
    assert candidates[0]["quote_symbol"] == "USDT"


def test_candidates_for_ca_filters_by_chain_without_sql_parameter_mismatch(tmp_path):
    conn, repo = open_asset_repo(tmp_path)
    try:
        result = repo.upsert_dex_asset(
            chain="solana",
            address="Mirror111",
            symbol="MIRROR",
            observed_at_ms=1_700_000_000_000,
            provider="okx_dex",
        )
        candidates = repo.candidates_for_ca(chain="solana", address="Mirror111")
    finally:
        conn.close()

    assert [candidate["asset_id"] for candidate in candidates] == [result.asset["asset_id"]]
    assert candidates[0]["venue_id"] == result.venue["venue_id"]


def test_dex_asset_provider_symbol_survives_later_ca_only_upsert(tmp_path):
    conn, repo = open_asset_repo(tmp_path)
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    try:
        provider = repo.upsert_dex_asset(
            chain="solana",
            address=address,
            symbol="USDUC",
            observed_at_ms=1_700_000_000_000,
            provider="okx_dex",
            commit=False,
        )
        later_direct_ca = repo.upsert_dex_asset(
            chain="solana",
            address=address,
            symbol=address,
            observed_at_ms=1_700_000_060_000,
            provider="deterministic",
            commit=True,
        )
        candidates_for_address_as_symbol = repo.candidates_for_symbol(address)
    finally:
        conn.close()

    assert later_direct_ca.asset["asset_id"] == provider.asset["asset_id"]
    assert later_direct_ca.asset["canonical_symbol"] == "USDUC"
    assert later_direct_ca.asset["display_name"] == "USDUC"
    assert candidates_for_address_as_symbol == []
