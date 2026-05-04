from gmgn_twitter_intel.pipeline.llm_enrichment import EnrichmentResult, NarrativeItem
from gmgn_twitter_intel.pipeline.narrative_seed_builder import NarrativeSeedBuilder
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_enrichment_repository import make_event


def test_seed_builder_only_materializes_watched_event_narratives(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        enrichment = EnrichmentRepository(conn)
        EntityRepository(conn)
        SignalRepository(conn)
        TokenRepository(conn)
        watched = make_event("watched-seed", text="Grok is getting scary good")
        public = make_event("public-seed", text="Grok is getting scary good", is_watched=False)
        evidence.insert_event(watched, is_watched=True)
        evidence.insert_event(public, is_watched=False)
        result = EnrichmentResult(
            summary="Musk-like account talked about Grok.",
            summary_zh="关注账号讨论 Grok，引发 AI Agent 主题注意力。",
            narratives=[
                NarrativeItem(
                    label="ai_agent_grok",
                    display_name_zh="Grok AI Agent",
                    headline_zh="Grok 相关发言带动 AI Agent 注意力",
                    description_zh="Grok as an AI-agent attention seed",
                    seed_family="ai_agent",
                    trigger_terms=["Grok", "AI agent"],
                    market_interpretation_zh="交易员可能关注 Grok 或 AI Agent 相关 token。",
                    evidence="Grok is getting scary good",
                    confidence=0.9,
                )
            ],
            stance="bullish",
            intent="technical_commentary",
            confidence=0.9,
            raw_response={"ok": True},
        )
        watched_seed_rows = NarrativeSeedBuilder(enrichment).build_for_event(
            event=evidence.events_by_ids(["watched-seed"])["watched-seed"],
            result=result,
        )
        public_seed_rows = NarrativeSeedBuilder(enrichment).build_for_event(
            event=evidence.events_by_ids(["public-seed"])["public-seed"],
            result=result,
        )
    finally:
        conn.close()

    assert len(watched_seed_rows) == 1
    assert watched_seed_rows[0]["narrative_label"] == "ai_agent_grok"
    assert watched_seed_rows[0]["seed_terms"] == ["grok", "ai agent"]
    assert watched_seed_rows[0]["display"]["headline_zh"] == "Grok 相关发言带动 AI Agent 注意力"
    assert watched_seed_rows[0]["display"]["summary_zh"] == "关注账号讨论 Grok，引发 AI Agent 主题注意力。"
    assert "Musk-like account" not in watched_seed_rows[0]["display"]["summary_zh"]
    assert public_seed_rows == []
