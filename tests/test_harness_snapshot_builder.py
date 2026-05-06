from gmgn_twitter_intel.pipeline.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_snapshot_builder_materializes_seed_cluster_snapshot_and_shadow_decision(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        extraction = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="BNB attention seed",
            direction_hint="attention_positive",
            attention_mechanism="meme_phrase",
            impact_hint=0.72,
            semantic_novelty_hint=0.68,
            confidence=0.86,
            anchor_terms=[AnchorTerm(term="build on BNB", role="meme_phrase", evidence="build on BNB")],
            token_candidates=[
                SocialTokenCandidate(
                    symbol="BNB",
                    project_name=None,
                    chain=None,
                    address=None,
                    evidence="BNB",
                    confidence=0.8,
                )
            ],
            semantic_risks=["public_stream_coverage"],
            summary_zh="CZ 提到 build on BNB。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness).materialize(
            event={
                "event_id": "event-1",
                "author_handle": "cz_binance",
                "received_at_ms": 1_000,
                "search_text": "CZ says build on BNB",
            },
            extraction=extraction,
            run_id="run-1",
            model_version="gpt-test",
        )
        duplicate = HarnessSnapshotBuilder(harness).materialize(
            event={
                "event_id": "event-1",
                "author_handle": "cz_binance",
                "received_at_ms": 1_000,
                "search_text": "CZ says build on BNB",
            },
            extraction=extraction,
            run_id="run-1",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["social_event"]["event_type"] == "meme_phrase_seed"
    assert materialized["seed"]["seed_status"] == "snapshot_ready"
    assert [snapshot["horizon"] for snapshot in materialized["snapshots"]] == ["6h", "24h"]
    assert materialized["snapshots"][0]["asset"] == "BNB"
    assert materialized["clusters"][0]["pricedness"] != 0.35
    assert materialized["decisions"][0]["execution_mode"] == "shadow"
    assert materialized["decisions"][0]["signal"] == "LONG_SMALL"
    assert duplicate["snapshots"][0]["snapshot_id"] == materialized["snapshots"][0]["snapshot_id"]
    read_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=True)
    try:
        snapshots = HarnessRepository(read_conn).list_snapshots(
            window_ms=10_000,
            now_ms=2_000,
            horizon=None,
            limit=10,
        )
    finally:
        read_conn.close()
    assert len(snapshots) == 2


def test_snapshot_builder_stores_non_signal_without_snapshot(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        extraction = SocialEventExtraction(
            is_signal_event=False,
            event_type="founder_reply",
            source_action="replied",
            subject="casual reply",
            direction_hint="neutral",
            attention_mechanism="reply_target",
            impact_hint=0.2,
            semantic_novelty_hint=0.1,
            confidence=0.8,
            anchor_terms=[AnchorTerm(term="gm", role="meme_phrase", evidence="gm")],
            token_candidates=[],
            semantic_risks=["low_information"],
            summary_zh="普通回复。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness).materialize(
            event={"event_id": "event-2", "author_handle": "heyi", "received_at_ms": 2_000, "search_text": "gm"},
            extraction=extraction,
            run_id="run-2",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["social_event"]["is_signal_event"] is False
    assert materialized["seed"] is None
    assert materialized["snapshots"] == []
    assert materialized["decisions"] == []


def test_snapshot_builder_uses_anchor_terms_for_seed_only_signal_snapshots(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        extraction = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="Grok meme attention",
            direction_hint="attention_positive",
            attention_mechanism="meme_phrase",
            impact_hint=0.7,
            semantic_novelty_hint=0.8,
            confidence=0.9,
            anchor_terms=[AnchorTerm(term="Grok", role="meme_phrase", evidence="Grok")],
            token_candidates=[],
            semantic_risks=["unresolved_symbol"],
            summary_zh="Musk 提到 Grok，形成 seed-only 信号。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness).materialize(
            event={
                "event_id": "event-grok",
                "author_handle": "elonmusk",
                "received_at_ms": 3_000,
                "search_text": "Grok",
            },
            extraction=extraction,
            run_id="run-grok",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["seed"]["seed_status"] == "seed_only"
    assert materialized["seed"]["top_linked_symbols"] == ["GROK"]
    assert materialized["snapshots"][0]["asset"] == "GROK"
    assert "unresolved_symbol" in materialized["snapshots"][0]["risks"]
