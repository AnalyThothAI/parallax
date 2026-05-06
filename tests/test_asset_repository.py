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


def test_candidates_for_symbol_prefers_usdt_spot_cex_venue(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-AED",
            base_symbol="BTC",
            quote_symbol="AED",
            observed_at_ms=1_700_000_000_000,
            commit=False,
        )
        usdt = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            observed_at_ms=1_700_000_000_001,
            commit=True,
        )
        candidates = repo.candidates_for_symbol("BTC")
    finally:
        conn.close()

    assert candidates[0]["venue_id"] == usdt.venue["venue_id"]
    assert candidates[0]["quote_symbol"] == "USDT"


def test_asset_flow_rows_use_preferred_cex_usdt_venue_and_market(tmp_path):
    conn, evidence, repo = open_asset_repo(tmp_path)
    try:
        aed = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-AED",
            base_symbol="BTC",
            quote_symbol="AED",
            observed_at_ms=1_700_000_000_000,
            commit=False,
        )
        usdt = repo.upsert_cex_instrument(
            exchange="okx",
            inst_type="SPOT",
            inst_id="BTC-USDT",
            base_symbol="BTC",
            quote_symbol="USDT",
            observed_at_ms=1_700_000_000_000,
            commit=False,
        )
        evidence.insert_event(make_event("event-btc", text="$BTC is moving"), is_watched=False, commit=False)
        mention = repo.insert_mention(
            event_id="event-btc",
            mention_type="cashtag",
            raw_value="$BTC",
            normalized_symbol="BTC",
            source="deterministic_extractor",
            mention_confidence=0.8,
            created_at_ms=1_700_000_000_000,
            commit=False,
        )
        repo.insert_attribution(
            event_id="event-btc",
            mention_id=mention["mention_id"],
            asset_id=aed.asset["asset_id"],
            venue_id=aed.venue["venue_id"],
            attribution_status="selected",
            attribution_weight=1.0,
            confidence=0.9,
            identity_status="resolved",
            reasons=["legacy_selected_aed_venue"],
            risks=[],
            decision_time_ms=1_700_000_000_000,
            created_at_ms=1_700_000_000_000,
            commit=False,
        )
        repo.insert_market_snapshot(
            asset_id=aed.asset["asset_id"],
            venue_id=aed.venue["venue_id"],
            provider="okx_cex",
            observed_at_ms=1_700_000_010_000,
            price_usd=22_000.0,
            volume_24h_usd=1_000.0,
            commit=False,
        )
        repo.insert_market_snapshot(
            asset_id=usdt.asset["asset_id"],
            venue_id=usdt.venue["venue_id"],
            provider="okx_cex",
            observed_at_ms=1_700_000_010_000,
            price_usd=69_000.0,
            volume_24h_usd=2_000.0,
            commit=True,
        )

        rows = repo.asset_flow_rows(
            since_ms=1_699_999_900_000,
            watched_only=False,
            limit=20,
            now_ms=1_700_000_020_000,
        )
    finally:
        conn.close()

    assert rows[0]["venue_id"] == usdt.venue["venue_id"]
    assert rows[0]["inst_id"] == "BTC-USDT"
    assert rows[0]["market_price_usd"] == 69_000.0


def test_asset_flow_rows_expose_non_address_symbol_alias_for_legacy_dex_assets(tmp_path):
    conn, evidence, repo = open_asset_repo(tmp_path)
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    asset_id = f"asset:dex:solana:{address.lower()}"
    try:
        result = repo.upsert_dex_asset(
            chain="solana",
            address=address,
            symbol="USDUC",
            observed_at_ms=1_700_000_000_000,
            provider="okx_dex",
            commit=False,
        )
        conn.execute(
            "UPDATE assets SET canonical_symbol = %s, display_name = %s WHERE asset_id = %s",
            (address.upper(), address.upper(), asset_id),
        )
        evidence.insert_event(make_event("event-usduc", text=address), is_watched=False)
        mention = repo.insert_mention(
            event_id="event-usduc",
            mention_type="ca",
            raw_value=address,
            chain_hint="solana",
            address_hint=address,
            source="deterministic_extractor",
            mention_confidence=1.0,
            created_at_ms=1_700_000_000_000,
            commit=False,
        )
        repo.insert_attribution(
            event_id="event-usduc",
            mention_id=mention["mention_id"],
            asset_id=result.asset["asset_id"],
            venue_id=result.venue["venue_id"],
            attribution_status="direct",
            attribution_weight=1.0,
            confidence=0.95,
            identity_status="resolved",
            reasons=["direct_ca"],
            risks=[],
            decision_time_ms=1_700_000_000_000,
            created_at_ms=1_700_000_000_000,
            commit=True,
        )

        rows = repo.asset_flow_rows(
            since_ms=1_699_999_900_000,
            watched_only=False,
            limit=20,
            now_ms=1_700_000_020_000,
        )
    finally:
        conn.close()

    assert rows[0]["canonical_symbol"] == address.upper()
    assert rows[0]["display_symbol"] == "USDUC"


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


def test_dex_asset_provider_symbol_survives_later_ca_only_upsert(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    try:
        provider = repo.upsert_dex_asset(
            chain="solana",
            address=address,
            symbol="USDUC",
            observed_at_ms=1_700_000_000_000,
            provider="okx_dex",
            commit=False,
        )
        later_direct_ca = repo.upsert_dex_asset(
            chain="solana",
            address=address,
            symbol=address,
            observed_at_ms=1_700_000_060_000,
            provider="deterministic",
            commit=True,
        )
        candidates_for_address_as_symbol = repo.candidates_for_symbol(address)
    finally:
        conn.close()

    assert later_direct_ca.asset["asset_id"] == provider.asset["asset_id"]
    assert later_direct_ca.asset["canonical_symbol"] == "USDUC"
    assert later_direct_ca.asset["display_name"] == "USDUC"
    assert candidates_for_address_as_symbol == []


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


def test_resolution_claim_uses_next_run_before_attempt_count_for_hot_requeues(tmp_path):
    conn, _, repo = open_asset_repo(tmp_path)
    try:
        repo.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol="USDUC",
            next_run_at_ms=1_700_000_000_000,
        )
        first = repo.claim_resolution_job(now_ms=1_700_000_000_100)
        repo.finish_resolution_job(job_id=first["job_id"], status="succeeded", commit=False)
        repo.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol="USDUC",
            next_run_at_ms=1_700_000_000_200,
            commit=False,
        )
        repo.queue_resolution_job(
            job_type="symbol_resolution",
            normalized_symbol="COLD",
            next_run_at_ms=1_700_000_010_000,
            commit=True,
        )

        hot = repo.claim_resolution_job(now_ms=1_700_000_020_000)
    finally:
        conn.close()

    assert hot is not None
    assert hot["normalized_symbol"] == "USDUC"


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
