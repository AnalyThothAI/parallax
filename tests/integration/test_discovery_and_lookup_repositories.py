from __future__ import annotations

from typing import Any

from parallax.domains.asset_market.repositories.discovery_repository import DiscoveryRepository
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import (
    TokenIntentLookupRepository,
)
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_discovery_results_claim_only_explicitly_enqueued_unresolved_lookup_keys(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(conn)
        lookup = TokenIntentLookupRepository(conn)
        discovery = DiscoveryRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-1",
            event_id="event-1",
            keys=["symbol:UPEG", "cex_token:UPEG"],
            source_evidence_id="evidence-1",
            created_at_ms=1_000,
        )

        not_enqueued = _due_lookup_keys_for_test(conn, now_ms=2_000, limit=10, running_timeout_ms=60_000)
        enqueued = discovery.enqueue_lookup_keys(
            ["symbol:UPEG", "cex_token:UPEG"],
            reason="intent_unresolved",
            now_ms=2_000,
        )
        due = _due_lookup_keys_for_test(conn, now_ms=2_000, limit=10, running_timeout_ms=60_000)
        discovery.start_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:UPEG",
            lookup_type="dex_symbol_lookup",
            now_ms=2_000,
            running_timeout_ms=60_000,
        )
        discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:UPEG",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["asset:eip155:1:erc20:0xupeg"],
            result_hash="hash-1",
            next_refresh_at_ms=62_000,
            now_ms=2_100,
        )
        suppressed = _due_lookup_keys_for_test(conn, now_ms=61_000, limit=10, running_timeout_ms=60_000)
        stale = _due_lookup_keys_for_test(conn, now_ms=62_000, limit=10, running_timeout_ms=60_000)
        conn.execute(
            """
            UPDATE token_intent_resolutions
            SET resolution_status = 'AMBIGUOUS',
                candidate_ids_json = '["asset:eip155:1:erc20:0xupeg"]'::jsonb
            WHERE resolution_id = 'resolution-1'
            """
        )
        conn.commit()
        known_ambiguous = _due_lookup_keys_for_test(conn, now_ms=63_000, limit=10, running_timeout_ms=60_000)
        intents = lookup.intents_for_lookup_keys(["cex_token:UPEG"], limit=10)
    finally:
        conn.close()

    assert not_enqueued == []
    assert enqueued == 1
    assert [item["lookup_key"] for item in due] == ["symbol:UPEG"]
    assert suppressed == []
    assert [item["lookup_key"] for item in stale] == ["symbol:UPEG"]
    assert [item["lookup_key"] for item in known_ambiguous] == ["symbol:UPEG"]
    assert [item["intent_id"] for item in intents] == ["intent-1"]


def test_discovery_refreshes_ambiguous_lookup_after_nil_backlog(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-nil",
            intent_id="intent-nil",
            evidence_id="evidence-nil",
            resolution_id="resolution-nil",
            symbol="NILCOIN",
            received_at_ms=1_000,
        )
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-ambiguous",
            intent_id="intent-ambiguous",
            evidence_id="evidence-ambiguous",
            resolution_id="resolution-ambiguous",
            symbol="MAYBE",
            received_at_ms=100_000,
        )
        lookup = TokenIntentLookupRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-nil",
            event_id="event-nil",
            keys=["symbol:NILCOIN"],
            source_evidence_id="evidence-nil",
            created_at_ms=1_000,
        )
        lookup.replace_lookup_keys(
            intent_id="intent-ambiguous",
            event_id="event-ambiguous",
            keys=["symbol:MAYBE"],
            source_evidence_id="evidence-ambiguous",
            created_at_ms=100_000,
        )
        conn.execute(
            """
            UPDATE token_intent_resolutions
            SET resolution_status = 'AMBIGUOUS',
                reason_codes_json = '["NO_MARKET_DOMINANT_CHAIN_ASSET"]'::jsonb,
                candidate_ids_json = '["asset:solana:token:maybe","asset:eip155:1:erc20:maybe"]'::jsonb
            WHERE resolution_id = 'resolution-ambiguous'
            """
        )
        discovery = DiscoveryRepository(conn)
        discovery.enqueue_lookup_keys(
            ["symbol:NILCOIN"],
            reason="intent_resolution_unresolved",
            now_ms=1_000,
            latest_seen_ms=1_000,
        )
        discovery.enqueue_lookup_keys(
            ["symbol:MAYBE"],
            reason="intent_resolution_unresolved",
            now_ms=100_000,
            latest_seen_ms=100_000,
        )

        due = _due_lookup_keys_for_test(conn, now_ms=120_000, limit=2, running_timeout_ms=60_000)
    finally:
        conn.close()

    assert [item["lookup_key"] for item in due] == ["symbol:MAYBE", "symbol:NILCOIN"]


