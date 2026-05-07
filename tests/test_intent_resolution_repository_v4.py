from __future__ import annotations

from gmgn_twitter_intel.pipeline.deterministic_token_resolver import DeterministicResolution
from gmgn_twitter_intel.storage.intent_resolution_repository import IntentResolutionRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_v4_resolution_supersedes_by_lifecycle_not_resolution_status(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_and_intent(conn)
        repo = IntentResolutionRepository(conn)

        first = repo.insert_resolution(
            DeterministicResolution(
                intent_id="intent-1",
                event_id="event-1",
                resolution_status="NIL",
                target_type=None,
                target_id=None,
                pricefeed_id=None,
                resolver_policy_version="token_radar_v4_deterministic_resolver",
                reason_codes=["SYMBOL_NOT_IN_REGISTRY"],
                candidate_ids=[],
                lookup_keys=["symbol:UPEG"],
                decision_time_ms=1_000,
                created_at_ms=1_000,
            )
        )
        second = repo.insert_resolution(
            DeterministicResolution(
                intent_id="intent-1",
                event_id="event-1",
                resolution_status="UNIQUE_BY_CONTEXT",
                target_type="Asset",
                target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
                pricefeed_id=None,
                resolver_policy_version="token_radar_v4_deterministic_resolver",
                reason_codes=["MARKET_DOMINANT_CHAIN_ASSET"],
                candidate_ids=["asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"],
                lookup_keys=["symbol:UPEG"],
                decision_time_ms=2_000,
                created_at_ms=2_000,
            )
        )
        active = repo.active_resolution_for_intent("intent-1")
        rows = conn.execute(
            """
            SELECT resolution_id, resolution_status, record_status, is_current
            FROM token_intent_resolutions
            ORDER BY decision_time_ms
            """
        ).fetchall()
    finally:
        conn.close()

    assert first["resolution_status"] == "NIL"
    assert second["resolution_status"] == "UNIQUE_BY_CONTEXT"
    assert active["resolution_id"] == second["resolution_id"]
    assert [row["resolution_status"] for row in rows] == ["NIL", "UNIQUE_BY_CONTEXT"]
    assert [row["record_status"] for row in rows] == ["superseded", "current"]
    assert [row["is_current"] for row in rows] == [False, True]


def _insert_event_and_intent(conn):
    from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository

    EvidenceRepository(conn).insert_event(make_event(), is_watched=True)
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          'intent-1', 'event-1', 'symbol:UPEG', 'test', NULL,
          'UPEG', NULL, NULL, NULL, 'pending', 1.0, 1, 1
        )
        """
    )
    conn.commit()
