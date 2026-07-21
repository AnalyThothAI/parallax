from __future__ import annotations

from parallax.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.services.deterministic_token_resolver import DeterministicResolution
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_resolution_supersedes_by_lifecycle_not_resolution_status(tmp_path):
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
                resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
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
                resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
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


def test_resolution_late_replay_does_not_rollback_current_pointer(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_and_intent(conn)
        repo = IntentResolutionRepository(conn)
        current_decision = _resolution(
            status="UNIQUE_BY_CONTEXT",
            target_type="Asset",
            target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
            decision_time_ms=2_000,
        )
        late_old_decision = _resolution(
            status="NIL",
            target_type=None,
            target_id=None,
            decision_time_ms=1_000,
        )

        current = repo.insert_resolution(current_decision)
        replay = repo.insert_resolution(late_old_decision)
        active = repo.active_resolution_for_intent("intent-1")
        rows = conn.execute(
            """
            SELECT resolution_id, resolution_status, record_status, is_current, superseded_at_ms
            FROM token_intent_resolutions
            ORDER BY decision_time_ms
            """
        ).fetchall()
    finally:
        conn.close()

    assert replay["resolution_id"] == current["resolution_id"]
    assert active["resolution_id"] == current["resolution_id"]
    assert [row["resolution_status"] for row in rows] == ["UNIQUE_BY_CONTEXT"]
    assert rows[0]["record_status"] == "current"
    assert rows[0]["is_current"] is True
    assert rows[0]["superseded_at_ms"] is None


def test_resolution_current_replay_keeps_superseded_timestamp_null(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_and_intent(conn)
        repo = IntentResolutionRepository(conn)
        decision = _resolution(
            status="UNIQUE_BY_CONTEXT",
            target_type="Asset",
            target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
            decision_time_ms=2_000,
        )

        first = repo.insert_resolution(decision)
        replay = repo.insert_resolution(decision)
        stored = repo.get(first["resolution_id"])
        rows = conn.execute(
            """
            SELECT resolution_id, record_status, is_current, superseded_at_ms
            FROM token_intent_resolutions
            """
        ).fetchall()
    finally:
        conn.close()

    assert replay["resolution_id"] == first["resolution_id"]
    assert stored is not None
    assert stored["record_status"] == "current"
    assert stored["is_current"] is True
    assert stored["superseded_at_ms"] is None
    assert len(rows) == 1
    assert rows[0]["superseded_at_ms"] is None


def _resolution(
    *,
    status: str,
    target_type: str | None,
    target_id: str | None,
    decision_time_ms: int,
) -> DeterministicResolution:
    return DeterministicResolution(
        intent_id="intent-1",
        event_id="event-1",
        resolution_status=status,
        target_type=target_type,
        target_id=target_id,
        pricefeed_id=None,
        resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
        reason_codes=["MARKET_DOMINANT_CHAIN_ASSET"] if target_id else ["SYMBOL_NOT_IN_REGISTRY"],
        candidate_ids=[target_id] if target_id else [],
        lookup_keys=["symbol:UPEG"],
        decision_time_ms=decision_time_ms,
        created_at_ms=decision_time_ms,
    )


def _insert_event_and_intent(conn):
    from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository

    with conn.transaction():
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
