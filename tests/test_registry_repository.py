from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.storage.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.storage.registry_repository import RegistryRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_registry_repository_writes_cex_token_asset_pricefeed_and_observation(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        observations = PriceObservationRepository(conn)

        cex_token = registry.upsert_cex_token(
            base_symbol="PEPE",
            project_id=None,
            source="okx",
            observed_at_ms=1_778_145_000_000,
        )
        asset = registry.upsert_chain_asset(
            chain_id="eip155:1",
            address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
            symbol="PEPE",
            name="Pepe",
            decimals=18,
            source="okx_dex",
            observed_at_ms=1_778_145_000_000,
        )
        pricefeed = registry.upsert_pricefeed(
            feed_type="cex_spot",
            provider="okx",
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            native_market_id="PEPE-USDT",
            base_cex_token_id=cex_token["cex_token_id"],
            base_symbol="PEPE",
            quote_symbol="USDT",
            observed_at_ms=1_778_145_000_000,
        )
        usdc_pricefeed = registry.upsert_pricefeed(
            feed_type="cex_spot",
            provider="okx",
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            native_market_id="PEPE-USDC",
            base_cex_token_id=cex_token["cex_token_id"],
            base_symbol="PEPE",
            quote_symbol="USDC",
            observed_at_ms=1_778_145_000_000,
        )
        observations.insert_observation(
            provider="okx_cex",
            pricefeed_id=pricefeed["pricefeed_id"],
            observed_at_ms=1_778_145_000_000,
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            price_usd=Decimal("0.0000208"),
            price_quote=Decimal("0.0000208"),
            quote_symbol="USDT",
            price_basis="usd_like",
            market_cap_usd=None,
            liquidity_usd=None,
            volume_24h_usd=Decimal("52345.00709138"),
            open_interest_usd=None,
            holders=None,
            raw_payload={"instId": "PEPE-USDT"},
        )

        found_cex = registry.find_cex_token("pepe")
        preferred_feed = registry.find_preferred_cex_pricefeed("pepe")
        found_asset = registry.find_assets_by_symbol_with_latest_observation("PEPE")[0]
        latest_price = observations.latest_for_subject(
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            at_or_before_ms=1_778_145_100_000,
        )
    finally:
        conn.close()

    assert cex_token["cex_token_id"] == "cex_token:PEPE"
    assert found_cex["cex_token_id"] == "cex_token:PEPE"
    assert asset["asset_id"] == "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert found_asset["market_cap_usd"] is None
    assert pricefeed["pricefeed_id"] == "pricefeed:cex:okx:spot:PEPE-USDT"
    assert usdc_pricefeed["pricefeed_id"] == "pricefeed:cex:okx:spot:PEPE-USDC"
    assert preferred_feed["pricefeed_id"] == "pricefeed:cex:okx:spot:PEPE-USDT"
    assert latest_price["price_usd"] == Decimal("0.0000208")
    assert latest_price["price_basis"] == "usd_like"
