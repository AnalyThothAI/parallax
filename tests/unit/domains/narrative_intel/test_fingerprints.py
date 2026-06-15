from parallax.domains.narrative_intel.types.fingerprints import (
    label_fingerprint,
    source_fingerprint,
    text_fingerprint,
)


def test_text_fingerprint_normalizes_whitespace_and_case():
    assert text_fingerprint("  BUY   $SOL\nNow\t") == text_fingerprint("buy $sol now")


def test_source_fingerprint_is_order_insensitive_and_includes_source_watermark():
    first = source_fingerprint(["event-b", "event-a", "event-a"], 1234)
    second = source_fingerprint(["event-a", "event-b"], 1234)

    assert first == second
    assert first != source_fingerprint(["event-a", "event-b"], 1235)


def test_label_fingerprint_is_order_insensitive_and_buckets_confidence_and_time():
    rows = [
        {
            "semantic_id": "semantic-2",
            "trade_stance": "bearish",
            "attention_valence": "panic",
            "narrative_cluster_key": "risk",
            "semantic_confidence": 0.849,
            "computed_at_ms": 10_999,
        },
        {
            "semantic_id": "semantic-1",
            "trade_stance": "bullish",
            "attention_valence": "celebratory",
            "narrative_cluster_key": "breakout",
            "semantic_confidence": 0.811,
            "computed_at_ms": 10_001,
        },
    ]
    reordered = list(reversed(rows))

    assert label_fingerprint(rows) == label_fingerprint(reordered)
    assert label_fingerprint(rows) != label_fingerprint([{**rows[0], "trade_stance": "neutral"}, rows[1]])
