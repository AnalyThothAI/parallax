from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts import regen_db_schema


class _ScalarResult:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[str]:
        return self.values


class _Connection:
    def __init__(self, versions: list[str]) -> None:
        self.versions = versions
        self.sql: list[str] = []

    def exec_driver_sql(self, sql: str, *_: Any, **__: Any) -> _ScalarResult:
        self.sql.append(sql)
        return _ScalarResult(self.versions)


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, *_: Any) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.disposed = False

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.connection)

    def dispose(self) -> None:
        self.disposed = True


class _Inspector:
    def __init__(self, table_names: list[str]) -> None:
        self.table_names = table_names

    def get_table_names(self, *, schema: str) -> list[str]:
        assert schema == "public"
        return self.table_names


def test_require_database_at_alembic_head_accepts_exact_single_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(regen_db_schema, "latest_migration_version", lambda: "20260722_0186")
    connection = _Connection(["20260722_0186"])

    regen_db_schema._require_database_at_alembic_head(connection)

    assert connection.sql == ["SELECT version_num FROM alembic_version ORDER BY version_num"]


@pytest.mark.parametrize(
    "versions, actual",
    [
        ([], "<missing>"),
        (["20260713_0183"], "20260713_0183"),
        (["20260713_0183", "20260722_0186"], "20260713_0183,20260722_0186"),
    ],
)
def test_require_database_at_alembic_head_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    versions: list[str],
    actual: str,
) -> None:
    monkeypatch.setattr(regen_db_schema, "latest_migration_version", lambda: "20260722_0186")

    with pytest.raises(
        RuntimeError,
        match=rf"db_schema_generation_requires_alembic_head: expected=20260722_0186 actual={actual}",
    ):
        regen_db_schema._require_database_at_alembic_head(_Connection(versions))


@pytest.mark.parametrize(
    "retired_table",
    [
        "cex_derivative_series",
        "market_tick_current_dirty_targets",
        "narrative_admissions",
        "news_story_agent_briefs",
        "projection_runs",
        "pulse_candidates",
        "token_capture_tier",
    ],
)
def test_same_revision_schema_drift_fails_closed_after_version_matches(
    monkeypatch: pytest.MonkeyPatch,
    retired_table: str,
) -> None:
    monkeypatch.setattr(regen_db_schema, "latest_migration_version", lambda: "20260722_0186")
    regen_db_schema._require_database_at_alembic_head(_Connection(["20260722_0186"]))

    with pytest.raises(
        RuntimeError,
        match=rf"db_schema_generation_requires_hard_cut_schema: retired_tables_present={retired_table}",
    ):
        regen_db_schema._require_retired_tables_absent(["events", retired_table])


def test_retired_table_guard_accepts_current_schema() -> None:
    regen_db_schema._require_retired_tables_absent(["alembic_version", "events", "token_radar_current_rows"])


def test_main_rejects_same_revision_schema_drift_before_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    connection = _Connection(["20260722_0186"])
    engine = _Engine(connection)
    output = tmp_path / "db-schema.md"
    monkeypatch.setenv(regen_db_schema.TEST_POSTGRES_DSN_ENV, "postgresql://test")
    monkeypatch.setattr(regen_db_schema, "latest_migration_version", lambda: "20260722_0186")
    monkeypatch.setattr(regen_db_schema, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(regen_db_schema, "inspect", lambda _connection: _Inspector(["events", "model_runs"]))
    monkeypatch.setattr(regen_db_schema, "OUTPUT", output)

    with pytest.raises(
        RuntimeError,
        match="db_schema_generation_requires_hard_cut_schema: retired_tables_present=model_runs",
    ):
        regen_db_schema.main()

    assert not output.exists()
    assert engine.disposed is True
