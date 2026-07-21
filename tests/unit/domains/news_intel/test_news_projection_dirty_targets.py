from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from parallax.domains.news_intel.repositories.news_projection_dirty_target_repository import (
    NewsProjectionDirtyTargetRepository,
)

NOW_MS = 1_779_000_000_000


class Cursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: int) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class Connection:
    def __init__(self, scripted_rows: list[list[dict[str, Any]]] | None = None, *, rowcount: int = 1) -> None:
        self.scripted_rows = list(scripted_rows or [])
        self.rowcount = rowcount
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield

    def execute(self, sql: str, params: Any = None) -> Cursor:
        self.sql.append(sql)
        self.params.append(params)
        rows = self.scripted_rows.pop(0) if self.scripted_rows else []
        return Cursor(rows, rowcount=self.rowcount if not rows else len(rows))


@pytest.mark.parametrize("projection_name", ["brief_input", "source_quality", "story"])
def test_retired_projection_names_are_rejected_before_sql(projection_name: str) -> None:
    conn = Connection()
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match=f"unsupported news projection_name: {projection_name}"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": projection_name,
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS,
                }
            ],
            reason="retired",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


@pytest.mark.parametrize(
    "target",
    [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS,
        },
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-1",
            "source_watermark_ms": NOW_MS,
        },
    ],
)
def test_page_and_story_targets_are_the_only_supported_shapes_without_implicit_transaction(
    target: dict[str, Any],
) -> None:
    conn = Connection(rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    assert repo.enqueue_targets([target], reason="changed", now_ms=NOW_MS) == 1
    assert conn.transaction_count == 0
    params = conn.params[-1]
    assert params["projection_names"] == [target["projection_name"]]
    assert params["target_kinds"] == [target["target_kind"]]
    assert params["windows"] == [""]
    assert params["source_watermark_ms_values"] == [NOW_MS]


@pytest.mark.parametrize(
    "target",
    [
        {
            "projection_name": "page",
            "target_kind": "story",
            "target_id": "story-1",
            "source_watermark_ms": NOW_MS,
        },
        {
            "projection_name": "story_brief",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS,
        },
    ],
)
def test_projection_target_kind_mismatch_is_rejected(target: dict[str, Any]) -> None:
    conn = Connection()
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="unsupported news projection target"):
        repo.enqueue_targets([target], reason="invalid", now_ms=NOW_MS)

    assert conn.sql == []


@pytest.mark.parametrize("source_watermark_ms", [None, 0, -1, True, "1"])
def test_projection_targets_require_positive_integer_watermarks(source_watermark_ms: object) -> None:
    conn = Connection()
    repo = NewsProjectionDirtyTargetRepository(conn)
    target = {
        "projection_name": "story_brief",
        "target_kind": "story",
        "target_id": "story-1",
        "source_watermark_ms": source_watermark_ms,
    }

    with pytest.raises(ValueError, match="news_projection_dirty_target_source_watermark_required"):
        repo.enqueue_targets([target], reason="invalid", now_ms=NOW_MS)

    assert conn.sql == []


def test_projection_targets_require_empty_window() -> None:
    conn = Connection()
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_window_empty_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "story_brief",
                    "target_kind": "story",
                    "target_id": "story-1",
                    "window": "24h",
                    "source_watermark_ms": NOW_MS,
                }
            ],
            reason="invalid",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


def test_claim_filters_by_story_projection() -> None:
    claim = {
        "projection_name": "story_brief",
        "target_kind": "story",
        "target_id": "story-1",
        "window": "",
        "payload_hash": "hash-1",
        "source_watermark_ms": NOW_MS,
        "lease_owner": "worker",
        "attempt_count": 0,
    }
    conn = Connection([[claim]], rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    rows = repo.claim_due(
        projection_name="story_brief",
        limit=1,
        lease_ms=30_000,
        now_ms=NOW_MS,
        lease_owner="worker",
    )

    assert rows == [claim]
    assert conn.params[-1]["projection_name"] == "story_brief"
