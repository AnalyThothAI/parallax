from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.news_intel._constants import NEWS_ITEM_BRIEF_SCHEMA_VERSION
from parallax.domains.news_intel.services.news_item_brief_schema_hard_cut import (
    cleanup_news_item_brief_schema_hard_cut,
)

NOW_MS = 1_779_000_000_000


def test_cleanup_news_item_brief_schema_hard_cut_dry_run_only_lists_candidates() -> None:
    repos = _Repos(stale_ids=["news-1", "news-2"])

    result = cleanup_news_item_brief_schema_hard_cut(repos, execute=False, now_ms=NOW_MS)

    assert result == {
        "execute": False,
        "required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        "candidate_count": 2,
        "cleared_count": 0,
        "page_targets_enqueued": 0,
        "brief_input_targets_enqueued": 0,
        "news_item_ids": ["news-1", "news-2"],
    }
    assert repos.news.calls == [
        ("list", {"required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION, "limit": 5000})
    ]
    assert repos.news_projection_dirty_targets.enqueued == []
    assert repos.conn.commits == 0


def test_cleanup_news_item_brief_schema_hard_cut_clears_and_requeues_page_and_brief_input() -> None:
    repos = _Repos(stale_ids=["news-1", "news-2"])

    result = cleanup_news_item_brief_schema_hard_cut(repos, execute=True, now_ms=NOW_MS)

    assert result["execute"] is True
    assert result["candidate_count"] == 2
    assert result["cleared_count"] == 2
    assert result["page_targets_enqueued"] == 2
    assert result["brief_input_targets_enqueued"] == 2
    assert repos.news.calls == [
        ("list", {"required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION, "limit": 5000}),
        (
            "clear",
            {
                "required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
                "news_item_ids": ["news-1", "news-2"],
                "commit": False,
            },
        ),
    ]
    assert repos.news_projection_dirty_targets.enqueued == [
        {
            "rows": [
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1", "window": ""},
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-2", "window": ""},
            ],
            "reason": "news_item_brief_schema_hard_cut",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-1", "window": ""},
                {"projection_name": "brief_input", "target_kind": "news_item", "target_id": "news-2", "window": ""},
            ],
            "reason": "news_item_brief_schema_hard_cut",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert repos.conn.commits == 1


class _Repos(SimpleNamespace):
    def __init__(self, *, stale_ids: list[str]) -> None:
        super().__init__(
            news=_NewsRepo(stale_ids),
            news_projection_dirty_targets=_DirtyTargets(),
            conn=_Conn(),
        )


class _NewsRepo:
    def __init__(self, stale_ids: list[str]) -> None:
        self.stale_ids = stale_ids
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_current_brief_ids_outside_schema(self, **kwargs: object) -> list[str]:
        self.calls.append(("list", dict(kwargs)))
        return list(self.stale_ids)

    def clear_current_briefs_outside_schema(self, **kwargs: object) -> list[str]:
        self.calls.append(("clear", dict(kwargs)))
        return list(kwargs.get("news_item_ids") or self.stale_ids)


class _DirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_targets(self, rows: list[dict[str, object]], **kwargs: object) -> int:
        self.enqueued.append({"rows": rows, **dict(kwargs)})
        return len(rows)


class _Conn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
