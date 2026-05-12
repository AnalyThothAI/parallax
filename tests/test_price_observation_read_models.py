from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_insert_message_anchor_writes_baseline_without_current_market_facts(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_resolution(conn)
        observation = PriceObservationRepository(conn).insert_observation(
            provider="okx",
            pricefeed_id=None,
            observed_at_ms=1_700_000_001_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=0.42,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_anchor",
            event_received_at_ms=1_700_000_000_000,
        )
        baseline = conn.execute(
            """
            SELECT *
            FROM token_market_price_baselines
            WHERE resolution_id = 'resolution-1'
            """
        ).fetchone()
        current_market_table = conn.execute(
            "SELECT to_regclass('public.current_market_field_facts') AS value"
        ).fetchone()
    finally:
        conn.close()

    assert observation["observation_kind"] == "message_anchor"
    assert observation["observation_lag_ms"] == 1_000
    assert baseline["event_id"] == "event-1"
    assert baseline["target_type"] == "Asset"
    assert baseline["target_id"] == "asset:eip155:1:erc20:0xabc"
    assert baseline["event_price_usd"] == 0.42
    assert baseline["event_price_observation_kind"] == "message_anchor"
    assert baseline["first_price_usd"] == 0.42
    assert current_market_table["value"] is None


def test_insert_message_anchor_is_idempotent_by_resolution(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_resolution(conn)
        repo = PriceObservationRepository(conn)
        first = repo.insert_observation(
            provider="okx",
            pricefeed_id=None,
            observed_at_ms=1_700_000_001_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=0.42,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_anchor",
            event_received_at_ms=1_700_000_000_000,
        )
        second = repo.insert_observation(
            provider="okx",
            pricefeed_id=None,
            observed_at_ms=1_700_000_002_000,
            subject_type="Asset",
            subject_id="asset:eip155:1:erc20:0xabc",
            price_usd=0.43,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id="resolution-1",
            observation_kind="message_anchor",
            event_received_at_ms=1_700_000_000_000,
        )
        row = conn.execute(
            """
            SELECT count(*) AS count, max(price_usd) AS price_usd, max(observed_at_ms) AS observed_at_ms
            FROM price_observations
            WHERE source_resolution_id = 'resolution-1'
              AND observation_kind = 'message_anchor'
            """
        ).fetchone()
        baseline = conn.execute(
            """
            SELECT event_price_observation_id, event_price_usd, event_price_observed_at_ms
            FROM token_market_price_baselines
            WHERE resolution_id = 'resolution-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert second["observation_id"] == first["observation_id"]
    assert row["count"] == 1
    assert float(row["price_usd"]) == 0.43
    assert row["observed_at_ms"] == 1_700_000_002_000
    assert baseline["event_price_observation_id"] == first["observation_id"]
    assert baseline["event_price_usd"] == 0.43
    assert baseline["event_price_observed_at_ms"] == 1_700_000_002_000


def test_insert_observation_rejects_non_anchor_refresh_writes(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        with pytest.raises(ValueError, match="anchor-only"):
            PriceObservationRepository(conn).insert_observation(
                provider="okx_dex_price",
                pricefeed_id=None,
                observed_at_ms=1_700_000_000_000,
                subject_type="Asset",
                subject_id="asset:eip155:1:erc20:0xabc",
                price_usd=1.0,
                price_basis="usd",
                observation_kind="refresh",
            )
    finally:
        conn.close()


def _insert_event_intent_resolution(conn) -> None:
    EvidenceRepository(conn).insert_event(
        make_event("event-1", text="$ABC", received_at_ms=1_700_000_000_000),
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
          'ABC', NULL, NULL, NULL, 'pending', 1.0, 1_700_000_000_000, 1_700_000_000_000
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
          '["symbol:ABC"]'::jsonb, 'current', true, 1_700_000_000_000, 1_700_000_000_000
        )
        """,
        (TOKEN_RADAR_RESOLVER_POLICY_VERSION,),
    )
    conn.commit()
