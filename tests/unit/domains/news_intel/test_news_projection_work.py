from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.news_intel.runtime.news_projection_work import (
    claim_item_brief_work,
    claim_page_projection_work,
    claim_source_quality_work,
    claim_story_brief_work,
    enqueue_item_brief_work,
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
    enqueue_source_quality_window_work,
    enqueue_story_brief_work,
    item_brief_news_item_ids,
    page_news_item_ids,
    queue_story_brief_depth,
    source_quality_claim_windows,
    story_brief_story_keys,
)

NOW_MS = 1_800_000


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.claim_rows: list[dict[str, object]] = []
        self.queue_depth_calls: list[dict[str, object]] = []

    def enqueue_targets(self, targets, *, reason, now_ms, due_at_ms=None, commit=True):
        rows = [dict(target) for target in targets]
        self.enqueued.extend(rows)
        self.reason = reason
        self.now_ms = now_ms
        self.due_at_ms = due_at_ms
        self.commit = commit
        return len(rows)

    def claim_due(self, **kwargs):
        self.claim_calls.append(dict(kwargs))
        return list(self.claim_rows)

    def queue_depth(self, **kwargs):
        self.queue_depth_calls.append(dict(kwargs))
        return 42


class FakeRepos:
    def __init__(self, *, servable_news_item_ids: list[str] | None = None) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()
        self.news = FakeNews(servable_news_item_ids=servable_news_item_ids)


class FakeReposWithoutServableFilter:
    def __init__(self) -> None:
        self.news_projection_dirty_targets = FakeDirtyTargets()
        self.news = object()


class FakeNews:
    def __init__(self, *, servable_news_item_ids: list[str] | None = None) -> None:
        self.servable_ids = servable_news_item_ids
        self.servable_calls: list[list[str]] = []

    def servable_news_item_ids(self, news_item_ids):
        ids = [str(news_item_id) for news_item_id in news_item_ids]
        self.servable_calls.append(ids)
        if self.servable_ids is None:
            return ids
        return [news_item_id for news_item_id in ids if news_item_id in set(self.servable_ids)]


def test_enqueue_page_reprojection_hides_page_projection_name() -> None:
    repos = FakeRepos()

    count = enqueue_page_reprojection(
        repos,
        news_item_ids=["news-1", "news-1", ""],
        reason="news_item_processed",
        now_ms=NOW_MS,
        source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 1_000},
        commit=False,
    )

    assert count == 1
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
        }
    ]


def test_enqueue_item_brief_work_sets_priority_by_item_id() -> None:
    repos = FakeRepos()

    count = enqueue_item_brief_work(
        repos,
        news_item_ids=["news-1", "news-2"],
        priority_by_news_item_id={"news-1": 7},
        source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 1_000, "news-2": NOW_MS - 2_000},
        reason="news_item_processed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 2
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
            "priority": 7,
        },
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
        },
    ]


def test_enqueue_story_brief_work_is_story_scoped_and_sets_priority() -> None:
    repos = FakeRepos(servable_news_item_ids=[])

    count = enqueue_story_brief_work(
        repos,
        story_keys=["story-1", "story-1", ""],
        priority_by_story_key={"story-1": 11},
        source_watermark_ms_by_story_key={"story-1": NOW_MS - 500},
        reason="story_identity_changed",
        now_ms=NOW_MS,
        commit=False,
    )

    assert count == 1
    assert repos.news.servable_calls == []
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-1",
            "source_watermark_ms": NOW_MS - 500,
            "priority": 11,
        }
    ]


@pytest.mark.parametrize("priority", [True, "7", 7.5, ""])
def test_enqueue_item_brief_work_rejects_malformed_priority_without_int_repair(priority: object) -> None:
    repos = FakeRepos()

    with pytest.raises(ValueError, match="news_projection_dirty_target_priority_required"):
        enqueue_item_brief_work(
            repos,
            news_item_ids=["news-1"],
            priority_by_news_item_id={"news-1": priority},  # type: ignore[dict-item]
            source_watermark_ms_by_news_item_id={"news-1": NOW_MS - 1_000},
            reason="news_item_processed",
            now_ms=NOW_MS,
            commit=False,
        )

    assert repos.news_projection_dirty_targets.enqueued == []


