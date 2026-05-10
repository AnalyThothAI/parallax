from __future__ import annotations

from decimal import Decimal

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    CONFIDENCE_MENTION_ONLY,
    CONFIDENCE_PROVIDER_CANDIDATE,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
    EVIDENCE_TWEET_CONTRACT_MENTION,
)
from gmgn_twitter_intel.domains.asset_market.repositories.identity_evidence_repository import IdentityEvidenceRepository
from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import (
    RegistryRepository,
)
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _evm_address(index: int) -> str:
    return f"0x{index:040x}"


def _insert_current_resolution(
    conn,
    *,
    event_id: str,
    intent_id: str,
    target_id: str | None,
    received_at_ms: int = 1_778_145_000_000,
    resolver_policy_version: str = "test",
    candidate_ids: list[str] | None = None,
    reason_codes: list[str] | None = None,
) -> None:
    EvidenceRepository(conn).insert_event(
        make_event(event_id, text="$HANTA", received_at_ms=received_at_ms, is_watched=True),
        is_watched=True,
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, display_symbol,
          intent_status, intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'deterministic', 'HANTA', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, f"symbol:HANTA:{intent_id}", received_at_ms, received_at_ms),
    )
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, identity_status, confidence,
          resolver_policy_version, reasons_json, risks_json, decision_time_ms, created_at_ms,
          target_type, target_id, reason_codes_json, candidate_ids_json, lookup_keys_json,
          registry_version, record_status, is_current
        )
        VALUES (
          %s, %s, %s, 'UNIQUE_BY_CONTEXT', 'resolved', 1.0, %s,
          %s, %s, %s, %s, 'Asset', %s, %s, %s, %s, 'test', 'current', true
        )
        """,
        (
            f"resolution:{intent_id}",
            intent_id,
            event_id,
            resolver_policy_version,
            Jsonb([]),
            Jsonb([]),
            received_at_ms,
            received_at_ms,
            target_id,
            Jsonb(reason_codes or ["TEST"]),
            Jsonb(candidate_ids or []),
            Jsonb(["symbol:HANTA"]),
        ),
    )


def _write_identity(
    identity: IdentityEvidenceRepository,
    asset: dict,
    *,
    symbol: str,
    name: str | None = None,
    evidence_kind: str = EVIDENCE_OKX_DEX_EXACT_ADDRESS,
    confidence: str = CONFIDENCE_PROVIDER_EXACT,
    observed_at_ms: int = 1_778_145_000_000,
) -> None:
    identity.upsert_identity_evidence(
        asset_id=str(asset["asset_id"]),
        evidence_kind=evidence_kind,
        provider="test",
        lookup_mode="test",
        chain_id=str(asset["chain_id"]),
        address=str(asset["address"]),
        symbol=symbol,
        name=name,
        decimals=18,
        confidence=confidence,
        observed_at_ms=observed_at_ms,
        commit=False,
    )
    identity.recompute_current_identity(str(asset["asset_id"]), now_ms=observed_at_ms, commit=False)


def test_registry_repository_writes_cex_token_asset_pricefeed_and_observation(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
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
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(identity, asset, symbol="PEPE", name="Pepe")
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


def test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
        observations = PriceObservationRepository(conn)
        asset = registry.upsert_chain_asset(
            chain_id="solana",
            address="5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            observed_at_ms=1_700_000_000_000,
        )
        _write_identity(identity, asset, symbol="TROLL", observed_at_ms=1_700_000_000_000)
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="Asset",
            subject_id=asset["asset_id"],
            price_usd=0.051,
            price_basis="usd",
            market_cap_usd=51_000_000,
            liquidity_usd=3_000_000,
            holders=52_000,
        )
        observations.insert_observation(
            provider="okx_dex_price",
            pricefeed_id=None,
            observed_at_ms=1_700_086_400_000,
            subject_type="Asset",
            subject_id=asset["asset_id"],
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=100_000_000,
            liquidity_usd=4_000_000,
            holders=55_000,
        )
        row = registry.find_assets_by_symbol_with_latest_observation("TROLL")[0]
    finally:
        conn.close()

    assert row["price_usd"] == Decimal("0.104")
    assert row["market_cap_usd"] == Decimal("51000000")
    assert row["market_cap_observed_at_ms"] == 1_700_000_000_000
    assert row["market_cap_provider"] == "okx_dex_search"


def test_okx_search_reactivates_demoted_search_asset(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        asset = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(1),
            observed_at_ms=1_778_145_000_000,
        )
        conn.execute("UPDATE registry_assets SET status = 'demoted_search' WHERE asset_id = %s", (asset["asset_id"],))

        reactivated = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(1),
            observed_at_ms=1_778_145_060_000,
        )
    finally:
        conn.close()

    assert reactivated["status"] == "candidate"


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
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            asset,
            symbol="SLOP",
            name="SLOP",
            evidence_kind=EVIDENCE_OKX_DEX_EXACT_ADDRESS,
            confidence=CONFIDENCE_PROVIDER_EXACT,
            observed_at_ms=1_778_145_060_000,
        )
        selected = identity.current_identity(str(asset["asset_id"]))
        rows = registry.find_assets_by_symbol_with_latest_observation("SLOP")
    finally:
        conn.close()

    assert selected["canonical_symbol"] == "SLOP"
    assert selected["identity_confidence"] == "provider_exact"
    assert rows[0]["asset_id"] == asset["asset_id"]
    assert rows[0]["symbol"] == "SLOP"


def test_symbol_lookup_and_price_refresh_ignore_demoted_search_assets(tmp_path):
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
        )
        conn.execute("UPDATE registry_assets SET status = 'demoted_search' WHERE asset_id = %s", (demoted["asset_id"],))

        symbol_assets = registry.find_assets_by_symbol_with_latest_observation("HANTA")
        refresh_assets = registry.chain_assets_needing_price_refresh(stale_before_ms=1_778_145_100_000, limit=10)
    finally:
        conn.close()

    assert [row["asset_id"] for row in symbol_assets] == [active["asset_id"]]
    refresh_ids = {row["asset_id"] for row in refresh_assets}
    assert active["asset_id"] in refresh_ids
    assert demoted["asset_id"] not in refresh_ids


def test_radar_price_refresh_selects_current_candidates_not_cold_registry_assets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        identity = IdentityEvidenceRepository(conn)
        hot_asset = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(7),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            hot_asset,
            symbol="HANTA",
            name="Hot",
            evidence_kind=EVIDENCE_TWEET_CONTRACT_MENTION,
            confidence=CONFIDENCE_MENTION_ONLY,
        )
        cold_asset = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(8),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            cold_asset,
            symbol="HANTA",
            name="Cold",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
        )
        demoted = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(9),
            observed_at_ms=1_778_145_000_000,
        )
        _write_identity(
            identity,
            demoted,
            symbol="HANTA",
            name="Demoted",
            evidence_kind=EVIDENCE_OKX_DEX_SYMBOL_CANDIDATE,
            confidence=CONFIDENCE_PROVIDER_CANDIDATE,
        )
        conn.execute("UPDATE registry_assets SET status = 'demoted_search' WHERE asset_id = %s", (demoted["asset_id"],))
        _insert_current_resolution(
            conn,
            event_id="evt-hot-radar-target",
            intent_id="intent-hot-radar-target",
            target_id=hot_asset["asset_id"],
            received_at_ms=1_778_145_200_000,
            resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
        )
        _insert_current_resolution(
            conn,
            event_id="evt-demoted-radar-target",
            intent_id="intent-demoted-radar-target",
            target_id=demoted["asset_id"],
            received_at_ms=1_778_145_210_000,
            resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
        )

        rows = registry.chain_assets_needing_radar_price_refresh(
            stale_before_ms=1_778_145_300_000,
            radar_since_ms=1_778_141_400_000,
            hot_since_ms=1_778_141_400_000,
            limit=10,
        )
    finally:
        conn.close()

    assert [row["asset_id"] for row in rows] == [hot_asset["asset_id"]]
