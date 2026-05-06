from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.retrieval.rolling_token_flow import RollingTokenFlow
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event

TOKEN_ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


def open_runtime(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    tokens = TokenRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
    )
    return conn, ingest, signals, tokens


def open_runtime_with_enrichment(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    return conn, ingest, signals, tokens, EnrichmentRepository(conn)


def open_runtime_with_harness(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    return conn, ingest, signals, tokens, HarnessRepository(conn)


def token_event(
    event_id: str,
    *,
    received_at_ms: int,
    author_handle: str = "traderpow",
    text: str = "$DOG",
):
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": TOKEN_ADDRESS,
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "p1": None,
                "s": "DOG",
                "liquidity": "250000",
                "holder_count": 10000,
                "pool": {"pool_address": "pool-dog"},
                "stat": {"volume_24h": "750000"},
            },
        }
    )
    return replace(
        make_event(event_id, author_handle=author_handle, text=text, received_at_ms=received_at_ms),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def test_token_flow_uses_trailing_window_not_epoch_bucket(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        current_event = token_event("event-dog-current", received_at_ms=now_ms - 10 * 60_000)
        previous_event = token_event("event-dog-previous", received_at_ms=now_ms - 70 * 60_000)

        ingest.ingest_event(previous_event, is_watched=True)
        ingest.ingest_event(current_event, is_watched=True)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["mentions"] == 1
    assert item["flow"]["previous_mentions"] == 1
    assert item["flow"]["window_start_ms"] == now_ms - 3_600_000
    assert item["flow"]["window_end_ms"] == now_ms


def test_token_flow_does_not_scan_unbounded_history_for_mention_bounds(tmp_path, monkeypatch):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    original = RollingTokenFlow._raw_token_mentions

    def guarded_raw_mentions(self, *, start_ms, end_ms, token_ids, watched_only):
        if start_ms is None and end_ms is None:
            raise AssertionError("unbounded raw mention scan")
        return original(
            self,
            start_ms=start_ms,
            end_ms=end_ms,
            token_ids=token_ids,
            watched_only=watched_only,
        )

    monkeypatch.setattr(RollingTokenFlow, "_raw_token_mentions", guarded_raw_mentions)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(token_event("event-dog-current", received_at_ms=now_ms - 10_000), is_watched=True)

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert items[0]["identity"]["symbol"] == "DOG"


def test_resolved_identity_bounds_use_token_ids_only(tmp_path, monkeypatch):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    captured_token_ids: set[str] = set()

    def guarded_bound_rows(self, *, token_ids, watched_only):
        captured_token_ids.update(token_ids)
        return []

    monkeypatch.setattr(RollingTokenFlow, "_indexed_mention_bound_rows", guarded_bound_rows)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(token_event("event-dog-current", received_at_ms=now_ms - 10_000), is_watched=True)

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert items[0]["identity"]["token_id"] is not None
    assert captured_token_ids == {items[0]["identity"]["token_id"]}


def test_baseline_zero_fills_silent_slots_and_scores_new_burst(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index in range(5):
            event = token_event(
                f"event-dog-burst-{index}",
                received_at_ms=now_ms - (index + 1) * 60_000,
                author_handle=f"voice{index}",
            )
            ingest.ingest_event(event, is_watched=False)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["mentions"] == 5
    assert item["flow"]["z_ewma"] is None
    assert item["flow"]["robust_z"] is None
    assert item["flow"]["baseline_version"] == "token_baseline_v2"
    assert item["social_heat"]["new_burst_score"] == item["flow"]["new_burst_score"]
    assert "insufficient_baseline_new_burst" in item["opportunity"]["reasons"]


def test_token_flow_omitted_now_ms_does_not_return_stale_fallback_rows(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        stale_event = token_event("event-dog-stale", received_at_ms=1_700_000_000_000)

        ingest.ingest_event(stale_event, is_watched=True)

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="1h", limit=10)
    finally:
        conn.close()

    assert items == []


def test_token_flow_diffusion_uses_full_author_counts_beyond_display_slice(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index in range(25):
            event = token_event(
                f"event-dog-author-{index}",
                received_at_ms=now_ms - (index + 1) * 1_000,
                author_handle=f"voice{index}",
            )
            ingest.ingest_event(event, is_watched=index < 3)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["propagation"]["independent_authors"] == 25
    assert sum(int(author["watched_count"]) for author in item["propagation"]["top_authors"]) == 3
    assert sum(int(author["followers"]) for author in item["propagation"]["top_authors"]) == 2000
    assert len(item["propagation"]["top_authors"]) == 20


def test_token_flow_response_includes_repeated_diffusion_block(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        repeated_texts = [
            "$DOG breakout now https://example.com/one",
            "$DOG breakout now 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            "$DOG breakout now",
        ]
        for index, text in enumerate(repeated_texts):
            event = token_event(
                f"event-dog-repeated-{index}",
                received_at_ms=now_ms - (index + 1) * 1_000,
                author_handle=f"voice{index}",
                text=text,
            )
            ingest.ingest_event(event, is_watched=index == 0)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["propagation"]["phase"] == "concentration"
    assert item["propagation"]["independent_authors"] == 3
    assert item["propagation"]["duplicate_text_share"] == 1.0
    assert "repeated_text_cluster" in item["propagation"]["risks"]
    assert "watched_author_present" in item["propagation"]["reasons"]


def test_token_flow_watch_block_marks_direct_watched_mentions(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index in range(25):
            event = token_event(
                f"event-dog-watch-{index}",
                received_at_ms=now_ms - (index + 1) * 1_000,
                author_handle=f"voice{index}",
            )
            ingest.ingest_event(event, is_watched=index < 3)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["watched_mentions"] == 3
    assert "watched_source_present" in item["social_heat"]["reasons"]
    assert "watched_author_present" in item["propagation"]["reasons"]


def test_token_flow_watch_block_marks_public_only_without_seed_links(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(token_event("event-dog-public", received_at_ms=now_ms - 10_000), is_watched=False)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["watched_mentions"] == 0
    assert "public_stream_coverage" in item["opportunity"]["risks"]


def test_token_flow_watch_block_does_not_link_unfrozen_unresolved_attention(tmp_path):
    conn, ingest, signals, tokens, harness = open_runtime_with_harness(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        seed_event = make_event(
            "seed-event",
            author_handle="toly",
            text="AI agent DOG thesis is accelerating",
            received_at_ms=now_ms - 4_000_000,
        )
        ingest.ingest_event(seed_event, is_watched=True)
        ingest.ingest_event(token_event("event-dog-public", received_at_ms=now_ms - 10_000), is_watched=False)
        HarnessSnapshotBuilder(harness, tokens=tokens).materialize(
            event=seed_event.to_dict(),
            extraction=SocialEventExtraction(
                is_signal_event=True,
                event_type="meme_phrase_seed",
                source_action="posted",
                subject="AI agent DOG thesis",
                direction_hint="attention_positive",
                attention_mechanism="meme_phrase",
                impact_hint=0.8,
                semantic_novelty_hint=0.8,
                confidence=0.9,
                anchor_terms=[AnchorTerm(term="AI agent", role="meme_phrase", evidence="AI agent")],
                token_candidates=[
                    SocialTokenCandidate(
                        symbol="DOG",
                        project_name=None,
                        chain="eth",
                        address=TOKEN_ADDRESS,
                        evidence="DOG",
                        confidence=0.9,
                    )
                ],
                semantic_risks=["public_stream_coverage"],
                summary_zh="Toly 提到 AI agent DOG，形成可回放的 harness seed。",
                raw_response={"ok": True},
            ),
            run_id="run-seed",
            model_version="fake-model",
        )

        item = TokenFlowService(signals=signals, tokens=tokens, harness=harness).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["watched_mentions"] == 0
    assert item["watch"]["status"] == "public_only"
    assert item["watch"]["top_seed"] is None
    assert item["propagation"]["score"] > 0
    assert item["opportunity"]["decision"] in {"watch", "driver"}
