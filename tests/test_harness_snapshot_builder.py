from gmgn_twitter_intel.domains.asset_market.repositories.asset_repository import AssetRepository
from gmgn_twitter_intel.domains.closed_loop_harness.repositories.harness_repository import HarnessRepository
from gmgn_twitter_intel.domains.closed_loop_harness.services.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.social_enrichment.types.social_event_extraction import (
    AnchorTerm,
    SocialEventExtraction,
    SocialTokenCandidate,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_api_http import make_token_event

BNB = "0x0000000000000000000000000000000000000b0b"


def test_snapshot_builder_materializes_seed_cluster_snapshot_and_shadow_decision(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        evidence = EvidenceRepository(conn)
        assets = AssetRepository(conn)
        event = make_token_event(
            "event-1",
            symbol="BNB",
            address=BNB,
            text=f"CZ says build on BNB {BNB}",
            received_at_ms=1_000,
        )
        evidence.insert_event(event, is_watched=True)
        asset_id = _upsert_asset_with_price(
            assets,
            symbol="BNB",
            address=BNB,
            observed_at_ms=1_000,
            price=1.0,
        )
        extraction = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="BNB attention seed",
            direction_hint="attention_positive",
            attention_mechanism="meme_phrase",
            impact_hint=0.72,
            semantic_novelty_hint=0.68,
            confidence=0.86,
            anchor_terms=[AnchorTerm(term="build on BNB", role="meme_phrase", evidence="build on BNB")],
            token_candidates=[
                SocialTokenCandidate(
                    symbol="BNB",
                    project_name=None,
                    chain="eth",
                    address=BNB,
                    evidence="BNB",
                    confidence=0.8,
                )
            ],
            semantic_risks=["public_stream_coverage"],
            summary_zh="CZ 提到 build on BNB。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness, assets=assets).materialize(
            event=event.to_dict(),
            extraction=extraction,
            run_id="run-1",
            model_version="gpt-test",
        )
        duplicate = HarnessSnapshotBuilder(harness, assets=assets).materialize(
            event=event.to_dict(),
            extraction=extraction,
            run_id="run-1",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["social_event"]["event_type"] == "meme_phrase_seed"
    assert materialized["seed"]["seed_status"] == "snapshot_ready"
    assert [snapshot["horizon"] for snapshot in materialized["snapshots"]] == ["6h", "24h"]
    assert materialized["snapshots"][0]["asset"] == asset_id
    assert materialized["clusters"][0]["pricedness"] != 0.35
    assert materialized["decisions"][0]["execution_mode"] == "shadow"
    assert materialized["decisions"][0]["signal"] == "LONG_SMALL"
    assert duplicate["snapshots"][0]["snapshot_id"] == materialized["snapshots"][0]["snapshot_id"]
    read_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=True)
    try:
        snapshots = HarnessRepository(read_conn).list_snapshots(
            window_ms=10_000,
            now_ms=2_000,
            horizon=None,
            limit=10,
        )
    finally:
        read_conn.close()
    assert len(snapshots) == 2


def test_snapshot_builder_stores_non_signal_without_snapshot(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        extraction = SocialEventExtraction(
            is_signal_event=False,
            event_type="founder_reply",
            source_action="replied",
            subject="casual reply",
            direction_hint="neutral",
            attention_mechanism="reply_target",
            impact_hint=0.2,
            semantic_novelty_hint=0.1,
            confidence=0.8,
            anchor_terms=[AnchorTerm(term="gm", role="meme_phrase", evidence="gm")],
            token_candidates=[],
            semantic_risks=["low_information"],
            summary_zh="普通回复。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness).materialize(
            event={"event_id": "event-2", "author_handle": "heyi", "received_at_ms": 2_000, "search_text": "gm"},
            extraction=extraction,
            run_id="run-2",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["social_event"]["is_signal_event"] is False
    assert materialized["seed"] is None
    assert materialized["snapshots"] == []
    assert materialized["decisions"] == []


def test_snapshot_builder_keeps_seed_only_attention_unfrozen_until_asset_resolves(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        extraction = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="Grok meme attention",
            direction_hint="attention_positive",
            attention_mechanism="meme_phrase",
            impact_hint=0.7,
            semantic_novelty_hint=0.8,
            confidence=0.9,
            anchor_terms=[AnchorTerm(term="Grok", role="meme_phrase", evidence="Grok")],
            token_candidates=[],
            semantic_risks=["unresolved_symbol"],
            summary_zh="Musk 提到 Grok，形成 seed-only 信号。",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness).materialize(
            event={
                "event_id": "event-grok",
                "author_handle": "elonmusk",
                "received_at_ms": 3_000,
                "search_text": "Grok",
            },
            extraction=extraction,
            run_id="run-grok",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["seed"]["seed_status"] == "asset_unresolved"
    assert materialized["seed"]["token_uptake_count"] == 0
    assert materialized["seed"]["top_linked_symbols"] == []
    assert materialized["snapshots"] == []
    assert materialized["decisions"] == []
    assert "unresolved_symbol" in materialized["seed"]["risks"]


def test_snapshot_builder_requires_entry_market_before_freezing_resolved_asset(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        evidence = EvidenceRepository(conn)
        assets = AssetRepository(conn)
        event = make_token_event(
            "event-no-entry",
            symbol="BNB",
            address=BNB,
            text=f"BNB attention {BNB}",
            received_at_ms=5_000,
        )
        evidence.insert_event(event, is_watched=True)
        assets.upsert_dex_asset(
            chain="ethereum",
            address=BNB,
            symbol="BNB",
            observed_at_ms=event.received_at_ms,
            event_id=event.event_id,
            provider="test",
        )
        extraction = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="BNB attention",
            direction_hint="attention_positive",
            attention_mechanism="direct_token_mention",
            impact_hint=0.7,
            semantic_novelty_hint=0.8,
            confidence=0.9,
            anchor_terms=[AnchorTerm(term="BNB", role="asset", evidence="BNB")],
            token_candidates=[
                SocialTokenCandidate(
                    symbol="BNB",
                    project_name=None,
                    chain="eth",
                    address=BNB,
                    evidence=BNB,
                    confidence=0.9,
                )
            ],
            semantic_risks=[],
            summary_zh="BNB attention.",
            raw_response={"ok": True},
        )

        materialized = HarnessSnapshotBuilder(harness, assets=assets).materialize(
            event=event.to_dict(),
            extraction=extraction,
            run_id="run-no-entry",
            model_version="gpt-test",
        )
    finally:
        conn.close()

    assert materialized["seed"]["seed_status"] == "market_unavailable"
    assert materialized["seed"]["top_linked_symbols"] == ["BNB"]
    assert materialized["snapshots"] == []
    assert "missing_entry_market" in materialized["seed"]["risks"]


def _upsert_asset_with_price(
    assets: AssetRepository,
    *,
    symbol: str,
    address: str,
    observed_at_ms: int,
    price: float,
) -> str:
    result = assets.upsert_dex_asset(
        chain="ethereum",
        address=address,
        symbol=symbol,
        observed_at_ms=observed_at_ms,
        provider="test",
    )
    assets.insert_market_snapshot(
        asset_id=str(result.asset["asset_id"]),
        venue_id=str(result.venue["venue_id"]),
        provider="test",
        observed_at_ms=observed_at_ms,
        price_usd=price,
    )
    return str(result.asset["asset_id"])
