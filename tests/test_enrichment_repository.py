import time
from threading import RLock

from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository


def make_event(
    event_id: str = "event-1",
    *,
    text: str | None = "Solana XDP throughput is nearly ready",
    is_watched: bool = True,
) -> TwitterEvent:
    received_at_ms = int(time.time() * 1000)
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
        author=Author(handle="toly", name="toly", avatar=None, followers=100, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"] if is_watched else [],
        raw={"id": event_id},
    )


def open_repositories(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
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
        write_lock=RLock(),
    )
    return conn, evidence, enrichment, ingest


def test_migration_creates_current_enrichment_tables(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "enrichment_jobs",
        "model_runs",
        "event_enrichments",
        "event_token_candidates",
        "event_narratives",
        "narrative_windows",
        "account_narrative_alerts",
        "narrative_seeds",
        "narrative_token_links",
    }.issubset(tables)


def test_narrative_seed_and_link_upserts_are_idempotent(tmp_path):
    conn, evidence, enrichment, ingest = open_repositories(tmp_path)
    try:
        event = make_event("seed-event")
        ingest.ingest_event(event, is_watched=True)
        seed = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="ai_agent_grok",
            seed_family="ai_agent",
            seed_terms=["grok", "ai agent"],
            market_interpretation="Market may look for Grok and AI-agent tokens.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.91,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=event.received_at_ms,
            author_handle="toly",
            evidence="Solana XDP",
            summary="seed summary",
        )
        duplicate = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="ai_agent_grok",
            seed_family="ai_agent",
            seed_terms=["grok"],
            market_interpretation="Updated interpretation.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.92,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=event.received_at_ms,
            author_handle="toly",
            evidence="Solana XDP",
            summary="updated summary",
        )
        link = enrichment.upsert_narrative_token_link(
            seed_id=seed["seed_id"],
            narrative_label="ai_agent_grok",
            token_identity_key="symbol:GROK",
            token_id=None,
            identity_status="unresolved_symbol",
            chain=None,
            address=None,
            symbol="GROK",
            first_linked_event_id="seed-event",
            best_evidence_event_id="seed-event",
            link_reason="seed_term_and_token_mention",
            matched_terms=["grok"],
            link_confidence=0.7,
            lag_ms=0,
            window="1h",
            mention_count_after_seed=1,
            watched_mention_count_after_seed=1,
            unique_author_count_after_seed=1,
            weighted_reach_after_seed=100.0,
            market_cap=None,
            market_status="missing",
            price_change_after_seed_pct=None,
            seed_score=70,
            diffusion_score=25,
            token_link_score=60,
            tradeability_score=10,
            decision="discard",
            reasons=["watched_handle_seed"],
            risks=["unresolved_symbol", "market_missing"],
        )
        duplicate_link = enrichment.upsert_narrative_token_link(**{
            **link,
            "link_confidence": 0.8,
            "matched_terms": ["grok", "ai agent"],
            "reasons": ["watched_handle_seed", "seed_term_and_token_mention"],
            "risks": ["unresolved_symbol", "market_missing"],
        })
        seeds = enrichment.narrative_seeds(window_ms=86_400_000, limit=10, now_ms=event.received_at_ms + 1)
        links = enrichment.narrative_token_links(seed_id=seed["seed_id"], window="1h", limit=10)
    finally:
        conn.close()

    assert seed["seed_id"] == duplicate["seed_id"]
    assert link["link_id"] == duplicate_link["link_id"]
    assert len(seeds) == 1
    assert seeds[0]["seed_terms"] == ["grok"]
    assert seeds[0]["summary"] == "updated summary"
    assert len(links) == 1
    assert links[0]["matched_terms"] == ["grok", "ai agent"]
    assert links[0]["link_confidence"] == 0.8


def test_seed_links_for_token_requires_chain_for_address_fallback(tmp_path):
    conn, _evidence, enrichment, ingest = open_repositories(tmp_path)
    try:
        seed_event = make_event("seed-event")
        linked_event = make_event("linked-event", is_watched=False)
        ingest.ingest_event(seed_event, is_watched=True)
        ingest.ingest_event(linked_event, is_watched=False)
        seed = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="same_address",
            seed_family="test",
            seed_terms=["same address"],
            market_interpretation="Address collision test.",
            stance="neutral",
            intent="test",
            confidence=0.9,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=seed_event.received_at_ms,
            author_handle="toly",
            evidence="same address",
            summary="seed summary",
        )
        address = "0x1111111111111111111111111111111111111111"
        enrichment.upsert_narrative_token_link(
            seed_id=seed["seed_id"],
            narrative_label="same_address",
            token_identity_key=f"token:bsc:{address}",
            token_id=f"token:bsc:{address}",
            identity_status="resolved_ca",
            chain="bsc",
            address=address,
            symbol="DOG",
            first_linked_event_id="linked-event",
            best_evidence_event_id="linked-event",
            link_reason="seed_term_and_token_mention",
            matched_terms=["same address"],
            link_confidence=0.7,
            lag_ms=1,
            window="1h",
            mention_count_after_seed=1,
            watched_mention_count_after_seed=0,
            unique_author_count_after_seed=1,
            weighted_reach_after_seed=100.0,
            market_cap=1000.0,
            market_status="fresh",
            price_change_after_seed_pct=None,
            seed_score=70,
            diffusion_score=25,
            token_link_score=60,
            tradeability_score=50,
            decision="watch",
            reasons=["watched_handle_seed"],
            risks=[],
        )

        eth_links = enrichment.seed_links_for_token(
            identity_key=f"token:eth:{address}",
            token_id=f"token:eth:{address}",
            chain="eth",
            address=address,
            symbol="DOG",
            since_ms=seed_event.received_at_ms - 1,
            limit=5,
        )
        bsc_links = enrichment.seed_links_for_token(
            identity_key=f"token:bsc:{address}",
            token_id=f"token:bsc:{address}",
            chain="bsc",
            address=address,
            symbol="DOG",
            since_ms=seed_event.received_at_ms - 1,
            limit=5,
        )
    finally:
        conn.close()

    assert eth_links == []
    assert len(bsc_links) == 1
    assert bsc_links[0]["link"]["chain"] == "bsc"


def test_watched_ingest_enqueues_one_durable_enrichment_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        result = ingest.ingest_event(make_event("watched-1"), is_watched=True)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.enrichment_job_id is not None
    assert len(jobs) == 1
    assert jobs[0]["event_id"] == "watched-1"
    assert jobs[0]["job_type"] == "watched_event_enrichment"
    assert jobs[0]["status"] == "pending"


def test_unwatched_or_textless_events_do_not_enqueue_enrichment_jobs(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("unwatched", is_watched=False), is_watched=False)
        ingest.ingest_event(make_event("textless", text=None), is_watched=True)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert jobs == []


def test_duplicate_watched_event_does_not_duplicate_enrichment_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        assert ingest.ingest_event(make_event("dup"), is_watched=True).inserted is True
        assert ingest.ingest_event(make_event("dup"), is_watched=True).inserted is False
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert [job["event_id"] for job in jobs] == ["dup"]


def test_claim_next_job_marks_running_and_respects_status(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("claim-me"), is_watched=True)
        claimed = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        second_claim = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        stored = enrichment.list_jobs(limit=10)[0]
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["event_id"] == "claim-me"
    assert second_claim is None
    assert stored["status"] == "running"
