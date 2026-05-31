from __future__ import annotations

from parallax.domains.token_intel.scoring.post_text_quality import post_quality_score


def test_post_quality_scores_informative_ca_posts() -> None:
    score = post_quality_score(
        {
            "text": "$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 new pool live, mcap under 2m",
            "mention_source": "gmgn_token_payload",
            "attribution_status": "direct",
            "attribution_confidence": 0.96,
            "attribution_weight": 1.0,
            "is_watched": True,
        }
    )

    assert score["score_version"] == "post_quality_v1"
    assert score["score"] >= 80
    assert "contains_contract_address" in score["reasons"]
    assert "market_context_present" in score["reasons"]
