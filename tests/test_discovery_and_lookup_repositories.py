from __future__ import annotations

from gmgn_twitter_intel.storage.discovery_repository import DiscoveryRepository
from gmgn_twitter_intel.storage.token_intent_lookup_repository import TokenIntentLookupRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_discovery_enqueue_is_idempotent_and_lookup_keys_round_trip(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(conn)
        discovery = DiscoveryRepository(conn)
        lookup = TokenIntentLookupRepository(conn)

        first = discovery.enqueue(
            task_type="dex_symbol_lookup",
            query_key="symbol:UPEG",
            payload={"symbol": "UPEG"},
            next_run_at_ms=1_000,
            created_at_ms=1_000,
        )
        second = discovery.enqueue(
            task_type="dex_symbol_lookup",
            query_key="symbol:UPEG",
            payload={"symbol": "UPEG"},
            next_run_at_ms=2_000,
            created_at_ms=2_000,
        )
        lookup.replace_lookup_keys(
            intent_id="intent-1",
            event_id="event-1",
            keys=["symbol:UPEG", "cex_token:UPEG"],
            source_evidence_id="evidence-1",
            created_at_ms=1_000,
        )
        intents = lookup.intents_for_lookup_keys(["cex_token:UPEG"], limit=10)
    finally:
        conn.close()

    assert first["task_id"] == second["task_id"]
    assert second["next_run_at_ms"] == 1_000
    assert [item["intent_id"] for item in intents] == ["intent-1"]


def test_discovery_repository_claims_completes_and_retries_due_tasks(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        discovery = DiscoveryRepository(conn)
        discovery.enqueue(
            task_type="dex_symbol_lookup",
            query_key="symbol:UPEG",
            payload={"symbol": "UPEG"},
            next_run_at_ms=1_000,
            created_at_ms=1_000,
        )

        claimed = discovery.claim_due(now_ms=2_000, limit=1)
        discovery.complete(task_id=claimed[0]["task_id"], updated_at_ms=2_100)
        done = discovery.task(claimed[0]["task_id"])
        discovery.enqueue(
            task_type="dex_symbol_lookup",
            query_key="symbol:LFI",
            payload={"symbol": "LFI"},
            next_run_at_ms=2_000,
            created_at_ms=2_000,
        )
        failed = discovery.claim_due(now_ms=2_000, limit=1)
        discovery.fail(
            task_id=failed[0]["task_id"],
            last_error="rate limited",
            next_run_at_ms=8_000,
            updated_at_ms=2_200,
        )
        retry = discovery.claim_due(now_ms=8_000, limit=5)
    finally:
        conn.close()

    assert claimed[0]["status"] == "running"
    assert claimed[0]["attempt_count"] == 1
    assert done["status"] == "done"
    assert retry[0]["query_key"] == "symbol:LFI"
    assert retry[0]["attempt_count"] == 2


def _insert_event_intent_and_evidence(conn):
    from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository

    EvidenceRepository(conn).insert_event(make_event(), is_watched=True)
    conn.execute(
        """
        INSERT INTO token_evidence(
          evidence_id, event_id, source_kind, source_id, evidence_type, raw_value,
          normalized_symbol, chain_hint, address_hint, provider, provider_ref,
          text_surface, span_start, span_end, sentence_id, local_group_key,
          strength, confidence, created_at_ms
        )
        VALUES (
          'evidence-1', 'event-1', 'entity', 'entity-1', 'cashtag', '$UPEG',
          'UPEG', NULL, NULL, NULL, NULL, 'primary', 0, 5, 0, 'primary:0',
          'medium', 0.8, 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          'intent-1', 'event-1', 'symbol:UPEG', 'test', 'evidence-1',
          'UPEG', NULL, NULL, NULL, 'pending', 1.0, 1, 1
        )
        """
    )
    conn.commit()
