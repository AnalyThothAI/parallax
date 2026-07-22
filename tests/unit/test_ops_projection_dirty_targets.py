from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from parallax.app.operations.news import enqueue_projection_dirty_targets
from parallax.app.operations.token_intel import token_profile_image_repair_targets, token_radar_publication_status
from parallax.app.surfaces.cli.parser import build_parser
from parallax.domains.news_intel._constants import NEWS_STORY_IDENTITY_VERSION

NOW_MS = 1_779_000_000_000


def test_enqueue_projection_dirty_targets_dry_run_reports_counts_without_writes() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        execute=False,
        now_ms=NOW_MS,
        projection="all",
    )

    assert result["execute"] is False
    assert result["news_item_ids"] == 3
    assert result["news_item_targets"] == 5
    assert repos.news_dirty.enqueued == []
    assert repos.conn.transactions == 0
    assert all("analysis_admission" not in sql for sql, _params in repos.conn.statements)


def test_enqueue_projection_dirty_targets_execute_enqueues_only_dirty_targets() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        execute=True,
        now_ms=NOW_MS,
        projection="all",
        since_ms=NOW_MS - 24 * 60 * 60 * 1000,
    )

    assert result["execute"] is True
    assert repos.conn.transactions == 1
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
        },
    ]
    assert repos.news_dirty.enqueued[1]["rows"] == [
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-sol",
            "source_watermark_ms": NOW_MS - 2_000,
            "priority": 10,
        },
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-eth",
            "source_watermark_ms": NOW_MS - 3_000,
            "priority": 55,
        },
    ]


def test_enqueue_projection_dirty_targets_execute_requires_transaction_before_reads_or_writes() -> None:
    repos = MissingTransactionRepos()

    with pytest.raises(AttributeError):
        enqueue_projection_dirty_targets(
            repos,
            execute=True,
            now_ms=NOW_MS,
            projection="page",
        )

    assert repos.conn.statements == []
    assert repos.news_dirty.enqueued == []


def test_enqueue_projection_dirty_targets_parser_requires_explicit_mode() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "enqueue-projection-dirty-targets",
            "--projection",
            "story_brief",
            "--since-hours",
            "24",
            "--dry-run",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "enqueue-projection-dirty-targets"
    assert args.projection == "story_brief"
    assert args.since_hours == 24
    assert args.dry_run is True
    assert args.execute is False


def test_enqueue_projection_dirty_targets_execute_requires_bounded_brief_repair() -> None:
    repos = FakeRepos()

    try:
        enqueue_projection_dirty_targets(
            repos,
            execute=True,
            now_ms=NOW_MS,
            projection="all",
        )
    except ValueError as exc:
        assert "--since-hours" in str(exc)
    else:
        raise AssertionError("expected unbounded story_brief repair to fail")


def test_enqueue_projection_dirty_targets_page_repair_can_run_unbounded_for_page_only_rows() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        execute=True,
        now_ms=NOW_MS,
        projection="page",
    )

    assert result["projection"] == "page"
    assert result["news_item_targets"] == 3
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
        },
    ]


def test_token_profile_image_repair_targets_require_current_row_watermark_without_runtime_fallback() -> None:
    conn = TokenProfileImageRepairConn(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "source_watermark_ms": None,
            }
        ]
    )

    with pytest.raises(ValueError, match="token_profile_image_repair_source_watermark_required"):
        token_profile_image_repair_targets(conn, limit=10)


def test_token_profile_image_repair_targets_use_observed_source_frontier_not_projection_update_time() -> None:
    conn = TokenProfileImageRepairConn(
        [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "source_watermark_ms": NOW_MS - 5_000,
            }
        ]
    )

    targets = token_profile_image_repair_targets(conn, limit=10)

    sql, params = conn.statements[0]
    assert "observed_at_ms AS source_watermark_ms" in sql
    assert params == (10,)
    assert targets == [
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "source_watermark_ms": NOW_MS - 5_000,
            "priority": 25,
        }
    ]


def test_token_radar_publication_status_reports_missing_without_run_or_offset_fallback() -> None:
    conn = TokenProfileImageRepairConn([])

    result = token_radar_publication_status(conn, projection_version="token-radar-v-test")

    sql, params = conn.statements[0]
    assert "FROM token_radar_publication_state" in sql
    assert "projection_runs" not in sql
    assert "projection_offsets" not in sql
    assert params == ("token-radar-v-test",)
    assert result == {
        "projection_version": "token-radar-v-test",
        "status": "missing",
        "state_count": 0,
        "ready_count": 0,
        "failed_count": 0,
        "publication_states": [],
    }


