from __future__ import annotations

from parallax.domains.news_intel.services.news_market_scope import infer_news_market_scope


def test_private_company_scope_is_market_relevant_not_crypto_filtered() -> None:
    scope = infer_news_market_scope(
        item={"title": "SpaceX discusses private company tender offer", "summary": "Shares trade privately."},
        entities=[{"entity_id": "entity-spacex", "raw_value": "SpaceX", "entity_type": "private_company"}],
        token_mentions=[],
        fact_candidates=[],
    )

    assert "private_company" in scope.domains
    assert "crypto" not in scope.domains


def test_nvidia_ai_chip_scope_marks_ai_semiconductors() -> None:
    scope = infer_news_market_scope(
        item={"title": "NVIDIA AI chip demand lifts semiconductor suppliers", "summary": "AI semis rally."},
        entities=[{"entity_id": "entity-nvda", "raw_value": "NVIDIA", "entity_type": "company"}],
        token_mentions=[],
        fact_candidates=[],
    )

    assert "ai_semiconductors" in scope.domains
    assert "us_equity" in scope.domains


def test_fed_rates_scope_marks_macro_rates() -> None:
    scope = infer_news_market_scope(
        item={"title": "Fed rate cut odds rise after inflation data", "summary": "Treasury yields fell."},
        entities=[{"entity_id": "entity-fed", "raw_value": "Federal Reserve", "entity_type": "regulator"}],
        token_mentions=[],
        fact_candidates=[],
    )

    assert scope.domains[0] == "macro_rates"


def test_crypto_token_mentions_mark_crypto_scope() -> None:
    scope = infer_news_market_scope(
        item={"title": "Exchange lists ABC perpetuals"},
        entities=[],
        token_mentions=[{"mention_id": "token-abc", "display_symbol": "ABC", "target_type": "Asset"}],
        fact_candidates=[],
    )

    assert "crypto" in scope.domains
