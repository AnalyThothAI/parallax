from __future__ import annotations

from gmgn_twitter_intel.storage.asset_repository import AssetRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event


def open_asset_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    repo = AssetRepository(conn)
    return conn, evidence, repo


def test_upsert_unresolved_symbol_asset_round_trips(tmp_path):
    conn, evidence, repo = open_asset_repo(tmp_path)
    try:
        evidence.insert_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
        asset = repo.upsert_unresolved_symbol(
            symbol="mirror",
            event_id="event-1",
            observed_at_ms=1_700_000_000_000,
        )
        candidates = repo.candidates_for_symbol("MIRROR")
    finally:
        conn.close()

    assert asset["asset_id"] == "asset:unresolved:MIRROR"
    assert asset["asset_type"] == "unresolved_symbol"
    assert asset["canonical_symbol"] == "MIRROR"
    assert asset["identity_status"] == "unresolved"
    assert [candidate["asset_id"] for candidate in candidates] == ["asset:unresolved:MIRROR"]


def test_upsert_cex_instrument_creates_asset_alias_and_venue(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        result = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-USDT",
            base_symbol="btc",
            quote_symbol="USDT",
            observed_at_ms=1_700_000_000_000,
            source_payload_hash="payload-hash",
        )
        candidates = repo.candidates_for_symbol("BTC")
    finally:
        conn.close()

    assert result.asset["asset_type"] == "cex_asset"
    assert result.asset["canonical_symbol"] == "BTC"
    assert result.venue is not None
    assert result.venue["venue_type"] == "cex"
    assert result.venue["exchange"] == "okx"
    assert result.venue["inst_id"] == "BTC-USDT"
    assert candidates[0]["asset_id"] == result.asset["asset_id"]
    assert candidates[0]["venue_id"] == result.venue["venue_id"]


def test_record_unresolved_attribution_and_find_symbol_mentions(tmp_path):
    conn, evidence, repo = open_asset_repo(tmp_path)
    try:
        evidence.insert_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
        mention = repo.insert_mention(
            event_id="event-1",
            mention_type="cashtag",
            raw_value="$mirror",
            normalized_symbol="MIRROR",
            source="deterministic_extractor",
            mention_confidence=0.8,
            created_at_ms=1_700_000_000_000,
        )
        asset = repo.upsert_unresolved_symbol(
            symbol="MIRROR",
            event_id="event-1",
            observed_at_ms=1_700_000_000_000,
        )
        attribution = repo.insert_attribution(
            event_id="event-1",
            mention_id=mention["mention_id"],
            asset_id=asset["asset_id"],
            venue_id=None,
            attribution_status="unresolved",
            attribution_weight=1.0,
            confidence=0.35,
            identity_status="unresolved",
            reasons=["symbol_has_no_candidates"],
            risks=[],
            decision_time_ms=1_700_000_000_000,
            created_at_ms=1_700_000_000_000,
        )
        rows = repo.events_for_symbol_mentions("MIRROR", limit=10)
    finally:
        conn.close()

    assert attribution["attribution_status"] == "unresolved"
    assert attribution["venue_id"] is None
    assert rows[0]["event_id"] == "event-1"
    assert rows[0]["normalized_symbol"] == "MIRROR"
    assert rows[0]["attribution_status"] == "unresolved"
