from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.token_intel.repositories.intent_resolution_repository import (
    IntentResolutionRepository,
)
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.watchlist_intel.repositories.watchlist_intel_repository import (
    WatchlistIntelRepository,
)
from parallax.domains.watchlist_intel.types import encode_watchlist_timeline_cursor
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_watchlist_timeline_pages_raw_source_events(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="toly", text="$SOL launch", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="toly", text="gm", received_at_ms=2_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-3", author_handle="toly", text="$BONK meta", received_at_ms=3_000),
            is_watched=True,
        )
        _insert_token_resolution(conn, event_id="event-3", symbol="BONK")

        first_page = repo.timeline(handle="toly", scope="all", cursor=None, limit=2)
        signal_scope_page = repo.timeline(handle="toly", scope="signal", cursor=None, limit=10)
        cursor = encode_watchlist_timeline_cursor(received_at_ms=2_000, event_id="event-2")
        second_page = repo.timeline(handle="toly", scope="all", cursor=cursor, limit=10)
    finally:
        conn.close()

    assert [item["event_id"] for item in first_page["items"]] == ["event-3", "event-2"]
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert [item["event_id"] for item in signal_scope_page["items"]] == ["event-3", "event-2", "event-1"]
    assert signal_scope_page["items"][0]["social_event"] is None
    assert signal_scope_page["items"][0]["token_resolutions"][0]["target_id"] == "cex_token:BONK"
    assert second_page["items"][0]["event_id"] == "event-1"


def test_watchlist_handle_overview_uses_raw_events_for_clusters(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="marionawfal", text="$ALOY #macro", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="marionawfal", text="$BONK #solana", received_at_ms=2_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-3", author_handle="marionawfal", text="source stream #fed", received_at_ms=3_000),
            is_watched=True,
        )
        _insert_token_resolution(conn, event_id="event-2", symbol="BONK")

        overview = repo.handle_overview(handle="MarionAwfal", scope="signal", since_ms=0)
    finally:
        conn.close()

    assert overview["query"]["handle"] == "marionawfal"
    assert overview["query"]["scope"] == "signal"
    assert overview["metrics"]["source_event_count"] == 3
    assert overview["metrics"]["signal_event_count"] == 0
    assert overview["metrics"]["candidate_mention_count"] == 1
    assert overview["metrics"]["resolved_token_count"] == 1
    assert overview["candidate_mention_clusters"][0]["label"] == "$ALOY"
    assert overview["candidate_mention_clusters"][0]["source"] == "event_cashtags"
    assert overview["resolved_token_clusters"][0]["label"] == "$BONK"
    assert overview["resolved_token_clusters"][0]["kind"] == "resolved_token"
    assert overview["resolved_token_clusters"][0]["target_type"] == "CexToken"
    assert "candidate_mentions_unresolved" in overview["risk_notes"]
    assert any(cluster["label"] == "#fed" for cluster in overview["narrative_clusters"])


def test_watchlist_handle_overview_metrics_are_not_limited_by_cluster_sample(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        repo = WatchlistIntelRepository(conn)
        for index, symbol in enumerate(("ONE", "TWO", "THREE"), start=1):
            evidence.insert_event(
                make_event(
                    f"event-{index}",
                    author_handle="marionawfal",
                    text=f"${symbol} #macro",
                    received_at_ms=index * 1_000,
                ),
                is_watched=True,
            )

        overview = repo.handle_overview(handle="marionawfal", scope="signal", since_ms=0, limit=2)
    finally:
        conn.close()

    assert overview["metrics"]["source_event_count"] == 3
    assert overview["metrics"]["signal_event_count"] == 0
    assert overview["metrics"]["candidate_mention_count"] == 3
    assert len(overview["candidate_mention_clusters"]) == 2
    assert overview["clusters_truncated"] is True


def test_watchlist_handles_overview_returns_configured_handle_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="marionawfal", text="$ALOY", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="toly", text="$SOL", received_at_ms=2_000),
            is_watched=True,
        )

        rows = repo.handles_overview(handles=("marionawfal", "toly"), since_ms=0)
    finally:
        conn.close()

    by_handle = {row["handle"]: row for row in rows}
    assert set(by_handle) == {"marionawfal", "toly"}
    assert by_handle["marionawfal"]["last_source_event_at_ms"] == 1_000
    assert by_handle["marionawfal"]["recent_source_event_count"] == 1
    assert by_handle["marionawfal"]["recent_signal_event_count"] == 0
    assert by_handle["marionawfal"]["total_signal_event_count"] == 0
    assert by_handle["toly"]["last_source_event_at_ms"] == 2_000
    assert by_handle["toly"]["recent_signal_event_count"] == 0


def test_watchlist_timeline_uses_lower_author_cursor_index(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="Toly", text="$SOL launch", received_at_ms=1_000),
            is_watched=True,
        )
        conn.execute("SET enable_seqscan = off")
        plan_rows = conn.execute(
            """
            EXPLAIN (COSTS OFF)
            SELECT e.event_id
            FROM events e
            WHERE lower(e.author_handle) = %s
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            LIMIT 30
            """,
            ("toly",),
        ).fetchall()
    finally:
        conn.close()

    plan = "\n".join(_first_column(row) for row in plan_rows)
    assert "idx_events_author_received_event_lower_desc" in plan


def _insert_token_resolution(conn, *, event_id: str, symbol: str) -> None:
    TokenIntentRepository(conn).insert(
        {
            "intent_id": f"intent-{event_id}",
            "event_id": event_id,
            "intent_key": f"symbol:{symbol}",
            "construction_policy": "test",
            "primary_evidence_id": None,
            "display_symbol": symbol,
            "display_name": symbol,
            "chain_hint": None,
            "address_hint": None,
            "intent_status": "resolved",
            "intent_confidence": 0.9,
            "created_at_ms": 1_000,
            "updated_at_ms": 1_000,
        },
        commit=False,
    )
    IntentResolutionRepository(conn).insert_resolution(
        {
            "intent_id": f"intent-{event_id}",
            "event_id": event_id,
            "resolution_status": "RESOLVED",
            "resolver_policy_version": "test",
            "target_type": "CexToken",
            "target_id": f"cex_token:{symbol}",
            "pricefeed_id": f"pf:{symbol}",
            "reason_codes": ["test"],
            "candidate_ids": [symbol],
            "lookup_keys": [f"symbol:{symbol}"],
            "decision_time_ms": 1_100,
            "created_at_ms": 1_100,
        },
        commit=True,
    )


def _first_column(row) -> str:
    if isinstance(row, dict):
        return str(next(iter(row.values())))
    return str(row[0])
