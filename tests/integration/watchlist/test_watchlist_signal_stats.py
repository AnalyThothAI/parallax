from __future__ import annotations

from gmgn_twitter_intel.domains.social_enrichment.repositories.social_event_extraction_repository import (
    SocialEventExtractionRepository,
)
from gmgn_twitter_intel.domains.watchlist_intel.repositories.watchlist_intel_repository import (
    WatchlistIntelRepository,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_social_event_extraction_persists_normalized_handle(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = SocialEventExtractionRepository(conn)

        row = _extract_signal(repo, event_id="event-1", author_handle="@Toly", received_at_ms=1_000)
        recent = repo.recent(window="24h", limit=10, handles={"TOLY"}, now_ms=2_000)
    finally:
        conn.close()

    assert row["normalized_handle"] == "toly"
    assert [item["event_id"] for item in recent["items"]] == ["event-1"]
    assert recent["items"][0]["normalized_handle"] == "toly"


def test_watchlist_signal_stats_tracks_event_idempotency_moves_and_removals(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = WatchlistIntelRepository(conn)

        assert repo.record_signal_event_state(
            handle="@Toly",
            event_id="event-1",
            received_at_ms=1_000,
            is_signal_event=True,
        )
        assert repo.record_signal_event_state(
            handle="TOLY",
            event_id="event-1",
            received_at_ms=1_500,
            is_signal_event=True,
        )
        assert repo.record_signal_event_state(
            handle="toly",
            event_id="event-2",
            received_at_ms=2_000,
            is_signal_event=True,
        )

        toly_before_move = repo.signal_stats_for_handle("toly")
        assert toly_before_move is not None
        assert toly_before_move["total_signal_count"] == 2
        assert toly_before_move["latest_signal_event_id"] == "event-2"
        assert toly_before_move["latest_signal_at_ms"] == 2_000
        assert repo.count_signal_events_total("TOLY") == 2

        assert repo.record_signal_event_state(
            handle="TraderPow",
            event_id="event-1",
            received_at_ms=3_000,
            is_signal_event=True,
        )
        assert repo.count_signal_events_total("toly") == 1
        assert repo.count_signal_events_total("traderpow") == 1
        traderpow = repo.signal_stats_for_handle("@traderpow")
        assert traderpow is not None
        assert traderpow["latest_signal_event_id"] == "event-1"

        assert repo.record_signal_event_state(
            handle="toly",
            event_id="event-2",
            received_at_ms=2_500,
            is_signal_event=False,
        )
        assert repo.count_signal_events_total("toly") == 0
        assert repo.signal_stats_for_handle("toly") is None
    finally:
        conn.close()


def test_backfill_signal_stats_dry_run_does_not_write_read_models(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        _extract_signal(social_events, event_id="event-1", author_handle="@Toly", received_at_ms=1_000)
        conn.execute(
            "UPDATE social_event_extractions SET normalized_handle = NULL WHERE event_id = %s",
            ("event-1",),
        )
        conn.commit()

        dry_run = repo.backfill_signal_stats_batch(
            after_received_at_ms=None,
            after_event_id=None,
            batch_size=10,
            dry_run=True,
        )
        dry_run_extraction = conn.execute(
            "SELECT normalized_handle FROM social_event_extractions WHERE event_id = %s",
            ("event-1",),
        ).fetchone()
        dry_run_signal_event = conn.execute(
            "SELECT * FROM watchlist_handle_signal_events WHERE event_id = %s",
            ("event-1",),
        ).fetchone()

        applied = repo.backfill_signal_stats_batch(
            after_received_at_ms=None,
            after_event_id=None,
            batch_size=10,
        )
        applied_extraction = conn.execute(
            "SELECT normalized_handle FROM social_event_extractions WHERE event_id = %s",
            ("event-1",),
        ).fetchone()
        applied_stats = repo.signal_stats_for_handle("toly")
    finally:
        conn.close()

    assert dry_run["processed"] == 1
    assert dry_run["signal_events"] == 1
    assert dry_run["normalized_handles"] == 1
    assert dry_run_extraction["normalized_handle"] is None
    assert dry_run_signal_event is None
    assert applied["processed"] == 1
    assert applied_extraction["normalized_handle"] == "toly"
    assert applied_stats is not None
    assert applied_stats["total_signal_count"] == 1


def _extract_signal(
    repo: SocialEventExtractionRepository,
    *,
    event_id: str,
    author_handle: str,
    received_at_ms: int,
    is_signal_event: bool = True,
) -> dict:
    return repo.upsert_extraction(
        extraction_id=f"extract-{event_id}",
        event_id=event_id,
        run_id=None,
        author_handle=author_handle,
        received_at_ms=received_at_ms,
        schema_version="social-event-v2",
        model_version="test-model",
        event_type="meme_phrase_seed",
        source_action="posted",
        subject="topic",
        direction_hint="attention_positive",
        attention_mechanism="meme_phrase",
        impact_hint=0.7,
        semantic_novelty_hint=0.6,
        confidence=0.85,
        is_signal_event=is_signal_event,
        anchor_terms=[{"term": "topic", "role": "topic", "evidence": "topic"}],
        token_candidates=[{"symbol": "SOL", "evidence": "$SOL", "confidence": 0.8}],
        semantic_risks=["public_stream_coverage"],
        summary_zh="SOL 讨论升温。",
        raw_response={"ok": True},
    )
