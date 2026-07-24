from __future__ import annotations

from datetime import date

import pytest
from alembic import command
from psycopg.errors import RaiseException

from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn
from tracefold.macro import MacroResearchRepository
from tracefold.platform.postgres.postgres_migrations import alembic_config

SESSION_DATE = date(2026, 7, 23)
PUBLISHED_DATE = date(2026, 7, 22)
NOW_MS = 500


def test_failed_research_retry_is_bounded_atomic_and_terminal_safe(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260724_0195")

        _insert_failed_run(conn, session_date=SESSION_DATE)
        _insert_published_run(conn, session_date=PUBLISHED_DATE)
        conn.commit()
        repository = MacroResearchRepository(conn)

        with conn.transaction():
            applied = repository.retry_failed_run(
                session_date=SESSION_DATE,
                now_ms=NOW_MS,
            )
        with conn.transaction():
            duplicate = repository.retry_failed_run(
                session_date=SESSION_DATE,
                now_ms=NOW_MS + 1,
            )
        with conn.transaction():
            published = repository.retry_failed_run(
                session_date=PUBLISHED_DATE,
                now_ms=NOW_MS,
            )
        with conn.transaction():
            missing = repository.retry_failed_run(
                session_date=date(2026, 7, 21),
                now_ms=NOW_MS,
            )

        assert applied["applied"] is True
        assert applied["previous_status"] == "failed"
        assert applied["status"] == "retryable"
        assert applied["attempt_count"] == 3
        assert applied["previous_max_attempts"] == 3
        assert applied["max_attempts"] == 4
        assert applied["due_at_ms"] == NOW_MS
        assert applied["lease_owner"] is None
        assert applied["last_error_code"] is None
        assert duplicate["applied"] is False
        assert duplicate["reason"] == "run_not_failed"
        assert duplicate["max_attempts"] == 4
        assert published["applied"] is False
        assert published["reason"] == "publication_exists"
        assert missing["applied"] is False
        assert missing["reason"] == "run_not_found"

        _insert_failed_run(conn, session_date=date(2026, 7, 20))
        conn.commit()
        with pytest.raises(RaiseException, match="operator_retry_shape_invalid"):
            conn.execute(
                """
                UPDATE macro_research_runs
                SET status = 'retryable',
                    max_attempts = max_attempts + 2,
                    due_at_ms = 600,
                    last_error_code = NULL,
                    last_error_message = NULL,
                    updated_at_ms = 600
                WHERE session_date = '2026-07-20'
                """
            )
        conn.rollback()
        with pytest.raises(RaiseException, match="macro_research_run_terminal"):
            conn.execute(
                """
                UPDATE macro_research_runs
                SET status = 'retryable',
                    due_at_ms = 700,
                    updated_at_ms = 700
                WHERE session_date = '2026-07-22'
                """
            )
        conn.rollback()
        with pytest.raises(RuntimeError, match="forward-only"):
            command.downgrade(config, "20260724_0194")
    finally:
        conn.close()


def _insert_failed_run(conn, *, session_date: date) -> None:
    conn.execute(
        """
        INSERT INTO macro_research_runs(
          session_date,
          market_cutoff_ms,
          status,
          sealed_at_ms,
          max_attempts,
          due_at_ms,
          created_at_ms,
          updated_at_ms
        )
        VALUES (%s, 100, 'pending', 110, 3, 110, 110, 110)
        """,
        (session_date,),
    )
    conn.execute(
        """
        UPDATE macro_research_runs
        SET status = 'running',
            attempt_count = 3,
            leased_until_ms = 200,
            lease_owner = 'integration-test',
            updated_at_ms = 120
        WHERE session_date = %s
        """,
        (session_date,),
    )
    conn.execute(
        """
        UPDATE macro_research_runs
        SET status = 'failed',
            leased_until_ms = NULL,
            lease_owner = NULL,
            last_error_code = 'provider_timeout',
            last_error_message = 'provider timed out',
            updated_at_ms = 130
        WHERE session_date = %s
        """,
        (session_date,),
    )


def _insert_published_run(conn, *, session_date: date) -> None:
    conn.execute(
        """
        INSERT INTO macro_research_runs(
          session_date,
          market_cutoff_ms,
          status,
          sealed_at_ms,
          max_attempts,
          due_at_ms,
          created_at_ms,
          updated_at_ms
        )
        VALUES (%s, 100, 'pending', 110, 3, 110, 110, 110)
        """,
        (session_date,),
    )
    conn.execute(
        """
        UPDATE macro_research_runs
        SET status = 'running',
            attempt_count = 1,
            leased_until_ms = 200,
            lease_owner = 'integration-test',
            updated_at_ms = 120
        WHERE session_date = %s
        """,
        (session_date,),
    )
    conn.execute(
        """
        INSERT INTO macro_research_publications(
          session_date,
          market_cutoff_ms,
          artifact_json,
          report_markdown,
          audit_json,
          model_name,
          prompt_version,
          workflow_version,
          artifact_hash,
          published_at_ms
        )
        VALUES (
          %s,
          100,
          '{}'::jsonb,
          '# 宏观研究',
          '{}'::jsonb,
          'fake-model',
          'prompt-v1',
          'workflow-v1',
          'sha256:artifact',
          130
        )
        """,
        (session_date,),
    )
    conn.execute(
        """
        UPDATE macro_research_runs
        SET status = 'published',
            leased_until_ms = NULL,
            lease_owner = NULL,
            updated_at_ms = 130
        WHERE session_date = %s
        """,
        (session_date,),
    )