@pytest.mark.parametrize("priority", [True, "11", 11.5, ""])
def test_enqueue_story_brief_work_rejects_malformed_priority_without_int_repair(priority: object) -> None:
    repos = FakeRepos()

    with pytest.raises(ValueError, match="news_projection_dirty_target_priority_required"):
        enqueue_story_brief_work(
            repos,
            story_keys=["story-1"],
            priority_by_story_key={"story-1": priority},  # type: ignore[dict-item]
            source_watermark_ms_by_story_key={"story-1": NOW_MS - 500},
            reason="story_identity_changed",
            now_ms=NOW_MS,
            commit=False,
        )

    assert repos.news_projection_dirty_targets.enqueued == []


def test_enqueue_news_item_work_filters_non_servable_duplicate_ids() -> None:
    repos = FakeRepos(servable_news_item_ids=["news-survivor"])

    page_count = enqueue_page_reprojection(
        repos,
        news_item_ids=["news-survivor", "news-deleted"],
        reason="canonical_news_item_merge",
        now_ms=NOW_MS,
        source_watermark_ms_by_news_item_id={"news-survivor": NOW_MS - 1_000},
        commit=False,
    )
    brief_count = enqueue_item_brief_work(
        repos,
        news_item_ids=["news-survivor", "news-deleted"],
        reason="canonical_news_item_merge",
        now_ms=NOW_MS,
        source_watermark_ms_by_news_item_id={"news-survivor": NOW_MS - 1_000},
        commit=False,
    )

    assert page_count == 1
    assert brief_count == 1
    assert repos.news.servable_calls == [
        ["news-survivor", "news-deleted"],
        ["news-survivor", "news-deleted"],
    ]
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-survivor",
            "source_watermark_ms": NOW_MS - 1_000,
        },
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-survivor",
            "source_watermark_ms": NOW_MS - 1_000,
        },
    ]


def test_enqueue_news_item_work_requires_repository_servable_filter() -> None:
    repos = FakeReposWithoutServableFilter()

    try:
        enqueue_page_reprojection(
            repos,
            news_item_ids=["news-1"],
            reason="news_item_processed",
            now_ms=NOW_MS,
            commit=False,
        )
    except ValueError as exc:
        assert "servable_news_item_ids" in str(exc)
    else:  # pragma: no cover - assertion branch documents the expected failure mode.
        raise AssertionError("missing servable_news_item_ids repository contract must fail closed")

    assert repos.news_projection_dirty_targets.enqueued == []


def test_news_item_projection_work_requires_source_watermark_before_enqueue() -> None:
    repos = FakeRepos()

    for operation in (
        lambda: enqueue_page_reprojection(
            repos,
            news_item_ids=["news-1"],
            reason="news_item_processed",
            now_ms=NOW_MS,
            commit=False,
        ),
        lambda: enqueue_item_brief_work(
            repos,
            news_item_ids=["news-1"],
            reason="news_item_processed",
            now_ms=NOW_MS,
            commit=False,
        ),
    ):
        try:
            operation()
        except ValueError as exc:
            assert "news_projection_dirty_target_source_watermark_required" in str(exc)
        else:  # pragma: no cover - assertion branch documents the expected failure mode.
            raise AssertionError("news item projection dirty work must require source_watermark_ms")

    assert repos.news_projection_dirty_targets.enqueued == []


def test_story_brief_work_requires_source_watermark_before_enqueue() -> None:
    repos = FakeRepos()

    try:
        enqueue_story_brief_work(
            repos,
            story_keys=["story-1"],
            reason="story_identity_changed",
            now_ms=NOW_MS,
            commit=False,
        )
    except ValueError as exc:
        assert "news_projection_dirty_target_source_watermark_required" in str(exc)
    else:  # pragma: no cover - assertion branch documents the expected failure mode.
        raise AssertionError("story brief dirty work must require source_watermark_ms")

    assert repos.news_projection_dirty_targets.enqueued == []


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


@pytest.mark.parametrize("due_at_ms", [True, "1800000", 1_800_000.5, 0])
def test_source_quality_refresh_rejects_malformed_due_at_without_int_repair(due_at_ms: object) -> None:
    repos = FakeRepos()

    with pytest.raises(ValueError, match="news_projection_dirty_target_due_at_ms_required"):
        enqueue_source_quality_refresh(
            repos,
            source_ids=["source-1"],
            reason="news_fetch_run_finished",
            now_ms=NOW_MS,
            due_at_ms=due_at_ms,  # type: ignore[arg-type]
            commit=False,
        )

    assert repos.news_projection_dirty_targets.enqueued == []


