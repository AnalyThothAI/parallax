from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.retrieval.token_target_posts_service import TokenTargetPostsService


def test_target_posts_cursor_keeps_same_millisecond_rows_reachable():
    targets = FakeTargets(
        pages={
            None: [
                post_row("event-3", received_at_ms=1_000),
                post_row("event-2", received_at_ms=1_000),
                post_row("event-1", received_at_ms=1_000),
            ],
            (1_000, "event-2"): [post_row("event-1", received_at_ms=1_000)],
        }
    )
    service = TokenTargetPostsService(targets=targets)

    first = service.target_posts(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        post_range="current_window",
        sort="recent",
        limit=2,
        cursor=None,
        now_ms=2_000_000,
    )
    second = service.target_posts(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        post_range="current_window",
        sort="recent",
        limit=2,
        cursor=first["next_cursor"],
        now_ms=2_000_000,
    )

    assert first["query"]["target_type"] == "CexToken"
    assert first["query"]["target_id"] == "cex_token:BTC"
    assert [item["event_id"] for item in first["items"]] == ["event-3", "event-2"]
    assert isinstance(first["items"][0]["attribution_confidence"], float)
    assert first["next_cursor"] == "1000:event-2"
    assert targets.seen_cursors[-1] == (1_000, "event-2")
    assert [item["event_id"] for item in second["items"]] == ["event-1"]


class FakeTargets:
    def __init__(self, *, pages):
        self.pages = pages
        self.seen_cursors = []

    def timeline_rows(self, *, target_type, target_id, since_ms, watched_only, limit, cursor=None):
        self.seen_cursors.append(cursor)
        return self.pages.get(cursor, [])[:limit]


def post_row(event_id: str, *, received_at_ms: int) -> dict:
    return {
        "event_id": event_id,
        "tweet_id": event_id,
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "symbol": "BTC",
        "author_handle": "alice",
        "text": "$BTC",
        "text_clean": "$BTC",
        "canonical_url": f"https://x.com/alice/status/{event_id}",
        "is_watched": False,
        "received_at_ms": received_at_ms,
        "attribution_status": "EXACT",
        "confidence": Decimal("0.95"),
        "reference_json": None,
    }