def test_discovery_prioritizes_recent_due_lookup_over_old_never_seen_backlog(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-old",
            intent_id="intent-old",
            evidence_id="evidence-old",
            resolution_id="resolution-old",
            symbol="OLD",
            received_at_ms=1_000,
        )
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-recent",
            intent_id="intent-recent",
            evidence_id="evidence-recent",
            resolution_id="resolution-recent",
            symbol="RECENT",
            received_at_ms=100_000,
        )
        lookup = TokenIntentLookupRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-old",
            event_id="event-old",
            keys=["symbol:OLD"],
            source_evidence_id="evidence-old",
            created_at_ms=1_000,
        )
        lookup.replace_lookup_keys(
            intent_id="intent-recent",
            event_id="event-recent",
            keys=["symbol:RECENT"],
            source_evidence_id="evidence-recent",
            created_at_ms=100_000,
        )
        discovery = DiscoveryRepository(conn)
        discovery.enqueue_lookup_keys(
            ["symbol:OLD"],
            reason="intent_resolution_unresolved",
            now_ms=1_000,
            latest_seen_ms=1_000,
        )
        discovery.enqueue_lookup_keys(
            ["symbol:RECENT"],
            reason="intent_resolution_unresolved",
            now_ms=100_000,
            latest_seen_ms=100_000,
        )
        discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:RECENT",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["asset:solana:token:recent"],
            result_hash="hash-recent",
            next_refresh_at_ms=90_000,
            now_ms=80_000,
        )

        due = _due_lookup_keys_for_test(conn, now_ms=120_000, limit=1, running_timeout_ms=60_000)
    finally:
        conn.close()

    assert [item["lookup_key"] for item in due] == ["symbol:RECENT"]


def test_discovery_retries_hot_not_found_before_old_backlog(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-old",
            intent_id="intent-old",
            evidence_id="evidence-old",
            resolution_id="resolution-old",
            symbol="OLD",
            received_at_ms=1_000,
        )
        _insert_event_intent_and_evidence(
            conn,
            event_id="event-hot",
            intent_id="intent-hot",
            evidence_id="evidence-hot",
            resolution_id="resolution-hot",
            symbol="HOT",
            received_at_ms=100_000,
        )
        lookup = TokenIntentLookupRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-old",
            event_id="event-old",
            keys=["symbol:OLD"],
            source_evidence_id="evidence-old",
            created_at_ms=1_000,
        )
        lookup.replace_lookup_keys(
            intent_id="intent-hot",
            event_id="event-hot",
            keys=["symbol:HOT"],
            source_evidence_id="evidence-hot",
            created_at_ms=100_000,
        )
        discovery = DiscoveryRepository(conn)
        discovery.enqueue_lookup_keys(
            ["symbol:OLD"],
            reason="intent_resolution_unresolved",
            now_ms=1_000,
            latest_seen_ms=1_000,
        )
        discovery.enqueue_lookup_keys(
            ["symbol:HOT"],
            reason="intent_resolution_unresolved",
            now_ms=100_000,
            latest_seen_ms=100_000,
        )
        discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:HOT",
            lookup_type="dex_symbol_lookup",
            status="not_found",
            candidate_ids=[],
            result_hash="empty",
            next_refresh_at_ms=380_000,
            now_ms=80_000,
        )

        due = _due_lookup_keys_for_test(
            conn,
            now_ms=120_000,
            limit=1,
            running_timeout_ms=60_000,
            hot_since_ms=90_000,
            hot_not_found_retry_ms=30_000,
        )
    finally:
        conn.close()

    assert [item["lookup_key"] for item in due] == ["symbol:HOT"]


