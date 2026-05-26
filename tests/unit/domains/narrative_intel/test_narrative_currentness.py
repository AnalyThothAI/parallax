from gmgn_twitter_intel.domains.narrative_intel.types.narrative_currentness import (
    narrative_delta_from_currentness,
    public_currentness,
    unsupported_digest_sentinel,
)

NOW_MS = 1_800_000_000_000


def test_currentness_exact_ready_digest_is_current() -> None:
    currentness = public_currentness(
        digest={
            "status": "ready",
            "epoch_id": "epoch-1",
            "epoch_policy_version": "token-narrative-epoch-v1",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a", "event-b"],
            "independent_author_count": 2,
            "computed_at_ms": NOW_MS - 30_000,
            "display_current_until_ms": NOW_MS + 60_000,
        },
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a", "event-b"],
            "source_event_count": 2,
            "independent_author_count": 2,
            "next_digest_due_at_ms": NOW_MS + 60_000,
        },
        window="1h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "current"
    assert currentness["reason"] == "fingerprint_match"
    assert currentness["delta_source_event_count"] == 0
    assert currentness["ready_source_event_count"] == 2
    assert currentness["current_source_event_count"] == 2


def test_currentness_last_ready_with_delta_is_updating() -> None:
    currentness = public_currentness(
        digest={
            "status": "ready",
            "source_fingerprint": "source-ready",
            "source_event_ids_json": ["event-a", "event-b"],
            "independent_author_count": 1,
            "source_window_end_ms": NOW_MS - 120_000,
            "computed_at_ms": NOW_MS - 90_000,
            "display_current_until_ms": NOW_MS + 60_000,
        },
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a", "event-b", "event-c"],
            "source_event_count": 3,
            "independent_author_count": 2,
        },
        window="1h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "updating"
    assert currentness["reason"] == "digest_updating"
    assert currentness["delta_source_event_count"] == 1
    assert currentness["delta_independent_author_count"] == 1
    assert currentness["delta_since_ms"] == NOW_MS - 120_000

    delta = narrative_delta_from_currentness(currentness)
    assert delta["display_status"] == "updating"
    assert delta["delta_source_event_count"] == 1


def test_currentness_last_ready_past_display_until_is_stale() -> None:
    currentness = public_currentness(
        digest={
            "status": "ready",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a"],
            "display_current_until_ms": NOW_MS - 1,
            "computed_at_ms": NOW_MS - 300_000,
        },
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a"],
            "source_event_count": 1,
        },
        window="1h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "stale"
    assert currentness["reason"] == "ttl_refresh_due"
    assert currentness["last_ready_computed_at_ms"] == NOW_MS - 300_000


def test_currentness_no_ready_with_admission_is_not_ready() -> None:
    currentness = public_currentness(
        digest=None,
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a"],
            "source_event_count": 1,
            "independent_author_count": 1,
        },
        window="1h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "not_ready"
    assert currentness["reason"] == "no_ready_digest"
    assert currentness["current_source_event_count"] == 1


def test_currentness_unsupported_5m_is_unsupported_window() -> None:
    currentness = public_currentness(
        digest=None,
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a"],
            "source_event_count": 1,
        },
        window="5m",
        now_ms=NOW_MS,
    )
    sentinel = unsupported_digest_sentinel(
        target_type="chain_token",
        target_id="solana:So111",
        window="5m",
        scope="matched",
        schema_version="narrative_intel_v1",
    )

    assert currentness["display_status"] == "unsupported_window"
    assert currentness["reason"] == "unsupported_window"
    assert sentinel["status"] == "pending"
    assert sentinel["currentness"]["display_status"] == "unsupported_window"
    assert sentinel["data_gaps_json"] == [{"reason": "narrative_not_supported_for_window"}]


def test_currentness_unsupported_24h_is_unsupported_window() -> None:
    currentness = public_currentness(
        digest=None,
        admission={
            "status": "admitted",
            "source_fingerprint": "source-current",
            "source_event_ids_json": ["event-a"],
            "source_event_count": 1,
        },
        window="24h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "unsupported_window"
    assert currentness["reason"] == "unsupported_window"


def test_currentness_out_of_frontier_is_not_current() -> None:
    currentness = public_currentness(
        digest={
            "status": "ready",
            "source_fingerprint": "source-ready",
            "source_event_ids_json": ["event-a"],
            "computed_at_ms": NOW_MS - 90_000,
        },
        admission=None,
        window="1h",
        now_ms=NOW_MS,
    )

    assert currentness["display_status"] == "out_of_frontier"
    assert currentness["reason"] == "not_in_current_frontier"
    assert currentness["ready_source_event_count"] == 1
