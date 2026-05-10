from __future__ import annotations

import hashlib

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_price_observation_repository_records_message_attribution(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_resolution(conn)
        repo = PriceObservationRepository(conn)

        observation = repo.insert_observation(
            provider="gmgn_payload",
            pricefeed_id=None,
            observed_at_ms=1_700_000_001_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=1.25,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_payload",
            event_received_at_ms=1_700_000_000_000,
        )
    finally:
        conn.close()

    assert observation["observation_kind"] == "message_payload"
    assert observation["source_event_id"] == "event-1"
    assert observation["source_intent_id"] == "intent-1"
    assert observation["source_resolution_id"] == "resolution-1"
    assert observation["event_received_at_ms"] == 1_700_000_000_000
    assert observation["observation_lag_ms"] == 1_000


def test_price_observation_message_id_does_not_collide_with_refresh(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_resolution(conn)
        repo = PriceObservationRepository(conn)

        refresh = repo.insert_observation(
            provider="okx_cex",
            pricefeed_id="pricefeed:okx:BTC-USDT",
            observed_at_ms=1_700_000_001_000,
            subject_type="CexToken",
            subject_id="cex-token:BTC",
            price_usd=70_000,
            price_basis="usd",
            observation_kind="refresh",
        )
        message = repo.insert_observation(
            provider="okx_cex",
            pricefeed_id="pricefeed:okx:BTC-USDT",
            observed_at_ms=1_700_000_001_000,
            subject_type="CexToken",
            subject_id="cex-token:BTC",
            price_usd=70_100,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_quote",
            event_received_at_ms=1_700_000_000_000,
        )
    finally:
        conn.close()

    assert refresh["observation_id"] != message["observation_id"]
    assert refresh["observation_kind"] == "refresh"
    assert message["observation_kind"] == "message_quote"


def test_refresh_observation_keeps_provider_subject_time_identity(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PriceObservationRepository(conn)
        observation_id = hashlib.sha256(
            b"price-observation|okx_cex|pricefeed:okx:BTC-USDT|CexToken|cex-token:BTC|1700000001000"
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO price_observations(
              observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
              price_usd, price_basis, raw_payload_json, created_at_ms
            )
            VALUES (
              %s, 'pricefeed:okx:BTC-USDT', 'okx_cex', 1700000001000, 'CexToken', 'cex-token:BTC',
              70000, 'usd', '{}'::jsonb, 1700000001000
            )
            """,
            (observation_id,),
        )
        conn.commit()

        observation = repo.insert_observation(
            provider="okx_cex",
            pricefeed_id="pricefeed:okx:BTC-USDT",
            observed_at_ms=1_700_000_001_000,
            subject_type="CexToken",
            subject_id="cex-token:BTC",
            price_usd=71_000,
            price_basis="usd",
            observation_kind="refresh",
        )
        rows = conn.execute(
            """
            SELECT observation_id, price_usd, observation_kind
            FROM price_observations
            WHERE provider = 'okx_cex'
              AND pricefeed_id = 'pricefeed:okx:BTC-USDT'
              AND subject_type = 'CexToken'
              AND subject_id = 'cex-token:BTC'
              AND observed_at_ms = 1700000001000
            """
        ).fetchall()
    finally:
        conn.close()

    assert observation["observation_id"] == observation_id
    assert len(rows) == 1
    assert rows[0]["price_usd"] == 71_000
    assert rows[0]["observation_kind"] == "refresh"


def test_price_observation_repository_reads_baselines_and_message_price(tmp_path):
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

        first = repo.first_for_subject(subject_type="Asset", subject_id="asset:eip155:1:erc20:0xabc")
        before = repo.latest_for_subject_at_or_before(
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            at_or_before_ms=1_700_000_030_000,
        )
        message = repo.latest_message_for_event(
            event_id="event-1",
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
        )
    finally:
        conn.close()

    assert first and first["price_usd"] == 1.0
    assert before and before["price_usd"] == 1.0
    assert message and message["price_usd"] == 1.2
    assert message["observation_kind"] == "message_payload"


def _insert_event_intent_resolution(conn) -> None:
    conn.execute(
        """
        INSERT INTO events(event_id, source, payload_hash, author_handle, text, received_at_ms, inserted_at_ms)
        VALUES ('event-1', 'gmgn', 'hash-1', 'alice', '$BTC', 1700000000000, 1700000000000)
        """
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, display_symbol, display_name, address_hint, chain_hint, source_json,
          confidence, evidence_count, resolver_status, created_at_ms
        )
        VALUES ('intent-1', 'event-1', 'BTC', NULL, NULL, NULL, '{}'::jsonb, 1, 1, 'pending', 1700000000000)
        """
    )
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, asset_id, primary_venue_id, identity_status, confidence,
          resolver_policy_version, resolved_at_ms, resolution_status, target_type, target_id,
          decision_time_ms, record_status, is_current
        )
        VALUES (
          'resolution-1', 'intent-1', 'event-1', NULL, NULL, 'EXACT', 1,
          %s, 1700000000000, 'EXACT', 'Asset',
          'asset:eip155:1:erc20:0xabc', 1700000000000, 'current', true
        )
        """,
        (TOKEN_RADAR_RESOLVER_POLICY_VERSION,),
    )
    conn.commit()
