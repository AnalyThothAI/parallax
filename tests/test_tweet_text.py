from gmgn_twitter_intel.pipeline.tweet_text import build_text_projection


def test_text_projection_preserves_display_text_and_builds_search_text():
    projection = build_text_projection(
        "🚀 $PEPE is live https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 @maker #memecoin",
        reference_text="quoted $DOGE context",
    )

    assert projection.text_raw.startswith("🚀 $PEPE")
    assert projection.text_clean.startswith("$PEPE is live")
    assert projection.embedding_text == "$PEPE is live @maker #memecoin\nquoted $DOGE context"
    assert projection.urls == ["https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933"]
    assert projection.cashtags == ["PEPE"]
    assert projection.hashtags == ["memecoin"]
    assert projection.mentions == ["maker"]


def test_text_projection_handles_empty_media_only_tweets():
    projection = build_text_projection(None)

    assert projection.text_raw is None
    assert projection.text_clean is None
    assert projection.embedding_text is None
    assert projection.urls == []
