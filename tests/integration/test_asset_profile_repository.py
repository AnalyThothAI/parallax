from __future__ import annotations

import pytest

from parallax.domains.asset_market.repositories.asset_profile_repository import (
    GMGN_DEX_PROFILE_PROVIDER,
    AssetProfileRepository,
)
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

READY_REFRESH_MS = 21_600_000
ERROR_REFRESH_MS = 900_000


def test_ready_profile_round_trips_by_asset_id(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        asset_id = _insert_asset(conn)
        repo = AssetProfileRepository(conn)

        repo.upsert_ready_profile(
            asset_id=asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            symbol="sat",
            name="Sato The Dog",
            logo_url="https://assets.example/sat.png",
            banner_url="https://assets.example/sat-banner.png",
            website_url="https://sat.example",
            twitter_username="sattoken",
            twitter_url="https://x.com/sattoken",
            telegram_url="https://t.me/sattoken",
            gmgn_url="https://gmgn.ai/eth/token/0x999b49c0d1612e619a4a4f6280733184da025108",
            geckoterminal_url="https://www.geckoterminal.com/eth/pools/0xpool",
            description="Official profile from GMGN.",
            raw_payload={"links": {"twitter": "https://x.com/sattoken"}},
            observed_at_ms=1_778_000_000_000,
            next_refresh_at_ms=1_778_000_000_000 + READY_REFRESH_MS,
        )

        rows = repo.profiles_for_asset_ids([asset_id])
    finally:
        conn.close()

    assert rows[asset_id]["status"] == "ready"
    assert rows[asset_id]["symbol"] == "sat"
    assert rows[asset_id]["name"] == "Sato The Dog"
    assert rows[asset_id]["logo_url"] == "https://assets.example/sat.png"
    assert rows[asset_id]["twitter_username"] == "sattoken"
    assert rows[asset_id]["raw_payload_json"] == {"links": {"twitter": "https://x.com/sattoken"}}
    assert rows[asset_id]["observed_at_ms"] == 1_778_000_000_000
    assert rows[asset_id]["next_refresh_at_ms"] == 1_778_000_000_000 + READY_REFRESH_MS
    assert rows[asset_id]["last_error"] is None


def test_status_error_row_round_trips_and_clears_profile_fields(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        asset_id = _insert_asset(conn)
        repo = AssetProfileRepository(conn)

        repo.upsert_ready_profile(
            asset_id=asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            symbol="SAT",
            name="Sato The Dog",
            logo_url="https://assets.example/sat.png",
            banner_url=None,
            website_url="https://sat.example",
            twitter_username="sattoken",
            twitter_url="https://x.com/sattoken",
            telegram_url=None,
            gmgn_url=None,
            geckoterminal_url=None,
            description="Profile before provider error.",
            raw_payload={"status": "ready"},
            observed_at_ms=1_778_000_000_000,
            next_refresh_at_ms=1_778_000_000_000 + READY_REFRESH_MS,
        )
        repo.upsert_status(
            asset_id=asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            status="error",
            observed_at_ms=1_778_000_030_000,
            next_refresh_at_ms=1_778_000_030_000 + ERROR_REFRESH_MS,
            last_error="rate limited",
            raw_payload={"error": "429"},
        )

        row = repo.profiles_for_asset_ids([asset_id])[asset_id]
    finally:
        conn.close()

    assert row["status"] == "error"
    assert row["symbol"] is None
    assert row["name"] is None
    assert row["logo_url"] is None
    assert row["website_url"] is None
    assert row["description"] is None
    assert row["raw_payload_json"] == {"error": "429"}
    assert row["observed_at_ms"] == 1_778_000_030_000
    assert row["next_refresh_at_ms"] == 1_778_000_030_000 + ERROR_REFRESH_MS
    assert row["last_error"] == "rate limited"


def test_ready_profile_normalizes_blank_strings_to_none(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        asset_id = _insert_asset(conn)
        repo = AssetProfileRepository(conn)

        repo.upsert_ready_profile(
            asset_id=asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            symbol="  ",
            name="",
            logo_url="\t",
            banner_url="",
            website_url="",
            twitter_username=" ",
            twitter_url="",
            telegram_url=None,
            gmgn_url="",
            geckoterminal_url="",
            description="",
            raw_payload={},
            observed_at_ms=1_778_000_000_000,
            next_refresh_at_ms=1_778_000_000_000 + READY_REFRESH_MS,
        )

        row = repo.profiles_for_asset_ids([asset_id])[asset_id]
    finally:
        conn.close()

    for key in (
        "symbol",
        "name",
        "logo_url",
        "banner_url",
        "website_url",
        "twitter_username",
        "twitter_url",
        "telegram_url",
        "gmgn_url",
        "geckoterminal_url",
        "description",
    ):
        assert row[key] is None


def test_ready_profile_strips_nul_bytes_from_text_and_raw_payload(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        asset_id = _insert_asset(conn)
        repo = AssetProfileRepository(conn)

        repo.upsert_ready_profile(
            asset_id=asset_id,
            provider=GMGN_DEX_PROFILE_PROVIDER,
            symbol="ZEC\x00\x00",
            name="Zero\x00Coin",
            logo_url=None,
            banner_url=None,
            website_url=None,
            twitter_username=None,
            twitter_url=None,
            telegram_url=None,
            gmgn_url=None,
            geckoterminal_url=None,
            description="profile\x00 text",
            raw_payload={"symbol\x00": "ZEC\x00", "links": ["https://x.example/\x00zec"]},
            observed_at_ms=1_778_000_000_000,
            next_refresh_at_ms=1_778_000_000_000 + READY_REFRESH_MS,
        )

        row = repo.profiles_for_asset_ids([asset_id])[asset_id]
    finally:
        conn.close()

    assert row["symbol"] == "ZEC"
    assert row["name"] == "ZeroCoin"
    assert row["description"] == "profile text"
    assert row["raw_payload_json"] == {"symbol": "ZEC", "links": ["https://x.example/zec"]}


def test_profiles_for_asset_ids_empty_input_returns_empty_dict():
    repo = AssetProfileRepository(conn=None)

    assert repo.profiles_for_asset_ids([]) == {}


def test_upsert_status_rejects_ready_status():
    repo = AssetProfileRepository(conn=None)

    with pytest.raises(ValueError, match="non-ready"):
        repo.upsert_status(
            asset_id="asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
            provider=GMGN_DEX_PROFILE_PROVIDER,
            status="ready",
            observed_at_ms=None,
            next_refresh_at_ms=1_778_000_000_000,
            last_error=None,
            commit=False,
        )


def _insert_asset(conn) -> str:
    row = RegistryRepository(conn).upsert_chain_asset(
        chain_id="eip155:1",
        address="0x999b49c0d1612e619a4a4f6280733184da025108",
        observed_at_ms=1_778_000_000_000,
        commit=False,
    )
    return str(row["asset_id"])
