from __future__ import annotations

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_dirty_target_identity_is_stable_and_newer_watermark_wins(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        with repos.transaction():
            first = repos.news_projection_dirty_targets.enqueue_targets(
                [
                    {
                        "projection_name": "page",
                        "target_kind": "news_item",
                        "target_id": "news-1",
                        "source_watermark_ms": NOW_MS,
                        "priority": 20,
                    }
                ],
                reason="news_item_processed",
                now_ms=NOW_MS,
            )
            second = repos.news_projection_dirty_targets.enqueue_targets(
                [
                    {
                        "projection_name": "page",
                        "target_kind": "news_item",
                        "target_id": "news-1",
                        "source_watermark_ms": NOW_MS + 100,
                        "priority": 10,
                    }
                ],
                reason="news_story_changed",
                now_ms=NOW_MS + 100,
            )
        rows = conn.execute(
            """
            SELECT projection_name, target_kind, target_id, "window", source_watermark_ms, priority
              FROM news_projection_dirty_targets
            """
        ).fetchall()
    finally:
        conn.close()

    assert first == 1
    assert second == 1
    assert [dict(row) for row in rows] == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "window": "",
            "source_watermark_ms": NOW_MS + 100,
            "priority": 10,
        }
    ]


@pytest.mark.parametrize("projection_name", ["brief_input", "source_quality", "story", "story_brief"])
def test_retired_projection_names_are_rejected(tmp_path, projection_name: str) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        with pytest.raises(ValueError, match="unsupported news projection_name"):
            repos.news_projection_dirty_targets.enqueue_targets(
                [
                    {
                        "projection_name": projection_name,
                        "target_kind": "news_item",
                        "target_id": "news-1",
                        "source_watermark_ms": NOW_MS,
                    }
                ],
                reason="retired_lane",
                now_ms=NOW_MS,
            )
    finally:
        conn.close()


def _repositories(conn):
    return repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
