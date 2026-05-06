from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.token_signal_repository import TokenSignalRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def open_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    EvidenceRepository(conn).insert_event(make_event("event-1"), is_watched=True)
    return conn, TokenSignalRepository(conn)


def snapshot_payload(**overrides):
    payload = {
        "snapshot_id": "snapshot-1",
        "token_id": "token:eth:0x1111111111111111111111111111111111111111",
        "identity_key": "token:eth:0x1111111111111111111111111111111111111111",
        "chain": "eth",
        "address": "0x1111111111111111111111111111111111111111",
        "symbol": "DOG",
        "window": "5m",
        "scope": "all",
        "decision_time_ms": 1_700_000_000_000,
        "rank": 1,
        "decision": "watch",
        "opportunity_score": 67,
        "score_versions": {
            "heat": "social_heat_v2",
            "opportunity": "social_opportunity_v2",
        },
        "component_payload": {
            "social_heat": {"score": 70, "score_version": "social_heat_v2"},
            "opportunity": {"score": 67, "score_version": "social_opportunity_v2"},
        },
        "identity": {"token_id": "token:eth:0x1111111111111111111111111111111111111111"},
        "market": {"snapshot_id": "market-1", "price": 1.0},
        "flow": {"mentions": 3},
        "timeline": {"buckets": [{"mentions": 2}], "summary": {"new_authors_total": 2}},
        "source_event_ids": ["event-1"],
        "market_snapshot_ids": ["market-1"],
        "data_health": {"market": "fresh"},
        "risks": ["public_stream_coverage"],
    }
    payload.update(overrides)
    return payload


def test_token_signal_snapshot_round_trips_json_payloads(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        created = repo.create_snapshot(**snapshot_payload())
        fetched = repo.snapshot_by_id("snapshot-1")
    finally:
        conn.close()

    assert created["component_payload"]["social_heat"]["score"] == 70
    assert fetched["score_versions"]["opportunity"] == "social_opportunity_v2"
    assert fetched["timeline"]["buckets"] == [{"mentions": 2}]
    assert fetched["source_event_ids"] == ["event-1"]
    assert fetched["market_snapshot_ids"] == ["market-1"]
    assert fetched["risks"] == ["public_stream_coverage"]


def test_token_signal_snapshot_upsert_is_idempotent_for_decision_key(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        repo.create_snapshot(**snapshot_payload(snapshot_id="snapshot-1", opportunity_score=67))
        repo.create_snapshot(**snapshot_payload(snapshot_id="snapshot-2", opportunity_score=71))
        rows = repo.list_snapshots(window="5m", scope="all", limit=10)
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0]["snapshot_id"] == "snapshot-2"
    assert rows[0]["opportunity_score"] == 71


def test_token_signal_outcome_and_evaluation_round_trip(tmp_path):
    conn, repo = open_repo(tmp_path)
    try:
        repo.create_snapshot(**snapshot_payload())
        outcome = repo.record_outcome(
            outcome_id="outcome-1",
            snapshot_id="snapshot-1",
            horizon="6h",
            status="settled",
            entry_snapshot_id="market-entry",
            exit_snapshot_id="market-exit",
            benchmark_snapshot_ids=["bench-entry", "bench-exit"],
            entry_price=1.0,
            exit_price=1.04,
            benchmark_return=0.01,
            actual_return=0.04,
            abnormal_return=0.03,
            realized_vol=0.08,
            normalized_outcome=0.375,
            market_coverage_status="ready",
            settled_at_ms=1_700_021_600_000,
        )
        evaluation = repo.upsert_evaluation(
            evaluation_id="eval-1",
            horizon="6h",
            window="5m",
            scope="all",
            score_version="social_opportunity_v2",
            bucket_label="55-69",
            bucket_min=55,
            bucket_max=69,
            snapshot_count=1,
            settled_count=1,
            settlement_coverage=1.0,
            avg_actual_return=0.04,
            avg_abnormal_return=0.03,
            avg_normalized_outcome=0.375,
            directional_hit_rate=1.0,
            wilson_low=0.2,
            wilson_high=1.0,
            generated_at_ms=1_700_030_000_000,
        )
    finally:
        conn.close()

    assert outcome["benchmark_snapshot_ids"] == ["bench-entry", "bench-exit"]
    assert outcome["normalized_outcome"] == 0.375
    assert evaluation["bucket_label"] == "55-69"
    assert evaluation["settlement_coverage"] == 1.0
