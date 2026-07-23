from __future__ import annotations

from parallax.domains.news_intel.repositories.news_source_repository import NewsSourceRepository


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
