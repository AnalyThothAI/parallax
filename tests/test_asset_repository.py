from __future__ import annotations

from gmgn_twitter_intel.storage.asset_repository import AssetRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


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


def test_candidates_for_ca_filters_by_chain_without_sql_parameter_mismatch(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        result = repo.upsert_dex_asset(
            chain="solana",
            address="Mirror111",
            symbol="MIRROR",
            observed_at_ms=1_700_000_000_000,
            provider="okx_dex",
        )
        candidates = repo.candidates_for_ca(chain="solana", address="Mirror111")
    finally:
        conn.close()

    assert [candidate["asset_id"] for candidate in candidates] == [result.asset["asset_id"]]
    assert candidates[0]["venue_id"] == result.venue["venue_id"]


def test_resolution_claim_prioritizes_contract_address_jobs_over_symbols(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        repo.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol="USDUC",
            next_run_at_ms=1_700_000_000_000,
            commit=False,
        )
        repo.queue_resolution_job(
            job_type="ca_resolution",
            chain_hint="bsc",
            address_hint="0x8f32420f2e3728c49399b00dd0a796602d984444",
            next_run_at_ms=1_700_000_100_000,
            commit=True,
        )

        job = repo.claim_resolution_job(now_ms=1_700_000_200_000)
    finally:
        conn.close()

    assert job is not None
    assert job["job_type"] == "ca_resolution"
    assert job["chain_hint"] == "bsc"


def test_resolution_claim_recovers_stale_running_jobs(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        repo.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol="USDUC",
            next_run_at_ms=1_700_000_000_000,
        )
        first = repo.claim_resolution_job(now_ms=1_700_000_000_100)
        second = repo.claim_resolution_job(now_ms=1_700_000_300_100)
    finally:
        conn.close()

    assert first is not None
    assert first["status"] == "running"
    assert second is not None
    assert second["job_id"] == first["job_id"]
    assert second["attempt_count"] == 2


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
