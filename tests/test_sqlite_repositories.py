import asyncio
import time

import pytest

from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.entity_extractor import extract_entities
from gmgn_twitter_intel.pipeline.signal_builder import SignalBuilder
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


def make_event(
    event_id: str = "event-1",
    *,
    author_handle: str = "toly",
    text: str = "$PEPE mainnet 0x6982508145454ce325ddbe47a25d4ec3d2311933",
    received_at_ms: int | None = None,
    is_watched: bool = True,
) -> TwitterEvent:
    received_at_ms = received_at_ms if received_at_ms is not None else int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=author_handle, name=author_handle, avatar=None, followers=100, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[author_handle] if is_watched else [],
        raw={"id": event_id},
    )


def open_repositories(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    return conn, evidence, entities, signals


def test_evidence_repository_writes_event_and_fts_in_one_transaction(tmp_path):
    conn, evidence, _, _ = open_repositories(tmp_path)
    try:
        event = make_event()

        assert evidence.insert_event(event, is_watched=True) is True
        assert evidence.insert_event(event, is_watched=True) is False
        results = evidence.search_fts("mainnet", limit=10, watched_only=True)
    finally:
        conn.close()

    assert [item["event_id"] for item in results] == ["event-1"]
    assert results[0]["is_watched"] == 1


def test_search_fts_sanitizes_user_query_syntax(tmp_path):
    conn, evidence, _, _ = open_repositories(tmp_path)
    try:
        event = make_event(text="$PEPE mainnet stablecoin")
        evidence.insert_event(event, is_watched=True)
        results = evidence.search_fts('stablecoin?! -"unterminated', limit=10, watched_only=True)
        empty_results = evidence.search_fts('?! -" ', limit=10, watched_only=True)
    finally:
        conn.close()

    assert [item["event_id"] for item in results] == ["event-1"]
    assert empty_results == []


def test_raw_frame_insert_is_idempotent_by_payload_hash(tmp_path):
    conn, evidence, _, _ = open_repositories(tmp_path)
    try:
        assert evidence.insert_raw_frame(
            source="gmgn",
            channel="twitter_monitor_basic",
            received_at_ms=1_000,
            raw_payload_json='{"a":1}',
        )
        assert not evidence.insert_raw_frame(
            source="gmgn",
            channel="twitter_monitor_basic",
            received_at_ms=1_001,
            raw_payload_json='{"a":1}',
        )
        assert not conn.in_transaction
        counts = evidence.counts()
    finally:
        conn.close()

    assert counts["raw_frames"] == 1


def test_duplicate_raw_frame_does_not_poison_next_ingest_transaction(tmp_path):
    from gmgn_twitter_intel.pipeline.ingest_service import IngestService

    conn, evidence, entity_repo, signal_repo = open_repositories(tmp_path)
    try:
        ingest = IngestService(
            evidence=evidence,
            entities=entity_repo,
            signals=signal_repo,
            watch_keywords=("mainnet",),
        )
        assert ingest.insert_raw_frame(
            source="gmgn",
            channel="twitter_monitor_basic",
            received_at_ms=1_000,
            raw_payload_json='{"duplicate":true}',
        )
        assert not ingest.insert_raw_frame(
            source="gmgn",
            channel="twitter_monitor_basic",
            received_at_ms=1_001,
            raw_payload_json='{"duplicate":true}',
        )

        result = ingest.ingest_event(make_event("event-after-duplicate-raw"), is_watched=True)
        counts = evidence.counts()
    finally:
        conn.close()

    assert result.inserted is True
    assert counts["raw_frames"] == 1
    assert counts["events"] == 1


def test_entity_repository_persists_exact_token_and_keyword_entities(tmp_path):
    conn, evidence, entity_repo, _ = open_repositories(tmp_path)
    try:
        event = make_event()
        evidence.insert_event(event, is_watched=True)
        entities = extract_entities(event.content.text, watch_keywords=("mainnet",))
        inserted = entity_repo.insert_event_entities(event, entities, is_watched=True)

        assert inserted == len(entities)
        assert entity_repo.insert_event_entities(event, entities, is_watched=True) == 0
        ca_rows = entity_repo.find_by_ca("0x6982508145454ce325ddbe47a25d4ec3d2311933", limit=10)
        symbol_rows = entity_repo.find_by_symbol("PEPE", limit=10)
        keyword_rows = entity_repo.find_by_keyword("mainnet", limit=10)
    finally:
        conn.close()

    assert ca_rows[0]["event_id"] == "event-1"
    assert symbol_rows[0]["event_id"] == "event-1"
    assert keyword_rows[0]["event_id"] == "event-1"


def test_signal_builder_materializes_account_alerts_and_token_windows(tmp_path):
    conn, evidence, entity_repo, signal_repo = open_repositories(tmp_path)
    try:
        event = make_event()
        evidence.insert_event(event, is_watched=True)
        entities = extract_entities(event.content.text, watch_keywords=("mainnet",))
        entity_repo.insert_event_entities(event, entities, is_watched=True)

        result = SignalBuilder(signal_repo).build_for_event(event, entities, is_watched=True)
        alerts = signal_repo.account_alerts(window_ms=86_400_000, now_ms=event.received_at_ms + 1, limit=10)
        token_flow = signal_repo.token_flow(window="5m", limit=10)
    finally:
        conn.close()

    assert {alert["alert_type"] for alert in result.alerts} == {"account_token", "account_keyword"}
    assert {alert["alert_type"] for alert in alerts} == {"account_token", "account_keyword"}
    assert token_flow[0]["entity_key"].startswith("ca:eth:")
    assert token_flow[0]["mention_count"] == 1


def test_ingest_service_serializes_concurrent_sqlite_writes(tmp_path):
    from gmgn_twitter_intel.pipeline.ingest_service import IngestService

    conn, evidence, entity_repo, signal_repo = open_repositories(tmp_path)
    try:
        ingest = IngestService(
            evidence=evidence,
            entities=entity_repo,
            signals=signal_repo,
            watch_keywords=("mainnet",),
        )

        async def scenario():
            await asyncio.gather(
                *[
                    asyncio.to_thread(
                        ingest.ingest_event,
                        make_event(f"event-{index}", text=f"$PEPE mainnet {index}"),
                        is_watched=True,
                    )
                    for index in range(20)
                ]
            )

        asyncio.run(scenario())
        counts = evidence.counts()
    finally:
        conn.close()

    assert counts["events"] == 20


def test_ingest_service_rolls_back_event_when_signal_build_fails(tmp_path):
    from gmgn_twitter_intel.pipeline.ingest_service import IngestService

    class FailingSignalBuilder:
        def build_for_event(self, *args, **kwargs):
            raise RuntimeError("signal failed")

    conn, evidence, entity_repo, signal_repo = open_repositories(tmp_path)
    try:
        ingest = IngestService(
            evidence=evidence,
            entities=entity_repo,
            signals=signal_repo,
            watch_keywords=("mainnet",),
        )
        ingest.signal_builder = FailingSignalBuilder()

        with pytest.raises(RuntimeError, match="signal failed"):
            ingest.ingest_event(make_event("event-fails"), is_watched=True)

        counts = evidence.counts()
        entity_count = conn.execute("SELECT COUNT(*) FROM event_entities").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM event_fts").fetchone()[0]
    finally:
        conn.close()

    assert counts["events"] == 0
    assert entity_count == 0
    assert fts_count == 0
