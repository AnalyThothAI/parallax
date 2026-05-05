import pytest

from gmgn_twitter_intel.retrieval.timeline_features import bucket_width_ms, build_timeline_features


def event(event_id, *, received_at_ms, handle, text="same text", watched=False):
    return {
        "event_id": event_id,
        "received_at_ms": received_at_ms,
        "author_handle": handle,
        "text_clean": text,
        "is_watched": 1 if watched else 0,
    }


def test_timeline_feature_bucket_widths_follow_window_contract():
    assert bucket_width_ms("5m") == 30_000
    assert bucket_width_ms("1h") == 300_000
    assert bucket_width_ms("4h") == 15 * 60_000
    assert bucket_width_ms("24h") == 3_600_000


def test_timeline_features_count_new_authors_by_first_bucket_and_entropy():
    start_ms = 1_700_000_000_000
    features = build_timeline_features(
        [
            event("event-a1", received_at_ms=start_ms + 10_000, handle="alice", text="alpha", watched=True),
            event("event-a2", received_at_ms=start_ms + 40_000, handle="alice", text="alpha update"),
            event("event-b1", received_at_ms=start_ms + 70_000, handle="bob", text="beta"),
        ],
        window="5m",
        window_start_ms=start_ms,
        window_end_ms=start_ms + 300_000,
    )

    assert len(features["buckets"]) == 10
    assert features["summary"]["independent_authors"] == 2
    assert features["summary"]["new_authors_total"] == 2
    assert features["summary"]["effective_authors"] == pytest.approx(1.8899)
    assert features["buckets"][0]["new_authors"] == 1
    assert features["buckets"][1]["new_authors"] == 0
    assert features["buckets"][2]["new_authors"] == 1
    assert features["buckets"][0]["watched_authors"] == 1
    assert features["summary"]["peak_reproduction_rate"] == pytest.approx(1.0)


def test_timeline_features_detect_duplicate_concentration():
    start_ms = 1_700_000_000_000
    features = build_timeline_features(
        [
            event("event-a", received_at_ms=start_ms + 1_000, handle="alice", text="same"),
            event("event-b", received_at_ms=start_ms + 2_000, handle="bob", text="same"),
            event("event-c", received_at_ms=start_ms + 3_000, handle="carol", text="same"),
        ],
        window="5m",
        window_start_ms=start_ms,
        window_end_ms=start_ms + 300_000,
    )

    assert features["summary"]["duplicate_text_share"] == pytest.approx(1.0)
    assert features["summary"]["phase_inputs"]["duplicate_text_share"] == pytest.approx(1.0)
