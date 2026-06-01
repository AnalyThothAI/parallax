from __future__ import annotations

from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_item_brief_work,
    claim_page_projection_work,
    claim_source_quality_work,
    enqueue_item_brief_work,
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
    page_news_item_ids,
    source_quality_windows_for_claimed,
)

NOW_MS = 1_800_000


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claim_rows: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms, due_at_ms=None, commit=True):
        self.enqueued.extend(dict(target) for target in targets)
        self.reason = reason
        self.now_ms = now_ms
        self.due_at_ms = due_at_ms
        self.commit = commit
        return len(self.enqueued)

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claim_rows)


class FakeRepos:
    def __init__(self) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()


def test_enqueue_page_reprojection_hides_page_projection_name() -> None:
    repos = FakeRepos()

    count = enqueue_page_reprojection(
        repos,
        news_item_ids=["news-1", "news-1", ""],
        reason="news_item_processed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 1
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"}
    ]


def test_enqueue_item_brief_work_sets_priority_by_item_id() -> None:
    repos = FakeRepos()

    count = enqueue_item_brief_work(
        repos,
        news_item_ids=["news-1", "news-2"],
        priority_by_news_item_id={"news-1": 7},
        reason="news_item_processed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 2
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-1", "priority": 7},
        {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-2"},
    ]


def test_source_quality_refresh_is_source_scoped_not_window_fanout() -> None:
    repos = FakeRepos()

    count = enqueue_source_quality_refresh(
        repos,
        source_ids=["source-1", "source-1", "source-2"],
        reason="news_fetch_run_finished",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 2
    assert repos.news_projection_dirty_targets.enqueued == [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-2", "window": "_refresh"},
    ]


def test_claim_helpers_filter_by_semantic_work_type() -> None:
    repos = FakeRepos()
    repos.news_projection_dirty_targets.claim_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""}
    ]

    claimed = claim_page_projection_work(
        repos,
        limit=10,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="worker",
        commit=False,
    )

    assert claimed[0]["target_id"] == "news-1"
    assert repos.news_projection_dirty_targets.claim_calls[0]["projection_name"] == "page"

    repos.news_projection_dirty_targets.claim_rows = []
    claim_item_brief_work(repos, limit=1, lease_ms=30_000, now_ms=NOW_MS, lease_owner="worker", commit=False)
    claim_source_quality_work(repos, limit=1, lease_ms=30_000, now_ms=NOW_MS, lease_owner="worker", commit=False)
    assert repos.news_projection_dirty_targets.claim_calls[1]["projection_name"] == "brief_input"
    assert repos.news_projection_dirty_targets.claim_calls[2]["projection_name"] == "source_quality"


def test_page_ids_and_source_quality_refresh_expansion() -> None:
    page_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
    ]
    source_rows = [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
    ]

    assert page_news_item_ids(page_rows) == ["news-1"]
    assert source_quality_windows_for_claimed(source_rows, configured_windows=("24h", "7d")) == [
        ("source-1", "24h"),
        ("source-1", "7d"),
    ]
