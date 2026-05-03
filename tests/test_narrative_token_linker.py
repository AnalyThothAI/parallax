from dataclasses import replace
from threading import RLock

from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.narrative_token_linker import NarrativeTokenLinker
from gmgn_twitter_intel.retrieval.narrative_link_service import NarrativeLinkService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_enrichment_repository import make_event


def open_runtime(tmp_path):
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
    return conn, evidence, signals, enrichment, tokens, ingest


def test_linker_uses_public_stream_mentions_after_watched_seed(tmp_path):
    conn, evidence, signals, enrichment, tokens, ingest = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        seed_event = make_event("seed-event", text="Grok is getting scary good")
        seed_event = replace(seed_event, received_at_ms=base_ms, timestamp=base_ms // 1000)
        public_event = make_event("public-grok", text="$GROK Grok is running", is_watched=False)
        public_event = replace(public_event, received_at_ms=base_ms + 60_000, timestamp=(base_ms + 60_000) // 1000)
        ingest.ingest_event(seed_event, is_watched=True)
        ingest.ingest_event(public_event, is_watched=False)
        seed = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="ai_agent_grok",
            seed_family="ai_agent",
            seed_terms=["grok"],
            market_interpretation="Market may look for Grok tokens.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.9,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=base_ms,
            author_handle="toly",
            evidence="Grok is getting scary good",
            summary="seed summary",
        )

        links = NarrativeTokenLinker(
            evidence=evidence,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
        ).link_seed(seed=seed, window="1h")
        view = NarrativeLinkService(enrichment=enrichment).narrative_token_flow(
            seed_id=seed["seed_id"],
            window="1h",
            limit=10,
        )
    finally:
        conn.close()

    assert len(links) == 1
    assert links[0]["symbol"] == "GROK"
    assert links[0]["link_reason"] == "seed_term_and_token_mention"
    assert links[0]["lag_ms"] == 60_000
    assert links[0]["decision"] == "discard"
    assert view["seed"]["seed_id"] == seed["seed_id"]
    assert view["links"][0]["identity"]["symbol"] == "GROK"


def test_linker_does_not_link_without_seed_term_evidence(tmp_path):
    conn, evidence, signals, enrichment, tokens, ingest = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        seed_event = make_event("seed-event", text="Grok is getting scary good")
        seed_event = replace(seed_event, received_at_ms=base_ms, timestamp=base_ms // 1000)
        public_event = make_event("public-dog", text="$DOG unrelated launch", is_watched=False)
        public_event = replace(public_event, received_at_ms=base_ms + 60_000, timestamp=(base_ms + 60_000) // 1000)
        ingest.ingest_event(seed_event, is_watched=True)
        ingest.ingest_event(public_event, is_watched=False)
        seed = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="ai_agent_grok",
            seed_family="ai_agent",
            seed_terms=["grok"],
            market_interpretation="Market may look for Grok tokens.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.9,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=base_ms,
            author_handle="toly",
            evidence="Grok is getting scary good",
            summary="seed summary",
        )

        links = NarrativeTokenLinker(
            evidence=evidence,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
        ).link_seed(seed=seed, window="1h")
    finally:
        conn.close()

    assert links == []


def test_linker_confirms_seed_llm_token_candidate_with_later_public_symbol(tmp_path):
    conn, evidence, signals, enrichment, tokens, ingest = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        seed_event = make_event("seed-event", text="xAI is shipping Grok fast")
        seed_event = replace(seed_event, received_at_ms=base_ms, timestamp=base_ms // 1000)
        public_event = make_event("public-grok", text="$GROK running now", is_watched=False)
        public_event = replace(public_event, received_at_ms=base_ms + 60_000, timestamp=(base_ms + 60_000) // 1000)
        ingest.ingest_event(seed_event, is_watched=True)
        ingest.ingest_event(public_event, is_watched=False)
        enrichment.conn.execute(
            """
            INSERT INTO event_token_candidates(
              candidate_id, event_id, symbol, project_name, chain, address, evidence,
              confidence, resolution_status, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "candidate-seed-grok",
                "seed-event",
                "GROK",
                "Grok",
                None,
                None,
                "Grok",
                0.9,
                "unresolved_llm_candidate",
                base_ms,
            ),
        )
        seed = enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="xai_product_velocity",
            seed_family="ai_agent",
            seed_terms=["xai"],
            market_interpretation="Market may look for xAI-related tokens.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.9,
            source_weight=1.0,
            novelty_status="new_global",
            received_at_ms=base_ms,
            author_handle="toly",
            evidence="xAI is shipping Grok fast",
            summary="seed summary",
        )

        links = NarrativeTokenLinker(
            evidence=evidence,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
        ).link_seed(seed=seed, window="1h")
    finally:
        conn.close()

    assert len(links) == 1
    assert links[0]["symbol"] == "GROK"
    assert links[0]["link_reason"] == "seed_symbol_candidate_confirmed"
