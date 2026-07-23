from __future__ import annotations

import pytest

from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_page_projection_work,
    enqueue_page_reprojection,
)

NOW_MS = 1_800_000


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claim_rows: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms):
        del reason, now_ms
        rows = [dict(target) for target in targets]
        self.enqueued.extend(rows)
        return len(rows)

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claim_rows)


class FakeNews:
    def __init__(self, servable_ids: list[str] | None = None) -> None:
        self.servable_ids = servable_ids

    def servable_news_item_ids(self, news_item_ids):
        ids = [str(news_item_id) for news_item_id in news_item_ids]
        if self.servable_ids is None:
            return ids
        return [news_item_id for news_item_id in ids if news_item_id in set(self.servable_ids)]


class FakeRepos:
    def __init__(self, servable_ids: list[str] | None = None) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()
        self.news_items = FakeNews(servable_ids)


def test_page_enqueue_uses_stable_fact_projection_target() -> None:
    repos = FakeRepos(["news-1"])

    inserted = enqueue_page_reprojection(
        repos,
        news_item_ids=["news-1", "news-deleted"],
        source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 100},
        reason="fact_changed",
        now_ms=NOW_MS,
    )

    assert inserted == 1
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 100,
        }
    ]


def test_page_enqueue_requires_source_watermark() -> None:
    with pytest.raises(ValueError, match="news_projection_dirty_target_source_watermark_required"):
        enqueue_page_reprojection(
            FakeRepos(),
            news_item_ids=["news-1"],
            reason="fact_changed",
            now_ms=NOW_MS,
        )


def test_page_claim_uses_only_page_projection() -> None:
    repos = FakeRepos()
    repos.news_projection_dirty_targets.claim_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""}
    ]

    rows = claim_page_projection_work(
        repos,
        limit=1,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="page-worker",
    )

    assert rows[0]["target_id"] == "news-1"
    assert repos.news_projection_dirty_targets.claim_calls[0]["projection_name"] == "page"
