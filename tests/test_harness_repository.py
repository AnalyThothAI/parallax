from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_harness_repository_persists_closed_loop_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        repo = HarnessRepository(conn)
        extraction = repo.upsert_social_event_extraction(
            extraction_id="extract-1",
            event_id="event-1",
            run_id=None,
            author_handle="cz_binance",
            received_at_ms=1_000,
            schema_version="social-event-v2",
            model_version="test-model",
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="BNB attention seed",
            direction_hint="attention_positive",
            attention_mechanism="meme_phrase",
            impact_hint=0.72,
            semantic_novelty_hint=0.68,
            confidence=0.86,
            is_signal_event=True,
            anchor_terms=[{"term": "build on BNB", "role": "meme_phrase", "evidence": "build on BNB"}],
            token_candidates=[{"symbol": "BNB", "evidence": "BNB", "confidence": 0.8}],
            semantic_risks=["public_stream_coverage"],
            summary_zh="CZ 提到 build on BNB。",
            raw_response={"ok": True},
        )
        seed = repo.upsert_attention_seed(
            seed_id="seed-1",
            extraction_id=extraction["extraction_id"],
            event_id="event-1",
            author_handle="cz_binance",
            received_at_ms=1_000,
            event_type="meme_phrase_seed",
            subject="BNB attention seed",
            anchor_terms=extraction["anchor_terms"],
            token_uptake_count=2,
            top_linked_symbols=["BNB"],
            seed_status="snapshot_ready",
            risks=["public_stream_coverage"],
        )
        repo.upsert_event_cluster(
            cluster_id="cluster-1",
            seed_id=seed["seed_id"],
            extraction_id=extraction["extraction_id"],
            event_id="event-1",
            asset="BNB",
            event_type="meme_phrase_seed",
            source="cz_binance",
            first_seen_at_ms=1_000,
            last_seen_at_ms=1_000,
            direction=1,
            impact=0.72,
            confidence=0.86,
            novelty=0.68,
            pricedness=0.2,
            base_score=0.34,
            event_score=0.31,
            source_list=["cz_binance"],
            raw_event_ids=["event-1"],
            representative_text="build on BNB",
            risks=["public_stream_coverage"],
        )
        snapshot = repo.create_snapshot(
            snapshot_id="snapshot-1",
            source_event_id="event-1",
            seed_id=seed["seed_id"],
            asset="BNB",
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.31,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"pre_move": 0.0},
            event_clusters=[
                {
                    "cluster_id": "cluster-1",
                    "event_type": "meme_phrase_seed",
                    "source": "cz_binance",
                    "event_score": 0.31,
                }
            ],
            versions={"config_version": "social-harness-mvp-v1", "prompt_version": "social-event-extractor-v2"},
            risks=["public_stream_coverage"],
        )
        repo.record_decision(
            decision_id="decision-1",
            snapshot_id=snapshot["snapshot_id"],
            asset="BNB",
            decision_time_ms=1_000,
            execution_mode="shadow",
            signal="LONG_SMALL",
            side="LONG",
            size=0.0,
            entry_price=None,
            risk_reject_reason=None,
            config_version="social-mvp-v1",
        )
        repo.record_outcome(
            snapshot_id=snapshot["snapshot_id"],
            settled_at_ms=2_000,
            actual_return=0.02,
            expected_return=0.01,
            abnormal_return=0.01,
            realized_vol=0.02,
            normalized_outcome=0.5,
            baseline_version="benchmark-zero-v1",
        )
        repo.record_credits(
            [
                {
                    "credit_id": "credit-1",
                    "snapshot_id": snapshot["snapshot_id"],
                    "cluster_id": "cluster-1",
                    "asset": "BNB",
                    "event_type": "meme_phrase_seed",
                    "source": "cz_binance",
                    "horizon": "6h",
                    "event_score": 0.31,
                    "responsibility": 1.0,
                    "credit": 0.5,
                }
            ]
        )
        repo.upsert_weight(
            key="event_type:meme_phrase_seed:6h",
            weight_type="event_type",
            asset=None,
            horizon="6h",
            n=1,
            mean_credit=0.5,
            weight=1.0049,
            status="report_only",
        )
    finally:
        conn.close()

    read_conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=True)
    try:
        read_repo = HarnessRepository(read_conn)
        social_events = read_repo.list_social_events(window_ms=10_000, now_ms=2_000, limit=5)
        seeds = read_repo.list_attention_seeds(window_ms=10_000, now_ms=2_000, limit=5)
        snapshots = read_repo.list_snapshots(window_ms=10_000, now_ms=2_000, horizon="6h", limit=5)
        outcomes = read_repo.list_outcomes(window_ms=10_000, now_ms=2_000, horizon="6h", limit=5)
        assert social_events[0]["anchor_terms"][0]["term"] == "build on BNB"
        assert seeds[0]["top_linked_symbols"] == ["BNB"]
        assert snapshots[0]["outcome_status"] == "settled"
        assert outcomes[0]["normalized_outcome"] == 0.5
        assert read_repo.list_credits(window_ms=10_000, now_ms=2_000, horizon="6h", limit=5)[0]["credit"] == 0.5
        assert read_repo.list_weights(horizon="6h", limit=5)[0]["status"] == "report_only"
    finally:
        read_conn.close()
