from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.retrieval.token_posts_service import TokenPostsService
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
