from __future__ import annotations

from decimal import Decimal

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_RESOLVER_POLICY_VERSION
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


def test_okx_search_reactivates_demoted_search_asset(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        asset = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(1),
            symbol="HANTA",
            name="Hanta",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        conn.execute("UPDATE registry_assets SET status = 'demoted_search' WHERE asset_id = %s", (asset["asset_id"],))

        reactivated = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(1),
            symbol="HANTA",
            name="Hanta",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_060_000,
        )
    finally:
        conn.close()

    assert reactivated["status"] == "candidate"


def test_low_confidence_search_source_does_not_downgrade_explicit_source(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        explicit = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(2),
            symbol="HANTA",
            name="Hanta",
            decimals=18,
            source="tweet_ca",
            observed_at_ms=1_778_145_000_000,
        )
        searched = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(2),
            symbol="HANTA",
            name="Search Hanta",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_060_000,
        )
    finally:
        conn.close()

    assert explicit["primary_source"] == "tweet_ca"
    assert searched["primary_source"] == "tweet_ca"
    assert searched["name"] == "Search Hanta"


def test_demote_unretained_symbol_assets_keeps_current_targets_not_candidate_audit(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        retained = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(1),
            symbol="HANTA",
            name="Retained",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        protected_target = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(2),
            symbol="HANTA",
            name="Protected target",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        protected_candidate = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(3),
            symbol="HANTA",
            name="Protected candidate",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        unretained = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(4),
            symbol="HANTA",
            name="Unretained",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        _insert_current_resolution(
            conn,
            event_id="evt-protected-target",
            intent_id="intent-protected-target",
            target_id=protected_target["asset_id"],
            reason_codes=["CHAIN_ADDRESS_EXACT"],
        )
        _insert_current_resolution(
            conn,
            event_id="evt-protected-candidate",
            intent_id="intent-protected-candidate",
            target_id=None,
            candidate_ids=[protected_candidate["asset_id"]],
        )

        demoted = registry.demote_unretained_symbol_assets(
            symbol="HANTA",
            retained_asset_ids=[retained["asset_id"]],
            now_ms=1_778_145_100_000,
        )
        rows = conn.execute(
            """
            SELECT asset_id, status
            FROM registry_assets
            WHERE upper(symbol) = 'HANTA'
            ORDER BY asset_id
            """
        ).fetchall()
    finally:
        conn.close()

    statuses = {row["asset_id"]: row["status"] for row in rows}
    assert demoted == 2
    assert statuses[retained["asset_id"]] == "candidate"
    assert statuses[protected_target["asset_id"]] == "candidate"
    assert statuses[protected_candidate["asset_id"]] == "demoted_search"
    assert statuses[unretained["asset_id"]] == "demoted_search"


def test_demote_symbol_search_tail_assets_preserves_address_exact_targets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        assets = [
            registry.upsert_chain_asset(
                chain_id="eip155:56",
                address=_evm_address(index),
                symbol="HANTA",
                name=f"Hanta {index}",
                decimals=18,
                source="okx_dex_search",
                observed_at_ms=1_778_145_000_000 + index,
            )
            for index in range(1, 6)
        ]
        _insert_current_resolution(
            conn,
            event_id="evt-protected-address",
            intent_id="intent-protected-address",
            target_id=assets[4]["asset_id"],
            reason_codes=["CHAIN_ADDRESS_EXACT"],
        )

        demoted = registry.demote_symbol_search_tail_assets(
            now_ms=1_778_145_100_000,
        )
        rows = conn.execute(
            """
            SELECT asset_id, status
            FROM registry_assets
            WHERE upper(symbol) = 'HANTA'
            ORDER BY updated_at_ms DESC, asset_id
            """
        ).fetchall()
    finally:
        conn.close()

    statuses = {row["asset_id"]: row["status"] for row in rows}
    assert demoted == 1
    assert statuses[assets[4]["asset_id"]] == "candidate"
    assert statuses[assets[3]["asset_id"]] == "candidate"
    assert statuses[assets[2]["asset_id"]] == "candidate"
    assert statuses[assets[1]["asset_id"]] == "candidate"
    assert statuses[assets[0]["asset_id"]] == "demoted_search"


def test_symbol_lookup_and_price_refresh_ignore_demoted_search_assets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        registry = RegistryRepository(conn)
        active = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(5),
            symbol="HANTA",
            name="Active",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        demoted = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(6),
            symbol="HANTA",
            name="Demoted",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
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
        hot_asset = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(7),
            symbol="HANTA",
            name="Hot",
            decimals=18,
            source="tweet_ca",
            observed_at_ms=1_778_145_000_000,
        )
        registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(8),
            symbol="HANTA",
            name="Cold",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
        )
        demoted = registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(9),
            symbol="HANTA",
            name="Demoted",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=1_778_145_000_000,
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
