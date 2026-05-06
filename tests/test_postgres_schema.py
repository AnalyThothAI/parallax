from __future__ import annotations

from pathlib import Path

MIGRATION = Path("src/gmgn_twitter_intel/storage/alembic/versions/20260506_0001_initial_postgresql.py")
QUEUE_MIGRATION = Path("src/gmgn_twitter_intel/storage/alembic/versions/20260506_0002_postgres_queue_claims.py")
STALE_RUNNING_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260506_0003_enrichment_stale_running_claims.py"
)


def test_initial_postgres_schema_uses_jsonb_boolean_and_tsvector() -> None:
    text = MIGRATION.read_text()

    assert "JSONB" in text
    assert "BOOLEAN" in text
    assert "tsvector" in text
    assert "USING GIN" in text


def test_initial_postgres_schema_has_no_sqlite_pragmas_or_fts5() -> None:
    text = MIGRATION.read_text().lower()

    assert "pragma" not in text
    assert "fts5" not in text
    assert "virtual table" not in text


def test_queue_claim_migration_indexes_postgres_worker_paths() -> None:
    text = QUEUE_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "idx_token_market_observations_claim_ready" in text
    assert "idx_token_market_observations_claim_stale" in text
    assert "idx_notification_deliveries_claim" in text
    assert "WHERE status IN ('pending', 'failed')" in text


def test_enrichment_stale_running_migration_indexes_postgres_recovery_path() -> None:
    text = STALE_RUNNING_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "WHERE status IN ('pending', 'failed', 'running')" in text
