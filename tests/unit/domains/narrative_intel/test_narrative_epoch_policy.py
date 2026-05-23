from gmgn_twitter_intel.domains.narrative_intel.services.narrative_epoch_policy import (
    DEFAULT_THRESHOLDS,
    DIGEST_WINDOWS,
    EPOCH_POLICY_VERSION,
    NarrativeEpochPolicy,
)

NOW_MS = 1_800_000_000_000


def _admission(
    *,
    window: str = "1h",
    source_event_ids: list[str] | None = None,
    author_ids: list[str] | None = None,
) -> dict[str, object]:
    source_event_ids = source_event_ids if source_event_ids is not None else ["event-1", "event-2", "event-3"]
    author_ids = author_ids if author_ids is not None else ["author-1", "author-2"]
    return {
        "window": window,
        "source_event_ids": source_event_ids,
        "source_event_count": len(source_event_ids),
        "author_ids": author_ids,
        "independent_author_count": len(set(author_ids)),
    }


def _ready_digest(
    *,
    source_event_ids: list[str] | None = None,
    author_ids: list[str] | None = None,
    display_current_until_ms: int | None = None,
) -> dict[str, object]:
    return {
        "status": "ready",
        "source_event_ids_json": source_event_ids
        if source_event_ids is not None
        else ["event-1", "event-2", "event-3"],
        "author_ids": author_ids if author_ids is not None else ["author-1", "author-2"],
        "display_current_until_ms": display_current_until_ms if display_current_until_ms is not None else NOW_MS + 1,
    }


def _coverage(
    *,
    source_event_count: int = 3,
    missing: int = 0,
    pending: int = 0,
    retryable: int = 0,
) -> dict[str, int]:
    return {
        "source_event_count": source_event_count,
        "missing_semantic_count": missing,
        "pending_semantic_count": pending,
        "retryable_semantic_count": retryable,
    }


def test_unsupported_5m_window_never_refreshes_or_writes_status_digest() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(window="5m"),
        current_ready_digest=None,
        semantic_coverage=_coverage(),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "unsupported_window"
    assert decision.should_refresh is False
    assert decision.should_write_status_digest is False
    assert decision.next_due_at_ms == NOW_MS + 24 * 60 * 60 * 1000
    assert decision.epoch_policy_version == EPOCH_POLICY_VERSION


def test_ready_digest_plus_one_new_source_below_threshold_returns_no_material_delta() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(source_event_ids=["event-1", "event-2", "event-3", "event-4"]),
        current_ready_digest=_ready_digest(source_event_ids=["event-1", "event-2", "event-3"]),
        semantic_coverage=_coverage(source_event_count=4),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "no_material_delta"
    assert decision.should_refresh is False
    assert decision.should_write_status_digest is False


def test_no_ready_digest_with_sufficient_source_and_semantic_coverage_refreshes_initial_ready() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(),
        current_ready_digest=None,
        semantic_coverage=_coverage(),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "no_ready_digest"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False
    assert decision.refresh_reason == "initial_ready"


def test_new_source_or_author_delta_above_threshold_returns_material_delta_due() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(
            source_event_ids=["event-1", "event-2", "event-3", "event-4"],
            author_ids=["author-1", "author-2", "author-3"],
        ),
        current_ready_digest=_ready_digest(
            source_event_ids=["event-1", "event-2", "event-3"],
            author_ids=["author-1"],
        ),
        semantic_coverage=_coverage(source_event_count=4),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "material_delta_due"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False
    assert decision.refresh_reason == "material_delta_due"


def test_expired_display_current_until_returns_ttl_refresh_due() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(),
        current_ready_digest=_ready_digest(display_current_until_ms=NOW_MS - 1),
        semantic_coverage=_coverage(),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "ttl_refresh_due"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False
    assert decision.refresh_reason == "ttl_refresh_due"


def test_missing_or_pending_semantics_without_ready_digest_returns_initial_ready() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(),
        current_ready_digest=None,
        semantic_coverage=_coverage(missing=1, pending=1, retryable=1),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "no_ready_digest"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False
    assert decision.refresh_reason == "initial_ready"


def test_missing_or_pending_semantics_with_ready_digest_does_not_write_status_digest() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(source_event_ids=["event-1", "event-2", "event-3", "event-4"]),
        current_ready_digest=_ready_digest(source_event_ids=["event-1", "event-2", "event-3"]),
        semantic_coverage=_coverage(source_event_count=4, missing=2, pending=1),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "no_material_delta"
    assert decision.should_refresh is False
    assert decision.should_write_status_digest is False


def test_missing_or_pending_semantics_with_ready_digest_still_refreshes_on_material_delta() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(
            source_event_ids=["event-1", "event-2", "event-3", "event-4", "event-5", "event-6"],
            author_ids=["author-1", "author-2", "author-3"],
        ),
        current_ready_digest=_ready_digest(
            source_event_ids=["event-1", "event-2", "event-3"],
            author_ids=["author-1", "author-2"],
        ),
        semantic_coverage=_coverage(source_event_count=6, pending=2),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "material_delta_due"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False


def test_price_move_over_threshold_returns_material_delta_due() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission=_admission(),
        current_ready_digest=_ready_digest(),
        semantic_coverage=_coverage(),
        market_context={"price_move_pct": -12.1},
        now_ms=NOW_MS,
    )

    assert decision.reason == "material_delta_due"
    assert decision.should_refresh is True
    assert decision.should_write_status_digest is False
    assert decision.refresh_reason == "material_delta_due"


def test_source_event_id_json_strings_are_parsed_for_delta_detection() -> None:
    decision = NarrativeEpochPolicy().evaluate(
        admission={
            "window": "1h",
            "source_event_ids_json": '["event-1","event-2","event-3","event-4","event-5","event-6"]',
            "source_event_count": 6,
            "independent_author_count": 2,
        },
        current_ready_digest={
            "source_event_ids_json": '["event-1","event-2","event-3"]',
            "independent_author_count": 2,
            "display_current_until_ms": NOW_MS + 1,
        },
        semantic_coverage=_coverage(source_event_count=6),
        market_context=None,
        now_ms=NOW_MS,
    )

    assert decision.reason == "material_delta_due"
    assert decision.should_refresh is True


def test_epoch_policy_hard_cuts_digest_windows_to_1h() -> None:
    assert frozenset({"1h"}) == DIGEST_WINDOWS
    assert set(DEFAULT_THRESHOLDS) == {"1h"}

    decision = NarrativeEpochPolicy().evaluate(
        admission={"window": "4h", "source_event_count": 10, "independent_author_count": 4},
        current_ready_digest=None,
        semantic_coverage={"source_event_count": 10, "missing_semantic_count": 0},
        market_context={},
        now_ms=10_000,
    )

    assert decision.reason == "unsupported_window"
    assert decision.should_refresh is False
    assert decision.should_write_status_digest is False
