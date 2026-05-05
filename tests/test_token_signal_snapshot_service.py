from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.retrieval.token_signal_snapshot_service import TokenSignalSnapshotService
from gmgn_twitter_intel.storage.token_signal_repository import TokenSignalRepository
from tests.test_token_rolling_flow import open_runtime, token_event


def test_freeze_token_signal_writes_ranked_snapshot_with_versions_and_health(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index, handle in enumerate(["seed", "amp1", "amp2"]):
            ingest.ingest_event(
                token_event(
                    f"event-dog-freeze-{index}",
                    received_at_ms=now_ms - (index + 1) * 10_000,
                    author_handle=handle,
                    text=f"$DOG freeze {index}",
                ),
                is_watched=index == 0,
            )
        service = TokenSignalSnapshotService(
            token_flow=TokenFlowService(signals=signals, tokens=tokens),
            repository=TokenSignalRepository(conn),
        )

        result = service.freeze(window="5m", scope="all", limit=10, now_ms=now_ms)
        snapshots = TokenSignalRepository(conn).list_snapshots(window="5m", scope="all", limit=10)
    finally:
        conn.close()

    assert result["snapshots_written"] == 1
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["score_versions"]["opportunity"] == "social_opportunity_v2"
    assert snapshot["component_payload"]["opportunity"]["score_version"] == "social_opportunity_v2"
    assert snapshot["timeline"]["summary"]["new_authors_total"] == 3
    assert sorted(snapshot["source_event_ids"]) == [
        "event-dog-freeze-0",
        "event-dog-freeze-1",
        "event-dog-freeze-2",
    ]
    assert snapshot["market_snapshot_ids"]
    assert snapshot["data_health"]["market"] == "fresh"


def test_freeze_token_signal_is_idempotent_for_same_decision_time(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-freeze-idempotent", received_at_ms=now_ms - 10_000),
            is_watched=True,
        )
        service = TokenSignalSnapshotService(
            token_flow=TokenFlowService(signals=signals, tokens=tokens),
            repository=TokenSignalRepository(conn),
        )

        first = service.freeze(window="5m", scope="all", limit=10, now_ms=now_ms)
        second = service.freeze(window="5m", scope="all", limit=10, now_ms=now_ms)
        snapshots = TokenSignalRepository(conn).list_snapshots(window="5m", scope="all", limit=10)
    finally:
        conn.close()

    assert first["snapshots_written"] == 1
    assert second["snapshots_written"] == 1
    assert len(snapshots) == 1


def test_freeze_token_signal_does_not_require_or_call_llm(tmp_path, monkeypatch):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-freeze-no-llm", received_at_ms=now_ms - 10_000),
            is_watched=True,
        )

        def fail_if_called(*args, **kwargs):
            raise AssertionError("freeze must not call LLM prompt builder")

        monkeypatch.setattr(
            "gmgn_twitter_intel.pipeline.social_event_extraction.build_social_event_prompt",
            fail_if_called,
        )
        result = TokenSignalSnapshotService(
            token_flow=TokenFlowService(signals=signals, tokens=tokens),
            repository=TokenSignalRepository(conn),
        ).freeze(window="5m", scope="all", limit=10, now_ms=now_ms)
    finally:
        conn.close()

    assert result["snapshots_written"] == 1