def test_discovery_result_hash_reports_changed_only_when_lookup_result_changes(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        discovery = DiscoveryRepository(conn)

        first_changed = discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:SLOP",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["asset:solana:token:slop"],
            result_hash="hash-1",
            next_refresh_at_ms=10_000,
            now_ms=1_000,
        )
        unchanged = discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:SLOP",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["asset:solana:token:slop"],
            result_hash="hash-1",
            next_refresh_at_ms=20_000,
            now_ms=2_000,
        )
        changed_again = discovery.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:SLOP",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["asset:solana:token:slop", "asset:eip155:1:erc20:slop"],
            result_hash="hash-2",
            next_refresh_at_ms=30_000,
            now_ms=3_000,
        )
        counts = discovery.counts()
    finally:
        conn.close()

    assert first_changed is True
    assert unchanged is False
    assert changed_again is True
    assert counts == {"found": 1}


def test_discovery_due_order_includes_error_count_for_backoff(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(conn, symbol="RATE")
        lookup = TokenIntentLookupRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-1",
            event_id="event-1",
            keys=["symbol:RATE"],
            source_evidence_id="evidence-1",
            created_at_ms=1_000,
        )
        discovery = DiscoveryRepository(conn)
        discovery.enqueue_lookup_keys(
            ["symbol:RATE"],
            reason="intent_resolution_unresolved",
            now_ms=1_000,
            latest_seen_ms=1_000,
        )
        discovery.fail_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:RATE",
            lookup_type="dex_symbol_lookup",
            last_error="HTTP 429 Too Many Requests",
            next_refresh_at_ms=2_000,
            now_ms=1_000,
        )

        due = _due_lookup_keys_for_test(conn, now_ms=2_000, limit=10, running_timeout_ms=60_000)
    finally:
        conn.close()

    assert len(due) == 1
    assert due[0]["lookup_key"] == "symbol:RATE"
    assert due[0]["status"] == "error"
    assert due[0]["error_count"] == 1


