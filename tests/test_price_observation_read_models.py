from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_insert_observation_writes_current_market_field_facts(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observation = PriceObservationRepository(conn).insert_observation(
            provider="okx_dex_search",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="Asset",
            subject_id="asset:solana:token:TROLL",
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=100_000_000,
            liquidity_usd=4_100_000,
            holders=55_000,
        )
        rows = conn.execute(
            """
            SELECT field_key, value_json, observed_at_ms, provider, source_observation_id
            FROM current_market_field_facts
            WHERE subject_type = 'Asset'
              AND subject_id = 'asset:solana:token:TROLL'
            ORDER BY field_key
            """
        ).fetchall()
    finally:
        conn.close()

    by_key = {row["field_key"]: row for row in rows}
    assert by_key["price_usd"]["value_json"] == 0.104
    assert by_key["market_cap_usd"]["value_json"] == 100_000_000
    assert by_key["liquidity_usd"]["value_json"] == 4_100_000
    assert by_key["holders"]["value_json"] == 55_000
    assert by_key["price_usd"]["source_observation_id"] == observation["observation_id"]
    assert by_key["price_usd"]["provider"] == "okx_dex_search"


def test_backfill_current_market_field_facts_restores_existing_observations(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PriceObservationRepository(conn)
        repo.insert_observation(
            provider="okx_dex_search",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="Asset",
            subject_id="asset:solana:token:TROLL",
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=100_000_000,
            liquidity_usd=4_100_000,
            holders=55_000,
        )
        conn.execute("DELETE FROM current_market_field_facts")
        conn.commit()

        result = repo.backfill_current_market_field_facts(limit=10)
        rows = conn.execute(
            """
            SELECT field_key, value_json
            FROM current_market_field_facts
            WHERE subject_type = 'Asset'
              AND subject_id = 'asset:solana:token:TROLL'
            ORDER BY field_key
            """
        ).fetchall()
    finally:
        conn.close()

    by_key = {row["field_key"]: row["value_json"] for row in rows}
    assert result == {"observations_scanned": 1, "facts_written": 5}
    assert by_key["price_usd"] == 0.104
    assert by_key["market_cap_usd"] == 100_000_000
    assert by_key["liquidity_usd"] == 4_100_000
    assert by_key["holders"] == 55_000


def test_insert_message_observation_writes_token_price_baseline(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_resolution(conn)
        repo = PriceObservationRepository(conn)
        repo.insert_observation(
            provider="gmgn_payload",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=1.0,
            price_basis="usd",
        )
        repo.insert_observation(
            provider="gmgn_payload",
            pricefeed_id=None,
            observed_at_ms=1_700_000_060_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=1.2,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_payload",
            event_received_at_ms=1_700_000_060_000,
        )
        baseline = conn.execute(
            """
            SELECT *
            FROM token_market_price_baselines
            WHERE resolution_id = 'resolution-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert baseline["event_id"] == "event-1"
    assert baseline["target_type"] == "Asset"
    assert baseline["target_id"] == "asset:eip155:1:erc20:0xabc"
    assert baseline["event_price_usd"] == 1.2
    assert baseline["event_price_observation_kind"] == "message_payload"
    assert baseline["before_event_price_usd"] == 1.0
    assert baseline["first_price_usd"] == 1.0


def _insert_event_intent_resolution(conn) -> None:
    EvidenceRepository(conn).insert_event(
        make_event("event-1", text="$ABC", received_at_ms=1_700_000_060_000),
        is_watched=True,
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          'intent-1', 'event-1', 'symbol:ABC', 'test', NULL,
          'ABC', NULL, NULL, NULL, 'pending', 1.0, 1_700_000_060_000, 1_700_000_060_000
        )
        """
    )
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
          target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
          lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          'resolution-1', 'intent-1', 'event-1', 'EXACT', %s,
          'Asset', 'asset:eip155:1:erc20:0xabc', NULL, '[]'::jsonb, '[]'::jsonb,
          '["symbol:ABC"]'::jsonb, 'current', true, 1_700_000_060_000, 1_700_000_060_000
        )
        """,
        (TOKEN_RADAR_RESOLVER_POLICY_VERSION,),
    )
    conn.commit()
