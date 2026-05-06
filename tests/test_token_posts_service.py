import pytest

from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.retrieval.token_posts_service import TokenPostsRangeError, TokenPostsService
from tests.test_token_rolling_flow import open_runtime, token_event


def test_token_posts_returns_distinct_paginated_attributed_posts(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index in range(3):
            ingest.ingest_event(
                token_event(
                    f"event-dog-post-{index}",
                    received_at_ms=now_ms - (index + 1) * 1_000,
                    author_handle=f"voice{index}",
                    text=f"$DOG post {index}",
                ),
                is_watched=index == 0,
            )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        first_page = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="all",
            limit=2,
            now_ms=now_ms,
        )
        second_page = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="all",
            limit=2,
            cursor=first_page["next_cursor"],
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert first_page["total_count"] == 3
    assert first_page["query"]["range"] == "current_window"
    assert first_page["score_window"] == {"window": "1h"}
    assert first_page["returned_count"] == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert [item["event_id"] for item in first_page["items"]] == ["event-dog-post-0", "event-dog-post-1"]
    assert second_page["total_count"] == 3
    assert second_page["returned_count"] == 1
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None
    assert [item["event_id"] for item in second_page["items"]] == ["event-dog-post-2"]
    assert first_page["items"][0]["post_quality"]["score_version"] == "post_quality_v1"
    assert first_page["items"][0]["post_quality"]["contributions"]
    assert "score" not in first_page["items"][0]
    assert "evidence" not in first_page["items"][0]


def test_token_posts_scope_filters_to_watched_attributions(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-watched", received_at_ms=now_ms - 1_000, author_handle="toly"),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event("event-dog-public", received_at_ms=now_ms - 2_000, author_handle="anon"),
            is_watched=False,
        )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        watched_page = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="matched",
            limit=10,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert watched_page["total_count"] == 1
    assert [item["event_id"] for item in watched_page["items"]] == ["event-dog-watched"]


def test_token_posts_all_history_range_is_paginated_and_separate_from_score_window(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-old-history", received_at_ms=now_ms - 3 * 60 * 60_000, author_handle="old"),
            is_watched=False,
        )
        ingest.ingest_event(
            token_event("event-dog-current-window", received_at_ms=now_ms - 5_000, author_handle="new"),
            is_watched=False,
        )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        current_window = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="all",
            limit=10,
            now_ms=now_ms,
        )
        all_history = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="all",
            post_range="all_history",
            limit=10,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert current_window["query"]["range"] == "current_window"
    assert current_window["total_count"] == 1
    assert [item["event_id"] for item in current_window["items"]] == ["event-dog-current-window"]
    assert all_history["query"]["range"] == "all_history"
    assert all_history["score_window"] == {"window": "1h"}
    assert all_history["total_count"] == 2
    assert [item["event_id"] for item in all_history["items"]] == [
        "event-dog-current-window",
        "event-dog-old-history",
    ]


def test_token_posts_catalyst_sort_ranks_independent_followups_over_copy_pasta(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_600_000
        root_ms = now_ms - 40 * 60_000
        spam_ms = now_ms - 35 * 60_000
        ingest.ingest_event(
            token_event(
                "event-dog-catalyst-root",
                received_at_ms=root_ms,
                author_handle="origin",
                text="$DOG original thesis",
            ),
            is_watched=False,
        )
        for index in range(5):
            ingest.ingest_event(
                token_event(
                    f"event-dog-independent-{index}",
                    received_at_ms=root_ms + (index + 1) * 60_000,
                    author_handle=f"independent{index}",
                    text=f"$DOG independent follow-up {index}",
                ),
                is_watched=False,
            )
        ingest.ingest_event(
            token_event(
                "event-dog-spam-root",
                received_at_ms=spam_ms,
                author_handle="spamroot",
                text="$DOG spam seed",
            ),
            is_watched=False,
        )
        for index in range(30):
            ingest.ingest_event(
                token_event(
                    f"event-dog-copy-{index}",
                    received_at_ms=spam_ms + (index + 1) * 1_000,
                    author_handle="copypasta",
                    text="$DOG copy paste raid",
                ),
                is_watched=False,
            )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        catalyst_page = TokenPostsService(signals=signals).token_posts(
            token_id=token_id,
            window="1h",
            scope="all",
            limit=10,
            sort="catalyst",
            now_ms=now_ms,
        )
    finally:
        conn.close()

    scores = {item["event_id"]: item["catalyst_score"] for item in catalyst_page["items"]}
    assert catalyst_page["query"]["sort"] == "catalyst"
    assert catalyst_page["has_more"] is False
    assert catalyst_page["next_cursor"] is None
    assert catalyst_page["items"][0]["event_id"] == "event-dog-catalyst-root"
    assert scores["event-dog-catalyst-root"] >= scores["event-dog-spam-root"] * 3
    assert catalyst_page["items"][0]["catalyst_components"]["independent_authors"] == 7


def test_token_posts_rejects_unknown_range(tmp_path):
    conn, _, signals, _ = open_runtime(tmp_path)
    try:
        with pytest.raises(TokenPostsRangeError):
            TokenPostsService(signals=signals).token_posts(
                token_id="token:sol:abc",
                window="1h",
                scope="all",
                post_range="legacy",
                limit=10,
            )
    finally:
        conn.close()
