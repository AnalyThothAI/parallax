from gmgn_twitter_intel.retrieval.harness_service import HarnessService
from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_signal_lab_chains_join_snapshots_by_persisted_lineage_ids(tmp_path):
    repo, conn = _repo(tmp_path)
    try:
        _social_event(repo, "extract-match", "event-match", received_at_ms=10_000)
        _seed(repo, "seed-match", "extract-match", "event-match", received_at_ms=10_000)
        _snapshot(
            repo,
            "snapshot-decoy",
            source_event_id="event-decoy",
            seed_id=None,
            asset="BNB",
            decision_time_ms=10_900,
        )
        _snapshot(
            repo,
            "snapshot-match",
            source_event_id="event-match",
            seed_id="seed-match",
            asset="BNB",
            decision_time_ms=10_100,
        )

        data = HarnessService(repo).chains(window="1h", horizon="6h", scope="all", limit=10, now_ms=11_000)
    finally:
        conn.close()

    chain = next(item for item in data["items"] if item["lineage"]["event_id"] == "event-match")
    assert chain["lineage"]["seed_id"] == "seed-match"
    assert chain["lineage"]["snapshot_id"] == "snapshot-match"
    assert chain["snapshot"]["snapshot_id"] == "snapshot-match"


def test_signal_lab_chains_derive_stage_summary_and_filters(tmp_path):
    repo, conn = _repo(tmp_path)
    try:
        _social_event(repo, "extract-only", "event-only", received_at_ms=10_000, is_signal_event=False)

        _social_event(repo, "extract-seeded", "event-seeded", received_at_ms=10_100)
        _seed(repo, "seed-seeded", "extract-seeded", "event-seeded", received_at_ms=10_100)

        _social_event(repo, "extract-frozen", "event-frozen", received_at_ms=10_200)
        _seed(repo, "seed-frozen", "extract-frozen", "event-frozen", received_at_ms=10_200)
        _snapshot(
            repo,
            "snapshot-frozen",
            source_event_id="event-frozen",
            seed_id="seed-frozen",
            decision_time_ms=10_220,
        )

        _social_event(repo, "extract-settled", "event-settled", received_at_ms=10_300)
        _seed(repo, "seed-settled", "extract-settled", "event-settled", received_at_ms=10_300)
        _snapshot(
            repo,
            "snapshot-settled",
            source_event_id="event-settled",
            seed_id="seed-settled",
            decision_time_ms=10_320,
        )
        _outcome(repo, "snapshot-settled")

        _social_event(repo, "extract-credited", "event-credited", received_at_ms=10_400)
        _seed(repo, "seed-credited", "extract-credited", "event-credited", received_at_ms=10_400)
        _snapshot(
            repo,
            "snapshot-credited",
            source_event_id="event-credited",
            seed_id="seed-credited",
            decision_time_ms=10_420,
        )
        _outcome(repo, "snapshot-credited")
        repo.record_credits(
            [
                {
                    "credit_id": "credit-credited",
                    "snapshot_id": "snapshot-credited",
                    "cluster_id": "cluster-credited",
                    "asset": "BNB",
                    "event_type": "meme_phrase_seed",
                    "source": "cz_binance",
                    "horizon": "6h",
                    "event_score": 0.42,
                    "responsibility": 1.0,
                    "credit": 0.5,
                }
            ]
        )

        data = HarnessService(repo).chains(window="1h", horizon="6h", scope="all", limit=10, now_ms=11_000)
        settled = HarnessService(repo).chains(
            window="1h",
            horizon="6h",
            scope="all",
            stage="settled",
            limit=10,
            now_ms=11_000,
        )
    finally:
        conn.close()

    assert data["summary"] == {
        "extracted": 1,
        "seeded": 1,
        "frozen": 1,
        "settled": 1,
        "credited": 1,
    }
    assert [item["stage"] for item in data["items"]] == ["credited", "settled", "frozen", "seeded", "extracted"]
    assert [item["chain_id"] for item in settled["items"]] == ["snapshot:snapshot-settled"]
    assert settled["returned_count"] == 1
    assert settled["has_more"] is False


