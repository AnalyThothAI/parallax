from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxDexTokenCandidate
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.token_discovery_worker import TokenDiscoveryWorker, _process_address_lookup
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.repository_session import repositories_for_connection
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _evm_address(index: int) -> str:
    return f"0x{index:040x}"


def _dex_candidate(
    *,
    chain_index: str,
    address: str,
    symbol: str = "HANTA",
    market_cap_usd: float | None = None,
    liquidity_usd: float | None = None,
    holders: int | None = None,
    price_usd: float | None = 1.0,
) -> OkxDexTokenCandidate:
    return OkxDexTokenCandidate(
        chain_index=chain_index,
        chain="Solana" if chain_index == "501" else "BNB Chain",
        address=address,
        symbol=symbol,
        name=symbol,
        price_usd=price_usd,
        market_cap_usd=market_cap_usd,
        liquidity_usd=liquidity_usd,
        holders=holders,
        community_recognized=None,
        raw={"chainIndex": chain_index, "tokenContractAddress": address, "tokenSymbol": symbol},
    )


def test_token_discovery_worker_resolves_recent_symbol_and_rebuilds_radar(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_145_100_000
    address = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        migrate(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        event = make_event(
            "event-upeg",
            text="$UPEG is getting attention",
            received_at_ms=now_ms,
            is_watched=True,
        )
        ingested = ingest.ingest_event(event, is_watched=True)
        repos = repositories_for_connection(conn)
        before = repos.intent_resolutions.active_resolution_for_intent(ingested.token_intents[0]["intent_id"])

        worker = TokenDiscoveryWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_client=FakeDexClient(
                candidates=[
                    OkxDexTokenCandidate(
                        chain_index="1",
                        chain=None,
                        address=address,
                        symbol="UPEG",
                        name="Unipeg",
                        price_usd=1061.0,
                        market_cap_usd=10_600_000.0,
                        liquidity_usd=920_000.0,
                        holders=4_885,
                        community_recognized=True,
                        raw={"tokenSymbol": "UPEG"},
                    )
                ]
            ),
            chain_indexes=("1",),
            interval_seconds=60,
        )

        result = worker.run_once(now_ms=now_ms + 60_000)
        after = repos.intent_resolutions.active_resolution_for_intent(ingested.token_intents[0]["intent_id"])
        rows = repos.token_radar.latest_rows(
            window="5m",
            scope="all",
            limit=10,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
    finally:
        conn.close()

    assert before["resolution_status"] == "NIL"
    assert before["target_id"] is None
    assert result["lookups_selected"] == 1
    assert result["search_requests"] == 1
    assert result["search_hits"] == 1
    assert result["assets_written"] == 1
    assert result["reprocessed_intents"] == 1
    assert result["projection"]["rows_written"] >= 1
    assert result["discovery_result_counts"] == {"found": 1}
    assert after["resolution_status"] == "UNIQUE_BY_CONTEXT"
    assert after["target_type"] == "Asset"
    assert after["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert rows[0]["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert rows[0]["market_json"]["price_usd"] == 1061.0


def test_token_discovery_worker_skips_symbol_lookup_after_retained_candidate_resolves_intent(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_145_100_000
    address = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        migrate(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        worker = TokenDiscoveryWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_client=FakeDexClient(
                candidates=[
                    OkxDexTokenCandidate(
                        chain_index="1",
                        chain=None,
                        address=address,
                        symbol="UPEG",
                        name="Unipeg",
                        price_usd=1061.0,
                        market_cap_usd=10_600_000.0,
                        liquidity_usd=920_000.0,
                        holders=4_885,
                        community_recognized=True,
                        raw={"tokenSymbol": "UPEG"},
                    )
                ]
            ),
            chain_indexes=("1",),
            interval_seconds=60,
        )

        first_event = make_event(
            "event-upeg-1",
            text="$UPEG is getting attention",
            received_at_ms=now_ms,
            is_watched=True,
        )
        ingest.ingest_event(first_event, is_watched=True)
        worker.run_once(now_ms=now_ms + 60_000)

        second_event = make_event(
            "event-upeg-2",
            text="$UPEG again",
            received_at_ms=now_ms + 40 * 60_000,
            is_watched=True,
        )
        second_ingested = ingest.ingest_event(second_event, is_watched=True)
        repos = repositories_for_connection(conn)
        before = repos.intent_resolutions.active_resolution_for_intent(second_ingested.token_intents[0]["intent_id"])

        result = worker.run_once(now_ms=second_event.received_at_ms + 1_000)
        after = repos.intent_resolutions.active_resolution_for_intent(second_ingested.token_intents[0]["intent_id"])
    finally:
        conn.close()

    assert before["resolution_status"] == "UNIQUE_BY_CONTEXT"
    assert result["lookups_selected"] == 0
    assert result["lookups_done"] == 0
    assert result["reprocessed_intents"] == 0
    assert after["resolution_status"] == "UNIQUE_BY_CONTEXT"
    assert after["target_id"] == f"asset:eip155:1:erc20:{address}"


def test_dex_symbol_discovery_retains_top_three_per_chain(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_145_100_000
    try:
        migrate(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        ingest.ingest_event(
            make_event("event-hanta-top3", text="$HANTA is moving", received_at_ms=now_ms, is_watched=True),
            is_watched=True,
        )
        worker = TokenDiscoveryWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_client=FakeDexClient(
                candidates=[
                    _dex_candidate(
                        chain_index="501",
                        address="SoLow111111111111111111111111111111111111",
                        market_cap_usd=1,
                        liquidity_usd=1,
                        holders=1,
                    ),
                    _dex_candidate(
                        chain_index="501",
                        address="SoTop111111111111111111111111111111111111",
                        market_cap_usd=1_000_000,
                        liquidity_usd=50_000,
                        holders=5_000,
                    ),
                    _dex_candidate(
                        chain_index="501",
                        address="SoTop222222222222222222222222222222222222",
                        market_cap_usd=900_000,
                        liquidity_usd=60_000,
                        holders=4_000,
                    ),
                    _dex_candidate(
                        chain_index="501",
                        address="SoTop333333333333333333333333333333333333",
                        market_cap_usd=800_000,
                        liquidity_usd=70_000,
                        holders=3_000,
                    ),
                    _dex_candidate(
                        chain_index="501",
                        address="SoLow222222222222222222222222222222222222",
                        market_cap_usd=2,
                        liquidity_usd=2,
                        holders=2,
                    ),
                    _dex_candidate(
                        chain_index="501",
                        address="SoLow333333333333333333333333333333333333",
                        market_cap_usd=3,
                        liquidity_usd=3,
                        holders=3,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(1),
                        market_cap_usd=10,
                        liquidity_usd=10,
                        holders=10,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(2),
                        market_cap_usd=700_000,
                        liquidity_usd=20_000,
                        holders=2_000,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(3),
                        market_cap_usd=600_000,
                        liquidity_usd=30_000,
                        holders=1_500,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(4),
                        market_cap_usd=500_000,
                        liquidity_usd=40_000,
                        holders=1_000,
                    ),
                ]
            ),
            chain_indexes=("501", "56"),
            interval_seconds=60,
        )

        result = worker.run_once(now_ms=now_ms + 60_000)
        rows = conn.execute(
            """
            SELECT chain_id, address, status
            FROM registry_assets
            WHERE upper(symbol) = 'HANTA'
            ORDER BY chain_id, address
            """
        ).fetchall()
    finally:
        conn.close()

    assert result["search_candidates_seen"] == 10
    assert result["search_candidates_rejected"] == 4
    assert result["assets_written"] == 6
    by_chain: dict[str, list[str]] = {}
    for row in rows:
        assert row["status"] == "candidate"
        by_chain.setdefault(row["chain_id"], []).append(row["address"])
    assert by_chain["eip155:56"] == [_evm_address(2), _evm_address(3), _evm_address(4)]
    assert by_chain["solana"] == [
        "SoTop111111111111111111111111111111111111",
        "SoTop222222222222222222222222222222222222",
        "SoTop333333333333333333333333333333333333",
    ]


def test_dex_symbol_discovery_demotes_old_unretained_search_assets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_145_100_000
    try:
        migrate(conn)
        repos = repositories_for_connection(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        ingest.ingest_event(
            make_event("event-hanta-demote", text="$HANTA", received_at_ms=now_ms + 1_000, is_watched=True),
            is_watched=True,
        )
        old = repos.registry.upsert_chain_asset(
            chain_id="eip155:56",
            address=_evm_address(99),
            symbol="HANTA",
            name="Old HANTA",
            decimals=18,
            source="okx_dex_search",
            observed_at_ms=now_ms,
        )
        worker = TokenDiscoveryWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_client=FakeDexClient(
                candidates=[
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(1),
                        market_cap_usd=1_000_000,
                        liquidity_usd=10_000,
                        holders=1_000,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(2),
                        market_cap_usd=900_000,
                        liquidity_usd=10_000,
                        holders=900,
                    ),
                    _dex_candidate(
                        chain_index="56",
                        address=_evm_address(3),
                        market_cap_usd=800_000,
                        liquidity_usd=10_000,
                        holders=800,
                    ),
                ]
            ),
            chain_indexes=("56",),
            interval_seconds=60,
        )

        worker.run_once(now_ms=now_ms + 60_000)
        row = conn.execute("SELECT status FROM registry_assets WHERE asset_id = %s", (old["asset_id"],)).fetchone()
    finally:
        conn.close()

    assert row["status"] == "demoted_search"


def test_address_discovery_remains_uncapped(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    address = _evm_address(77)
    try:
        migrate(conn)
        result = _process_address_lookup(
            repos=repositories_for_connection(conn),
            lookup_key=f"address:eip155:56:{address}",
            dex_client=FakeDexClient(
                candidates=[
                    _dex_candidate(chain_index="56", address=_evm_address(1), market_cap_usd=1, liquidity_usd=1),
                    _dex_candidate(chain_index="56", address=address, market_cap_usd=2, liquidity_usd=2),
                    _dex_candidate(chain_index="56", address=_evm_address(3), market_cap_usd=3, liquidity_usd=3),
                ]
            ),
            chain_indexes=("56",),
            now_ms=1_000,
        )
        row = conn.execute("SELECT address, status FROM registry_assets WHERE upper(symbol) = 'HANTA'").fetchone()
    finally:
        conn.close()

    assert result["assets_written"] == 1
    assert row["address"] == address
    assert row["status"] == "candidate"


class FakeDexClient:
    def __init__(self, *, candidates):
        self.candidates = candidates
        self.search_requests = []

    def search_tokens(self, *, query, chain_indexes):
        self.search_requests.append({"query": query, "chain_indexes": tuple(chain_indexes)})
        return list(self.candidates)


class FakeEnrichment:
    def enqueue_watched_event(self, *, event_id, received_at_ms, priority=None, commit=False):
        return None
