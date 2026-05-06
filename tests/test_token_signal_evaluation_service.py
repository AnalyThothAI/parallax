import pytest

from gmgn_twitter_intel.retrieval.token_signal_evaluation_service import TokenSignalEvaluationService
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.token_signal_repository import TokenSignalRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_sqlite_repositories import make_event
from tests.test_token_signal_repository import snapshot_payload


def test_token_signal_evaluation_excludes_pending_from_hit_rate_denominator(tmp_path):
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(make_event("event-1"), is_watched=True)
        repo = TokenSignalRepository(conn)
        repo.create_snapshot(**snapshot_payload(snapshot_id="snapshot-settled", opportunity_score=62))
        repo.create_snapshot(
            **snapshot_payload(
                snapshot_id="snapshot-pending",
                decision_time_ms=1_700_000_010_000,
                opportunity_score=64,
            )
        )
        repo.record_outcome(
            outcome_id="outcome-settled",
            snapshot_id="snapshot-settled",
            horizon="6h",
            status="settled",
            entry_snapshot_id="entry",
            exit_snapshot_id="exit",
            benchmark_snapshot_ids=[],
            entry_price=1.0,
            exit_price=1.03,
            benchmark_return=0.0,
            actual_return=0.03,
            abnormal_return=0.03,
            realized_vol=0.06,
            normalized_outcome=0.5,
            market_coverage_status="ready",
            settled_at_ms=1_700_021_600_000,
        )

        report = TokenSignalEvaluationService(repository=repo).evaluate(horizon="6h", window="5m", scope="all")
        bucket = next(item for item in report["buckets"] if item["bucket_label"] == "55-69")
        stored = repo.list_evaluations(horizon="6h", window="5m", scope="all")
    finally:
        conn.close()

    assert bucket["snapshot_count"] == 2
    assert bucket["settled_count"] == 1
    assert bucket["settlement_coverage"] == pytest.approx(0.5)
    assert bucket["directional_hit_rate"] == pytest.approx(1.0)
    assert 0.0 <= bucket["wilson_low"] <= bucket["wilson_high"] <= 1.0
    assert stored