@pytest.mark.parametrize("due_at_ms", [True, "1800000", 1_800_000.5, 0])
def test_source_quality_window_work_rejects_malformed_due_at_without_int_repair(due_at_ms: object) -> None:
    repos = FakeRepos()

    with pytest.raises(ValueError, match="news_projection_dirty_target_due_at_ms_required"):
        enqueue_source_quality_window_work(
            repos,
            source_windows=[("source-1", "24h")],
            source_watermark_ms_by_source_window={("source-1", "24h"): NOW_MS - 1_000},
            reason="source_quality_window_due",
            now_ms=NOW_MS,
            due_at_ms=due_at_ms,  # type: ignore[arg-type]
            commit=False,
        )

    assert repos.news_projection_dirty_targets.enqueued == []


def test_source_quality_window_work_requires_source_watermark_before_enqueue() -> None:
    repos = FakeRepos()

    try:
        enqueue_source_quality_window_work(
            repos,
            source_windows=[("source-1", "24h")],
            reason="source_quality_window_due",
            now_ms=NOW_MS,
            commit=False,
        )
    except ValueError as exc:
        assert "news_projection_dirty_target_source_watermark_required" in str(exc)
    else:  # pragma: no cover - assertion branch documents the expected failure mode.
        raise AssertionError("source_quality window dirty work must require source_watermark_ms")

    assert repos.news_projection_dirty_targets.enqueued == []


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
    claim_story_brief_work(repos, limit=1, lease_ms=30_000, now_ms=NOW_MS, lease_owner="worker", commit=False)
    assert repos.news_projection_dirty_targets.claim_calls[1]["projection_name"] == "brief_input"
    assert repos.news_projection_dirty_targets.claim_calls[2]["projection_name"] == "source_quality"
    assert repos.news_projection_dirty_targets.claim_calls[3]["projection_name"] == "story_brief"


def test_story_brief_queue_depth_uses_story_brief_projection_name() -> None:
    repos = FakeRepos()

    assert queue_story_brief_depth(repos, now_ms=NOW_MS) == 42
    assert repos.news_projection_dirty_targets.queue_depth_calls == [
        {"now_ms": NOW_MS, "projection_name": "story_brief"}
    ]


def test_page_ids_and_source_quality_refresh_expansion() -> None:
    page_rows = [
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""},
    ]
    source_rows = [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
    ]

    assert page_news_item_ids(page_rows) == ["news-1"]
    assert source_quality_claim_windows(source_rows, configured_windows=("24h", "7d")) == [
        ("source-1", "24h"),
        ("source-1", "7d"),
    ]


@pytest.mark.parametrize(
    ("helper", "row", "match"),
    [
        pytest.param(
            page_news_item_ids,
            {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
            "news_page_projection_claim_projection_name_required",
            id="page_projection",
        ),
        pytest.param(
            item_brief_news_item_ids,
            {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "", "window": ""},
            "news_item_brief_claim_target_id_required",
            id="item_target_id",
        ),
        pytest.param(
            story_brief_story_keys,
            {"projection_name": "story_brief", "target_kind": "story", "target_id": "story-1", "window": "24h"},
            "news_story_brief_claim_window_empty_required",
            id="story_window",
        ),
    ],
)
def test_claim_target_helpers_require_claim_contract_without_silent_filtering(
    helper: Callable[[list[dict[str, Any]]], list[str]],
    row: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        helper([row])


@pytest.mark.parametrize(
    ("row", "match"),
    [
        pytest.param(
            {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""},
            "news_source_quality_projection_claim_projection_name_required",
            id="projection",
        ),
        pytest.param(
            {"projection_name": "source_quality", "target_kind": "source", "target_id": "", "window": "24h"},
            "news_source_quality_projection_claim_target_id_required",
            id="target_id",
        ),
        pytest.param(
            {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": ""},
            "news_source_quality_projection_claim_window_required",
            id="window",
        ),
    ],
)
def test_source_quality_claim_windows_requires_claim_contract_without_silent_filtering(
    row: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        source_quality_claim_windows([row], configured_windows=("24h", "7d"))


def test_story_brief_story_keys_deduplicate_valid_claims() -> None:
    rows = [
        {"projection_name": "story_brief", "target_kind": "story", "target_id": "story-1", "window": ""},
        {"projection_name": "story_brief", "target_kind": "story", "target_id": "story-1", "window": ""},
    ]

    assert story_brief_story_keys(rows) == ["story-1"]
