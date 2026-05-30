from __future__ import annotations

from pathlib import Path


def test_news_brief_semantic_packet_excludes_fetch_time() -> None:
    type_text = Path("src/gmgn_twitter_intel/domains/news_intel/types/news_item_brief.py").read_text(
        encoding="utf-8"
    )
    assert "fetched_at_ms" not in type_text


def test_news_brief_input_builder_does_not_read_fetch_time() -> None:
    builder_text = Path(
        "src/gmgn_twitter_intel/domains/news_intel/services/news_item_brief_input.py"
    ).read_text(encoding="utf-8")
    assert "fetched_at_ms" not in builder_text


def test_narrative_mention_semantics_does_not_hash_claimed_rows_directly() -> None:
    text = Path("src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py").read_text(
        encoding="utf-8"
    )
    assert "input_hash = _hash_json(rows)" not in text
    assert "input_hash = _hash_json(_mention_semantics_input_rows(rows))" in text