@pytest.mark.parametrize(
    ("rows", "expected_status"),
    [
        (
            [
                {
                    "latest_attempt_status": "ready",
                    "current_generation_id": "gen-1",
                }
            ],
            "ready",
        ),
        (
            [
                {
                    "latest_attempt_status": "ready",
                    "current_generation_id": "gen-1",
                },
                {
                    "latest_attempt_status": "failed",
                    "current_generation_id": "gen-2",
                },
            ],
            "degraded",
        ),
        (
            [
                {
                    "latest_attempt_status": "failed",
                    "current_generation_id": None,
                }
            ],
            "failed",
        ),
    ],
)
def test_token_radar_publication_status_derives_health_from_current_state_only(
    rows: list[dict[str, Any]],
    expected_status: str,
) -> None:
    result = token_radar_publication_status(
        TokenProfileImageRepairConn(rows),
        projection_version="token-radar-v-test",
    )

    assert result["status"] == expected_status
    assert result["state_count"] == len(rows)
    assert result["ready_count"] == sum(row["latest_attempt_status"] == "ready" for row in rows)
    assert result["failed_count"] == sum(row["latest_attempt_status"] == "failed" for row in rows)
    assert result["publication_states"] == rows


def test_token_radar_publication_status_rejects_unknown_publication_state() -> None:
    conn = TokenProfileImageRepairConn([{"latest_attempt_status": "running"}])

    with pytest.raises(ValueError, match="token_radar_publication_status_invalid"):
        token_radar_publication_status(conn, projection_version="token-radar-v-test")


def test_enqueue_projection_dirty_targets_can_scope_story_brief_repair() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        execute=True,
        now_ms=NOW_MS,
        projection="story_brief",
        since_ms=NOW_MS - 24 * 60 * 60 * 1000,
    )

    assert result["projection"] == "story_brief"
    assert result["news_item_targets"] == 2
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-sol",
            "source_watermark_ms": NOW_MS - 2_000,
            "priority": 10,
        },
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-eth",
            "source_watermark_ms": NOW_MS - 3_000,
            "priority": 55,
        },
    ]


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news_items = self
        self.news_dirty = FakeDirtyRepo()
        self.news_projection_dirty_targets = self.news_dirty

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]

    def transaction(self):
        return self.conn.transaction()


class MissingTransactionRepos:
    def __init__(self) -> None:
        self.conn = MissingTransactionConn()
        self.news_items = self
        self.news_dirty = FakeDirtyRepo()
        self.news_projection_dirty_targets = self.news_dirty

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeConn:
    def __init__(self) -> None:
        self.transactions = 0
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, _params: dict[str, Any] | None = None) -> FakeCursor:
        self.statements.append((sql, _params))
        if "FROM news_items" in sql:
            assert "items.agent_admission_json" in sql
            assert "items.story_key" in sql
            assert "items.lifecycle_status = 'processed'" in sql
            assert "items.story_key <> ''" in sql
            assert "items.story_identity_version = %(story_identity_version)s" in sql
            assert "items.agent_admission_status" not in sql
            assert "JOIN news_sources" not in sql
            assert "news_token_mentions" not in sql
            assert "news_fact_candidates" not in sql
            assert _params is not None
            assert _params["story_identity_version"] == NEWS_STORY_IDENTITY_VERSION
            return FakeCursor(
                [
                    {
                        "news_item_id": "news-1",
                        "story_key": "story-sol",
                        "published_at_ms": NOW_MS - 1_000,
                        "source_watermark_ms": NOW_MS - 1_000,
                        "agent_admission_json": {"status": "needs_review"},
                    },
                    {
                        "news_item_id": "news-2",
                        "story_key": "story-sol",
                        "published_at_ms": NOW_MS - 2_000,
                        "source_watermark_ms": NOW_MS - 2_000,
                        "agent_admission_json": {"status": "eligible_refresh"},
                    },
                    {
                        "news_item_id": "news-3",
                        "story_key": "story-eth",
                        "published_at_ms": NOW_MS - 3_000,
                        "source_watermark_ms": NOW_MS - 3_000,
                        "agent_admission_json": {"status": "eligible"},
                    },
                ]
            )
        if "FROM news_sources" in sql:
            return FakeCursor([{"source_id": "source-1"}, {"source_id": "source-2"}])
        raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transactions += 1
        yield


class MissingTransactionConn:
    transaction = None

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, _params: dict[str, Any] | None = None) -> FakeCursor:
        self.statements.append((sql, _params))
        raise AssertionError("execute repair must fail before SQL when transaction is missing")


class FakeCursor:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, str]]:
        return list(self.rows)


class TokenProfileImageRepairConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> TokenProfileImageRepairConn:
        self.statements.append((sql, params))
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


class FakeDirtyRepo:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(
        self,
        rows: list[dict[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
    ) -> int:
        del due_at_ms
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
            }
        )
        return len(rows)
