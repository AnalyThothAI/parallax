from __future__ import annotations

from parallax.domains.news_intel.repositories.news_source_repository import NewsSourceRepository
from parallax.domains.news_intel.repositories.news_story_agent_repository import NewsStoryAgentRepository


class _Cursor:
    def __init__(self, rowcount: object) -> None:
        self.rowcount = rowcount


class _Connection:
    def __init__(self, *, rowcount: object = 0) -> None:
        self.rowcount = rowcount
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> _Cursor:
        self.statements.append((sql, params))
        return _Cursor(self.rowcount)


def test_successful_fetch_run_retention_is_bounded_and_preserves_other_statuses() -> None:
    conn = _Connection(rowcount=5)

    deleted = NewsSourceRepository(conn).prune_successful_fetch_runs(cutoff_ms=1_000, limit=5)

    assert deleted == 5
    sql, params = conn.statements[0]
    assert "status = 'success'" in sql
    assert "finished_at_ms < %s" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "DELETE FROM news_fetch_runs" in sql
    assert params == (1_000, 5)


def test_story_run_retention_is_bounded_and_protects_current_briefs() -> None:
    conn = _Connection(rowcount=4)

    deleted = NewsStoryAgentRepository(conn).prune_unreferenced_story_agent_runs(cutoff_ms=2_000, limit=4)

    assert deleted == 4
    sql, params = conn.statements[0]
    assert "runs.finished_at_ms < %s" in sql
    assert "FROM news_story_agent_briefs AS briefs" in sql
    assert "briefs.agent_run_id = runs.run_id" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "DELETE FROM news_story_agent_runs" in sql
    assert params == (2_000, 4)
