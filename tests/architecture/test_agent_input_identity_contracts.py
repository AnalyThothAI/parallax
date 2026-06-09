from __future__ import annotations

from pathlib import Path


def test_news_brief_semantic_packet_excludes_fetch_time() -> None:
    type_text = Path("src/parallax/domains/news_intel/types/news_item_brief.py").read_text(encoding="utf-8")
    assert "fetched_at_ms" not in type_text


def test_news_brief_input_builder_does_not_read_fetch_time() -> None:
    builder_text = Path("src/parallax/domains/news_intel/services/news_item_brief_input.py").read_text(encoding="utf-8")
    assert "fetched_at_ms" not in builder_text


def test_deleted_narrative_llm_agents_do_not_reintroduce_input_hash_paths() -> None:
    assert not Path("src/parallax/domains/narrative_intel/runtime/mention_semantics_worker.py").exists()
    assert not Path("src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py").exists()
    assert not Path("src/parallax/integrations/model_execution/narrative_intel_agent_client.py").exists()
