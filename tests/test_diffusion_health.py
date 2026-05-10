import importlib


def _diffusion_module():
    try:
        return importlib.import_module("gmgn_twitter_intel.domains.token_intel.scoring.diffusion_health")
    except ModuleNotFoundError as exc:
        raise AssertionError("diffusion_health module is missing") from exc


def test_text_fingerprint_ignores_urls_and_contracts():
    module = _diffusion_module()

    assert (
        module.text_fingerprint(
            "BULLISH &amp; early $DOG https://gmgn.ai/eth/token "
            "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 "
            "7YttLkHDoJYpyLhVvL3Vp1JZj3hDeRkKjM1u7L7g8K9"
        )
        == "bullish & early $dog"
    )


def test_diffusion_health_marks_healthy_independent_authors():
    module = _diffusion_module()

    health = module.diffusion_health(
        mentions=[
            {"author_handle": "alpha", "text_clean": "$DOG first clean break", "is_watched": True},
            {"author_handle": "bravo", "text_clean": "$DOG volume expanding"},
            {"author_handle": "charlie", "text_clean": "$DOG buyers holding the reclaim"},
        ],
        watched_author_handles={"alpha"},
    )

    assert health["status"] == "healthy"
    assert health["score"] > 70
    assert health["independent_authors"] == 3
    assert health["effective_authors"] == 3
    assert health["top_author_share"] == 1 / 3
    assert health["duplicate_text_share"] == 1 / 3
    assert health["repeated_cluster_count"] == 0
    assert health["shill_author_count"] == 0
    assert health["top_authors"][0]["handle"] == "alpha"
    assert "multi_author" in health["reasons"]
    assert "watched_author_present" in health["reasons"]
    assert health["risks"] == []


def test_diffusion_health_marks_concentrated_single_author():
    module = _diffusion_module()

    health = module.diffusion_health(
        mentions=[
            {"author_handle": "singlevoice", "text_clean": "$DOG push one"},
            {"author_handle": "singlevoice", "text_clean": "$DOG push two"},
            {"author_handle": "singlevoice", "text_clean": "$DOG push three"},
            {"author_handle": "singlevoice", "text_clean": "$DOG push four"},
        ],
        watched_author_handles=set(),
    )

    assert health["status"] == "concentrated"
    assert health["independent_authors"] == 1
    assert health["top_author_share"] == 1.0
    assert health["shill_author_count"] == 0
    assert "author_concentration_high" in health["risks"]
    assert "thin_author_set" in health["risks"]


def test_diffusion_health_marks_repeated_text_cluster_across_authors():
    module = _diffusion_module()

    health = module.diffusion_health(
        mentions=[
            {"author_handle": "alpha", "text_clean": "$DOG breakout now"},
            {"author_handle": "bravo", "text_clean": "$DOG breakout now https://example.com/a"},
            {
                "author_handle": "charlie",
                "text_clean": "$DOG breakout now 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            },
            {"author_handle": "delta", "text_clean": "$DOG independent take"},
        ],
        watched_author_handles=set(),
    )

    assert health["status"] == "repeated"
    assert health["independent_authors"] == 4
    assert health["effective_authors"] == 2
    assert health["top_author_share"] == 0.25
    assert health["duplicate_text_share"] == 0.75
    assert health["repeated_cluster_count"] == 1
    assert "repeated_text_cluster" in health["risks"]
