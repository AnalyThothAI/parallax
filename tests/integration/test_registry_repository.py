from __future__ import annotations

from parallax.domains.asset_market.identity_evidence_policy import (
    CONFIDENCE_MENTION_ONLY,
    CONFIDENCE_PROVIDER_CANDIDATE,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
    EVIDENCE_TWEET_CONTRACT_MENTION,
)
from parallax.domains.asset_market.repositories.identity_evidence_repository import IdentityEvidenceRepository
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _evm_address(index: int) -> str:
    return f"0x{index:040x}"


def _write_identity(
    identity: IdentityEvidenceRepository,
    asset: dict,
    *,
    symbol: str,
    name: str | None = None,
    evidence_kind: str = EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    confidence: str = CONFIDENCE_PROVIDER_EXACT,
    provider: str = "okx",
    lookup_mode: str = "exact_address",
    raw_payload: dict | None = None,
    observed_at_ms: int = 1_778_145_000_000,
) -> None:
    identity.upsert_identity_evidence(
        asset_id=str(asset["asset_id"]),
        evidence_kind=evidence_kind,
        provider=provider,
        lookup_mode=lookup_mode,
        chain_id=str(asset["chain_id"]),
        address=str(asset["address"]),
        symbol=symbol,
        name=name,
        decimals=18,
        confidence=confidence,
        raw_payload=raw_payload or {},
        observed_at_ms=observed_at_ms,
    )
    identity.recompute_current_identity(str(asset["asset_id"]), now_ms=observed_at_ms)


