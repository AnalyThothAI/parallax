from gmgn_twitter_intel.pipeline.processing_policy import decide_processing
from gmgn_twitter_intel.pipeline.token_extractor import extract_token_entities
from gmgn_twitter_intel.pipeline.tweet_text import build_text_projection


def decision_for(text: str, *, matched: bool = False):
    projection = build_text_projection(text)
    return decide_processing(projection, extract_token_entities(projection.embedding_text), matched=matched)


def test_tokenless_off_topic_text_is_not_sent_to_embedding_queue():
    decision = decision_for("North Korea faces severe drought according to state media")

    assert decision.token_resolution_status == "no_token"
    assert decision.embedding_status == "skipped"
    assert "off_topic" in decision.quality_flags


def test_tokenless_crypto_signal_is_sent_to_embedding_queue():
    decision = decision_for("whale buy listing rumor gaining traction")

    assert decision.token_resolution_status == "no_token"
    assert decision.embedding_status == "pending"
    assert decision.processing_priority == 20
    assert "tokenless" in decision.quality_flags


def test_matched_meaningful_text_is_sent_to_embedding_queue():
    decision = decision_for("new base liquidity migration looks important", matched=True)

    assert decision.token_resolution_status == "no_token"
    assert decision.embedding_status == "pending"
    assert "matched_handle" in decision.quality_flags


def test_short_matched_chatter_is_not_sent_to_embedding_queue():
    decision = decision_for("okay noted", matched=True)

    assert decision.token_resolution_status == "no_token"
    assert decision.embedding_status == "skipped"
    assert "low_information" in decision.quality_flags
