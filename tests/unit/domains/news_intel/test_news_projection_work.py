from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_page_projection_work,
    claim_story_brief_work,
    enqueue_page_reprojection,
    enqueue_story_brief_work,
    queue_story_brief_depth,
    story_brief_story_keys,
)

NOW_MS = 1_800_000


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claim_rows: list[dict[str, object]] = []
        self.queue_depth_calls: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms):
        del reason, now_ms
        rows = [dict(target) for target in targets]
        self.enqueued.extend(rows)
        return len(rows)

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claim_rows)

    def queue_depth(self, **kwargs):
        self.queue_depth_calls.append(dict(kwargs))
        return 42


class FakeNews:
    def __init__(self, servable_ids: list[str] | None = None) -> None:
        self.servable_ids = servable_ids
        self.calls: list[list[str]] = []

    def servable_news_item_ids(self, news_item_ids):
        ids = [str(news_item_id) for news_item_id in news_item_ids]
        self.calls.append(ids)
        if self.servable_ids is None:
            return ids
        return [news_item_id for news_item_id in ids if news_item_id in set(self.servable_ids)]


class FakeRepos:
    def __init__(self, servable_ids: list[str] | None = None) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()
        self.news_items = FakeNews(servable_ids)


def test_page_and_story_enqueues_use_stable_semantic_targets() -> None:
    repos = FakeRepos(["news-1"])

    assert (
        enqueue_page_reprojection(
            repos,
            news_item_ids=["news-1", "news-deleted"],
            source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 100},
            reason="fact_changed",
            now_ms=NOW_MS,
        )
        == 1
    )
    assert (
        enqueue_story_brief_work(
            repos,
            story_keys=["story-1", "story-1"],
            priority_by_story_key={"story-1": 11},
            source_watermark_ms_by_story_key={"story-1": NOW_MS - 50},
            reason="story_changed",
            now_ms=NOW_MS,
        )
        == 1
    )
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 100,
        },
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-1",
            "source_watermark_ms": NOW_MS - 50,
            "priority": 11,
        },
    ]


def test_page_enqueue_preserves_repository_attribute_error() -> None:
    repos = FakeRepos()

    def fail(_news_item_ids):
        raise AttributeError("repository query failed")

    repos.news_items.servable_news_item_ids = fail

    with pytest.raises(AttributeError, match="repository query failed"):
        enqueue_page_reprojection(
            repos,
            news_item_ids=["news-1"],
            source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 100},
            reason="fact_changed",
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize(
    ("call", "error"),
    [
        (
            lambda repos: enqueue_page_reprojection(
                repos,
                news_item_ids=["news-1"],
                reason="fact_changed",
                now_ms=NOW_MS,
            ),
            "news_projection_dirty_target_source_watermark_required",
        ),
        (
            lambda repos: enqueue_story_brief_work(
                repos,
                story_keys=["story-1"],
                reason="story_changed",
                now_ms=NOW_MS,
            ),
            "news_projection_dirty_target_source_watermark_required",
        ),
    ],
)
def test_projection_enqueues_require_source_watermarks(call, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        call(FakeRepos())


def test_claim_helpers_expose_only_page_and_story_work() -> None:
    repos = FakeRepos()
    repos.news_projection_dirty_targets.claim_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""}
    ]
    claim_page_projection_work(
        repos,
        limit=1,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="page-worker",
    )
    repos.news_projection_dirty_targets.claim_rows = []
    claim_story_brief_work(
        repos,
        limit=1,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="story-worker",
    )

    assert [call["projection_name"] for call in repos.news_projection_dirty_targets.claim_calls] == [
        "page",
        "story_brief",
    ]
    assert queue_story_brief_depth(repos, now_ms=NOW_MS) == 42


def test_story_claim_keys_are_strict_and_deduplicated() -> None:
    rows: list[dict[str, Any]] = [
        {"projection_name": "story_brief", "target_kind": "story", "target_id": "story-1", "window": ""},
        {"projection_name": "story_brief", "target_kind": "story", "target_id": "story-1", "window": ""},
    ]
    assert story_brief_story_keys(rows) == ["story-1"]

    rows[0]["window"] = "24h"
    with pytest.raises(ValueError, match="news_story_brief_claim_window_empty_required"):
        story_brief_story_keys(rows)