def test_registry_repository_writes_cex_token_asset_and_pricefeed_routes(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)

        cex_token = registry.upsert_cex_token(
            base_symbol="PEPE",
            source="binance",
            observed_at_ms=1_778_145_000_000,
        )
        asset = registry.upsert_chain_asset(
            chain_id="eip155:1",
            address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(identity, asset, symbol="PEPE", name="Pepe")
        pricefeed = registry.upsert_pricefeed(
            feed_type="cex_swap",
            provider="binance",
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            native_market_id="PEPEUSDT",
            base_cex_token_id=cex_token["cex_token_id"],
            base_symbol="PEPE",
            quote_symbol="USDT",
            observed_at_ms=1_778_145_000_000,
        )
        usdc_pricefeed = registry.upsert_pricefeed(
            feed_type="cex_swap",
            provider="binance",
            subject_type="CexToken",
            subject_id=cex_token["cex_token_id"],
            native_market_id="PEPEUSDC",
            base_cex_token_id=cex_token["cex_token_id"],
            base_symbol="PEPE",
            quote_symbol="USDC",
            observed_at_ms=1_778_145_000_000,
        )

        found_cex = registry.find_cex_token("pepe")
        preferred_feed = registry.find_preferred_cex_pricefeed("pepe")
        found_asset = registry.find_assets_by_symbol_with_identity_metadata("PEPE")[0]
    finally:
        conn.close()

    assert cex_token["cex_token_id"] == "cex_token:PEPE"
    assert found_cex["cex_token_id"] == "cex_token:PEPE"
    assert asset["asset_id"] == "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert found_asset["market_cap_usd"] is None
    assert pricefeed["pricefeed_id"] == "pricefeed:cex:binance:swap:PEPEUSDT"
    assert usdc_pricefeed["pricefeed_id"] == "pricefeed:cex:binance:swap:PEPEUSDC"
    assert preferred_feed["pricefeed_id"] == "pricefeed:cex:binance:swap:PEPEUSDT"


def test_chain_asset_upserts_by_identity_index_when_address_case_differs(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        first = registry.upsert_chain_asset(
            chain_id="solana",
            address="DbSkJeuJwZTEzhpbwMbeNlfefwqzx87FvNuQRterpump",
            observed_at_ms=1_778_145_000_000,
        )
        second = registry.upsert_chain_asset(
            chain_id="solana",
            address="dbskjeujwztezhpbwmbenlfefwqzx87fvnuqrterpump",
            observed_at_ms=1_778_145_001_000,
        )
        third = registry.upsert_chain_asset(
            chain_id="solana",
            address="DBSKJEUJWZTEZHPBWMBENLFEFWQZX87FVNUQRTERPUMP",
            observed_at_ms=1_778_145_002_000,
        )
        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM registry_assets
            WHERE chain_id = 'solana'
              AND lower(address) = 'dbskjeujwztezhpbwmbenlfefwqzx87fvnuqrterpump'
            """
        ).fetchone()["count"]
    finally:
        conn.close()

    assert second["asset_id"] == first["asset_id"]
    assert third["asset_id"] == first["asset_id"]
    assert count == 1


def test_chain_asset_upsert_repairs_existing_asset_id_when_identity_index_misses(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        address = "DQ1WbZKFH6esW7pd4Yrf3SPLf4vTrQnBKbzrmfTQpump"
        asset_id = f"asset:solana:token:{address}"
        conn.execute(
            """
            INSERT INTO registry_assets(
              asset_id, chain_id, token_standard, address, status, first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, 'solana', 'token', %s, 'candidate', %s, %s)
            """,
            (asset_id, f"{address} ", 1_778_145_000_000, 1_778_145_000_000),
        )

        asset = registry.upsert_chain_asset(
            chain_id="solana",
            address=address,
            observed_at_ms=1_778_145_001_000,
        )
        stored = conn.execute(
            "SELECT address, updated_at_ms FROM registry_assets WHERE asset_id = %s",
            (asset_id,),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM registry_assets WHERE asset_id = %s",
            (asset_id,),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert asset["asset_id"] == asset_id
    assert stored["address"] == address
    assert stored["updated_at_ms"] == 1_778_145_001_000
    assert count == 1


def test_registry_repository_writes_and_deactivates_us_equity_symbols(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)

        row = registry.upsert_us_equity_symbol(
            symbol="aaoi",
            exchange="NASDAQ",
            security_name="Applied Optoelectronics, Inc. Common Stock",
            instrument_type="equity",
            source="nasdaq_trader",
            source_updated_at_ms=1_778_000_000_000,
            raw_payload={"Symbol": "AAOI"},
            observed_at_ms=1_778_000_000_000,
        )
        found = registry.find_us_equity_symbol("AAOI")
        deactivated = registry.deactivate_missing_us_equity_symbols(
            source="nasdaq_trader",
            active_symbols=set(),
            observed_at_ms=1_778_000_060_000,
        )
        missing_after_deactivate = registry.find_us_equity_symbol("AAOI")
    finally:
        conn.close()

    assert row["symbol"] == "AAOI"
    assert row["market_instrument_id"] == "market_instrument:us_equity:AAOI"
    assert found["security_name"] == "Applied Optoelectronics, Inc. Common Stock"
    assert found["status"] == "active"
    assert deactivated == 1
    assert missing_after_deactivate is None


def test_symbol_lookup_reads_market_metadata_from_binance_identity_evidence(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
        small = registry.upsert_chain_asset(
            chain_id="solana",
            address="SoSmall1111111111111111111111111111111111",
            observed_at_ms=1_700_000_000_000,
        )
        _write_identity(
            identity,
            small,
            symbol="HANTA",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
            lookup_mode="symbol_search",
            raw_payload={
                "marketCap": "1000000",
                "liquidity": "100000",
                "holders": "1000",
                "price": "0.01",
                "provider_rank": 1,
            },
            observed_at_ms=1_700_000_000_000,
        )
        large = registry.upsert_chain_asset(
            chain_id="solana",
            address="SoLarge1111111111111111111111111111111111",
            observed_at_ms=1_700_000_000_000,
        )
        _write_identity(
            identity,
            large,
            symbol="HANTA",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
            lookup_mode="symbol_search",
            raw_payload={
                "marketCapUsd": "51000000",
                "liquidityUsd": "3000000",
                "holderCount": "52000",
                "priceUsd": "0.051",
                "provider_rank": 0,
            },
            observed_at_ms=1_700_000_100_000,
        )

        rows = registry.find_assets_by_symbol_with_identity_metadata("HANTA")
    finally:
        conn.close()

    assert [row["asset_id"] for row in rows] == [large["asset_id"], small["asset_id"]]
    assert rows[0]["price_usd"] == 0.051
    assert rows[0]["market_cap_usd"] == 51_000_000.0
    assert rows[0]["liquidity_usd"] == 3_000_000.0
    assert rows[0]["holders"] == 52_000
    assert rows[0]["market_cap_provider"] == "okx"
    assert rows[0]["market_cap_observed_at_ms"] == 1_700_000_100_000
    assert rows[0]["provider_rank"] == 0
    assert rows[0]["provider_rank_observed_at_ms"] == 1_700_000_100_000


def test_identity_current_selects_exact_provider_over_tweet_alias_without_registry_identity_columns(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
        asset = registry.upsert_chain_asset(
            chain_id="eip155:1",
            address=_evm_address(43),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            asset,
            symbol="SATO",
            evidence_kind=EVIDENCE_TWEET_CONTRACT_MENTION,
            confidence=CONFIDENCE_MENTION_ONLY,
            provider="gmgn",
            lookup_mode="message_payload",
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            asset,
            symbol="SLOP",
            name="SLOP",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            confidence=CONFIDENCE_PROVIDER_EXACT,
            provider="binance",
            lookup_mode="exact_address",
            observed_at_ms=1_778_145_060_000,
        )
        selected = identity.current_identity(str(asset["asset_id"]))
        rows = registry.find_assets_by_symbol_with_identity_metadata("SLOP")
    finally:
        conn.close()

    assert selected["canonical_symbol"] == "SLOP"
    assert selected["identity_confidence"] == "provider_exact"
    assert rows[0]["asset_id"] == asset["asset_id"]
    assert rows[0]["symbol"] == "SLOP"


def test_symbol_lookup_ignores_demoted_search_assets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
        active = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(5),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            active,
            symbol="HANTA",
            name="Active",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
            lookup_mode="symbol_search",
        )
        demoted = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(6),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            demoted,
            symbol="HANTA",
            name="Demoted",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
            lookup_mode="symbol_search",
        )
        conn.execute("UPDATE registry_assets SET status = 'demoted_search' WHERE asset_id = %s", (demoted["asset_id"],))

        symbol_assets = registry.find_assets_by_symbol_with_identity_metadata("HANTA")
    finally:
        conn.close()

    assert [row["asset_id"] for row in symbol_assets] == [active["asset_id"]]