def test_signal_lab_chains_cursor_paginates_visible_chains(tmp_path):
    repo, conn = _repo(tmp_path)
    try:
        for index in range(3):
            event_id = f"event-page-{index}"
            extraction_id = f"extract-page-{index}"
            seed_id = f"seed-page-{index}"
            snapshot_id = f"snapshot-page-{index}"
            received_at_ms = 10_000 + index
            _social_event(repo, extraction_id, event_id, received_at_ms=received_at_ms)
            _seed(repo, seed_id, extraction_id, event_id, received_at_ms=received_at_ms)
            _snapshot(
                repo,
                snapshot_id,
                source_event_id=event_id,
                seed_id=seed_id,
                asset=f"BNB{index}",
                decision_time_ms=received_at_ms + 20,
            )

        first_page = HarnessService(repo).chains(
            window="1h",
            horizon="6h",
            scope="all",
            limit=2,
            now_ms=11_000,
        )
        second_page = HarnessService(repo).chains(
            window="1h",
            horizon="6h",
            scope="all",
            limit=2,
            cursor=first_page["next_cursor"],
            now_ms=11_000,
        )
    finally:
        conn.close()

    assert first_page["has_more"] is True
    assert first_page["next_cursor"] == "2"
    assert [item["chain_id"] for item in first_page["items"]] == [
        "snapshot:snapshot-page-2",
        "snapshot:snapshot-page-1",
    ]
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None
    assert [item["chain_id"] for item in second_page["items"]] == ["snapshot:snapshot-page-0"]


def _repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    return HarnessRepository(conn), conn


def _social_event(
    repo: HarnessRepository,
    extraction_id: str,
    event_id: str,
    *,
    received_at_ms: int,
    author_handle: str = "cz_binance",
    is_signal_event: bool = True,
):
    return repo.upsert_social_event_extraction(
        extraction_id=extraction_id,
        event_id=event_id,
        run_id=None,
        author_handle=author_handle,
        received_at_ms=received_at_ms,
        schema_version="social-event-v2",
        model_version="test-model",
        event_type="meme_phrase_seed",
        source_action="posted",
        subject=f"{event_id} attention seed",
        direction_hint="attention_positive",
        attention_mechanism="meme_phrase",
        impact_hint=0.72,
        semantic_novelty_hint=0.68,
        confidence=0.86,
        is_signal_event=is_signal_event,
        anchor_terms=[{"term": "build on BNB", "role": "meme_phrase", "evidence": "build on BNB"}],
        token_candidates=[{"symbol": "BNB", "evidence": "BNB", "confidence": 0.8}],
        semantic_risks=["public_stream_coverage"],
        summary_zh=f"{event_id} summary",
        raw_response={"ok": True},
    )


def _seed(repo: HarnessRepository, seed_id: str, extraction_id: str, event_id: str, *, received_at_ms: int):
    return repo.upsert_attention_seed(
        seed_id=seed_id,
        extraction_id=extraction_id,
        event_id=event_id,
        author_handle="cz_binance",
        received_at_ms=received_at_ms,
        event_type="meme_phrase_seed",
        subject=f"{event_id} attention seed",
        anchor_terms=[{"term": "build on BNB", "role": "meme_phrase", "evidence": "build on BNB"}],
        token_uptake_count=2,
        top_linked_symbols=["BNB"],
        seed_status="snapshot_ready",
        risks=["public_stream_coverage"],
    )


def _snapshot(
    repo: HarnessRepository,
    snapshot_id: str,
    *,
    source_event_id: str,
    seed_id: str | None,
    asset: str = "BNB",
    decision_time_ms: int,
):
    return repo.create_snapshot(
        snapshot_id=snapshot_id,
        source_event_id=source_event_id,
        seed_id=seed_id,
        asset=asset,
        decision_time_ms=decision_time_ms,
        horizon="6h",
        combined_score=0.42,
        policy_signal="NO_TRADE",
        shadow_signal="LONG_SMALL",
        market_state={"pre_move": 0.0},
        event_clusters=[
            {
                "cluster_id": f"cluster-{snapshot_id}",
                "event_type": "meme_phrase_seed",
                "source": "cz_binance",
                "event_score": 0.42,
            }
        ],
        versions={
            "config_version": "social-mvp-v1",
            "prompt_version": "social-event-extractor-v2",
            "schema_version": "social-event-v2",
            "scoring_version": "harness-score-v1",
            "weight_version": "report-only-v1",
            "policy_version": "shadow-v1",
            "risk_version": "risk-v1",
            "baseline_version": "baseline-v1",
        },
        risks=["public_stream_coverage"],
    )


def _outcome(repo: HarnessRepository, snapshot_id: str):
    return repo.record_outcome(
        snapshot_id=snapshot_id,
        settled_at_ms=20_000,
        actual_return=0.02,
        expected_return=0.01,
        abnormal_return=0.01,
        realized_vol=0.02,
        normalized_outcome=0.5,
        baseline_version="baseline-v1",
    )