def test_lookup_key_reprocess_can_revisit_already_resolved_intents(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_event_intent_and_evidence(conn)
        lookup = TokenIntentLookupRepository(conn)
        lookup.replace_lookup_keys(
            intent_id="intent-1",
            event_id="event-1",
            keys=["symbol:UPEG"],
            source_evidence_id="evidence-1",
            created_at_ms=1_000,
        )
        conn.execute(
            """
            UPDATE token_intent_resolutions
            SET resolution_status = 'UNIQUE_BY_CONTEXT',
                target_type = 'Asset',
                target_id = 'asset:eip155:1:erc20:0xold'
            WHERE resolution_id = 'resolution-1'
            """
        )
        conn.commit()

        intents = lookup.recent_intents_for_lookup_keys(["symbol:UPEG"], since_ms=0, limit=10)
    finally:
        conn.close()

    assert [item["intent_id"] for item in intents] == ["intent-1"]


def _due_lookup_keys_for_test(
    conn: Any,
    *,
    now_ms: int,
    limit: int,
    running_timeout_ms: int,
    hot_since_ms: int | None = None,
    hot_not_found_retry_ms: int | None = None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          queue.lookup_key,
          queue.lookup_type,
          queue.provider,
          queue.latest_seen_ms,
          queue.intent_count,
          queue.refresh_priority,
          CASE
            WHEN %(hot_since_ms)s::bigint IS NOT NULL AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint THEN 0
            ELSE 1
          END AS hot_priority,
          results.status,
          results.result_hash,
          results.next_refresh_at_ms,
          COALESCE(results.error_count, 0) AS error_count
        FROM token_discovery_dirty_lookup_keys queue
        LEFT JOIN token_discovery_results AS results
          ON results.provider = queue.provider
         AND results.lookup_key = queue.lookup_key
        WHERE queue.provider = 'okx_dex_search'
          AND queue.due_at_ms <= %(now_ms)s
          AND (queue.leased_until_ms IS NULL OR queue.leased_until_ms <= %(now_ms)s)
          AND (
            results.lookup_key IS NULL
            OR results.next_refresh_at_ms <= %(now_ms)s
            OR (
              results.status = 'running'
              AND results.updated_at_ms < %(running_expired_ms)s
            )
            OR (
              %(hot_since_ms)s::bigint IS NOT NULL
              AND %(hot_not_found_retry_ms)s::bigint IS NOT NULL
              AND queue.latest_seen_ms >= %(hot_since_ms)s::bigint
              AND results.status = 'not_found'
              AND results.last_lookup_at_ms <= %(now_ms)s::bigint - %(hot_not_found_retry_ms)s::bigint
            )
          )
        ORDER BY
          hot_priority ASC,
          queue.refresh_priority ASC,
          queue.latest_seen_ms DESC,
          CASE
            WHEN results.lookup_key IS NULL THEN 0
            WHEN results.status = 'error' THEN 1
            ELSE 2
          END,
          queue.intent_count DESC,
          queue.lookup_key ASC
        LIMIT %(limit)s
        """,
        {
            "now_ms": int(now_ms),
            "running_expired_ms": int(now_ms) - max(1, int(running_timeout_ms)),
            "hot_since_ms": int(hot_since_ms) if hot_since_ms is not None else None,
            "hot_not_found_retry_ms": int(hot_not_found_retry_ms) if hot_not_found_retry_ms is not None else None,
            "limit": max(0, int(limit)),
        },
    ).fetchall()
    return [dict(row) for row in rows]


def _insert_event_intent_and_evidence(
    conn,
    *,
    event_id: str = "event-1",
    intent_id: str = "intent-1",
    evidence_id: str = "evidence-1",
    resolution_id: str = "resolution-1",
    symbol: str = "UPEG",
    received_at_ms: int | None = None,
):
    from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository

    EvidenceRepository(conn).insert_event(
        make_event(event_id, text=f"${symbol}", received_at_ms=received_at_ms),
        is_watched=True,
    )
    conn.execute(
        """
        INSERT INTO token_evidence(
          evidence_id, event_id, source_kind, source_id, evidence_type, raw_value,
          normalized_symbol, chain_hint, address_hint, provider, provider_ref,
          text_surface, span_start, span_end, sentence_id, local_group_key,
          strength, confidence, created_at_ms
        )
        VALUES (
          %s, %s, 'entity', %s, 'cashtag', %s,
          %s, NULL, NULL, NULL, NULL, 'primary', 0, 5, 0, 'primary:0',
          'medium', 0.8, 1
        )
        """,
        (evidence_id, event_id, f"entity-{evidence_id}", f"${symbol}", symbol),
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
          display_symbol, display_name, chain_hint, address_hint, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, %s, 'test', %s,
          %s, NULL, NULL, NULL, 'pending', 1.0, 1, 1
        )
        """,
        (intent_id, event_id, f"symbol:{symbol}", evidence_id, symbol),
    )
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
          target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
          lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
        )
        VALUES (
          %s, %s, %s, 'NIL', %s,
          NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, %s::jsonb,
          'current', true, 1, 1
        )
        """,
        (resolution_id, intent_id, event_id, TOKEN_RADAR_RESOLVER_POLICY_VERSION, f'["symbol:{symbol}"]'),
    )
    conn.commit()
