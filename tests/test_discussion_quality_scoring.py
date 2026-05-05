from gmgn_twitter_intel.retrieval.discussion_quality_scoring import discussion_quality_score, post_quality_score


def test_discussion_quality_rewards_direct_ca_and_original_context():
    score = discussion_quality_score(
        {
            "mentions": 5,
            "direct_mentions": 4,
            "avg_attribution_confidence": 0.93,
            "duplicate_text_share": 0.05,
            "informative_post_count": 4,
            "watched_source_count": 1,
            "market_context_count": 3,
        }
    )

    assert score["score_version"] == "discussion_quality_v2"
    assert score["score"] >= 75
    assert "resolved_direct_evidence" in score["reasons"]
    assert "informative_discussion" in score["reasons"]
    assert "duplicate_text_cluster" not in score["risks"]
    assert score["data_health"]["deterministic_text_quality"] == "ready"


def test_discussion_quality_caps_repeated_text_clusters():
    score = discussion_quality_score(
        {
            "mentions": 6,
            "direct_mentions": 6,
            "avg_attribution_confidence": 0.9,
            "duplicate_text_share": 0.55,
            "informative_post_count": 1,
            "watched_source_count": 1,
            "market_context_count": 0,
        }
    )

    assert "duplicate_text_cluster" in score["risks"]
    assert score["score"] <= 45
    assert any(cap["risk"] == "duplicate_text_cluster" and cap["cap"] == 45 for cap in score["risk_caps"])


def test_discussion_quality_llm_label_cannot_rescue_weak_deterministic_quality():
    score = discussion_quality_score(
        {
            "mentions": 6,
            "direct_mentions": 1,
            "avg_attribution_confidence": 0.5,
            "duplicate_text_share": 0.1,
            "informative_post_count": 0,
            "watched_source_count": 0,
            "market_context_count": 0,
            "llm_semantic_utility": 1.0,
            "llm_label_confidence": 0.95,
        }
    )

    assert "llm_label_capped_by_deterministic_quality" in score["risks"]
    assert score["score"] <= 70


def test_post_quality_scores_informative_ca_posts():
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
