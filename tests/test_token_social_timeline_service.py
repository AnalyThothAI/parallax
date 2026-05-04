import pytest

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.retrieval.token_social_timeline_service import (
    TokenSocialTimelineIdentityError,
    TokenSocialTimelineService,
)
from tests.test_token_rolling_flow import open_runtime, token_event


def test_token_social_timeline_buckets_posts_and_authors(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index, handle in enumerate(["seed", "amp", "amp"]):
            ingest.ingest_event(
                token_event(
                    f"event-dog-timeline-{index}",
                    received_at_ms=now_ms - 180_000 + index * 30_000,
                    author_handle=handle,
                    text=f"$DOG mcap liquidity timeline {index}",
                ),
                is_watched=index == 0,
            )
        token_item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]

        data = TokenSocialTimelineService(signals=signals).timeline(
            token_id=token_item["identity"]["token_id"],
            window="1h",
            bucket="1m",
            scope="all",
            limit=2,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert data["summary"]["posts"] == 3
    assert data["summary"]["authors"] == 2
    assert data["summary"]["top_author_share"] == pytest.approx(2 / 3)
    assert len(data["buckets"]) == 2
    assert sum(bucket["posts"] for bucket in data["buckets"]) == 3
    assert [author["handle"] for author in data["authors"]] == ["amp", "seed"]
    assert data["authors"][0]["role"] in {"amplifier", "early_amplifier"}
    assert data["authors"][1]["role"] == "watched"
    assert data["returned_count"] == 2
    assert data["has_more"] is True
    assert data["next_cursor"]


def test_token_social_timeline_paginates_posts_from_complete_summary(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index in range(3):
            ingest.ingest_event(
                token_event(
                    f"event-dog-page-{index}",
                    received_at_ms=now_ms - (index + 1) * 1_000,
                    author_handle=f"voice{index}",
                    text=f"$DOG page {index}",
                ),
                is_watched=False,
            )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]
        first_page = TokenSocialTimelineService(signals=signals).timeline(
            token_id=token_id,
            window="1h",
            bucket="1m",
            scope="all",
            limit=2,
            now_ms=now_ms,
        )
        second_page = TokenSocialTimelineService(signals=signals).timeline(
            token_id=token_id,
            window="1h",
            bucket="1m",
            scope="all",
            limit=2,
            cursor=first_page["next_cursor"],
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert first_page["summary"]["posts"] == 3
    assert second_page["summary"]["posts"] == 3
    assert [post["event_id"] for post in first_page["posts"]] == ["event-dog-page-0", "event-dog-page-1"]
    assert [post["event_id"] for post in second_page["posts"]] == ["event-dog-page-2"]
    assert second_page["has_more"] is False


def test_token_social_timeline_price_overlay_uses_market_snapshots(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_300_000
        first_ms = now_ms - 180_000
        second_ms = now_ms - 120_000
        ingest.ingest_event(
            token_event(
                "event-dog-price-start",
                received_at_ms=first_ms,
                author_handle="seed",
                text="$DOG price start",
            ),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event(
                "event-dog-price-next",
                received_at_ms=second_ms,
                author_handle="amp",
                text="$DOG price next",
            ),
            is_watched=False,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-price-next",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.2",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=second_ms,
            source_channel="gmgn_openapi_token_info",
        )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        data = TokenSocialTimelineService(signals=signals).timeline(
            token_id=token_id,
            window="1h",
            bucket="1m",
            scope="all",
            limit=10,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    prices = [bucket["price"] for bucket in data["buckets"]]
    changes = [bucket["price_change_from_start_pct"] for bucket in data["buckets"]]
    assert prices == [1.0, 1.2]
    assert changes == [0.0, 0.2]


def test_token_social_timeline_pages_posts_in_sql_not_python(monkeypatch, tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    captured_limits: list[int | None] = []
    original = TokenSocialTimelineService._post_rows

    def guarded_post_rows(self, **kwargs):
        captured_limits.append(kwargs.get("limit"))
        return original(self, **kwargs)

    monkeypatch.setattr(TokenSocialTimelineService, "_post_rows", guarded_post_rows)
    try:
        now_ms = 1_700_000_123_456
        for index in range(5):
            ingest.ingest_event(
                token_event(
                    f"event-dog-sql-page-{index}",
                    received_at_ms=now_ms - (index + 1) * 1_000,
                    author_handle=f"voice{index}",
                    text=f"$DOG sql page {index}",
                ),
                is_watched=False,
            )
        token_id = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]["identity"]["token_id"]

        data = TokenSocialTimelineService(signals=signals).timeline(
            token_id=token_id,
            window="1h",
            bucket="1m",
            scope="all",
            limit=2,
            now_ms=now_ms,
        )
    finally:
        conn.close()

    assert captured_limits == [3]
    assert data["summary"]["posts"] == 5
    assert [post["event_id"] for post in data["posts"]] == ["event-dog-sql-page-0", "event-dog-sql-page-1"]


def test_token_social_timeline_requires_token_identity(tmp_path):
    conn, _, signals, _ = open_runtime(tmp_path)
    try:
        with pytest.raises(TokenSocialTimelineIdentityError):
            TokenSocialTimelineService(signals=signals).timeline(
                window="1h",
                bucket="1m",
                scope="all",
                limit=10,
            )
    finally:
        conn.close()
