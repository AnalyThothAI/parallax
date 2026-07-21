from parallax.domains.narrative_intel.types.fingerprints import source_fingerprint


def test_source_fingerprint_is_order_insensitive_and_includes_source_watermark():
    first = source_fingerprint(["event-b", "event-a", "event-a"], 1234)
    second = source_fingerprint(["event-a", "event-b"], 1234)

    assert first == second
    assert first != source_fingerprint(["event-a", "event-b"], 1235)
