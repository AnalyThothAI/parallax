from __future__ import annotations

import pytest

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.providers import DexTokenCandidate, DexTokenQuote
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import (
    ResolutionRefreshWorker,
    _process_address_lookup,
)
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION, SignalRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _evm_address(index: int) -> str:
    return f"0x{index:040x}"


def _dex_candidate(
    *,
    chain_id: str,
    address: str,
    symbol: str = "HANTA",
    market_cap_usd: float | None = None,
    liquidity_usd: float | None = None,
    holders: int | None = None,
    price_usd: float | None = 1.0,
) -> DexTokenCandidate:
    return DexTokenCandidate(
        chain_id=chain_id,
        address=address,
        symbol=symbol,
        name=symbol,
        price_usd=price_usd,
        market_cap_usd=market_cap_usd,
        liquidity_usd=liquidity_usd,
        holders=holders,
        community_recognized=None,
        raw={"chain_id": chain_id, "tokenContractAddress": address, "tokenSymbol": symbol},
    )


@pytest.mark.skip(
    reason="registry_assets.symbol/name/decimals dropped by token-identity-evidence hard-cut "
    "(migration 20260510_0021); test predates new asset_identity_evidence/current model. "
    "Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'."
)
def test_resolution_refresh_worker_resolves_recent_symbol_and_rebuilds_radar(tmp_path):
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

        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_discovery_market=FakeDexMarket(
                candidates=[
                    DexTokenCandidate(
                        chain_id="eip155:1",
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
            chain_ids=("eip155:1",),
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


def test_resolution_refresh_worker_skips_symbol_lookup_after_retained_candidate_resolves_intent(tmp_path):
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
        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_discovery_market=FakeDexMarket(
                candidates=[
                    DexTokenCandidate(
                        chain_id="eip155:1",
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
            chain_ids=("eip155:1",),
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


def test_resolution_refresh_worker_retries_hot_not_found_before_default_ttl(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_145_100_000
    address = "0x54b28991b167582f18ba0259e0173176ca125505"
    dex_market = FakeDexMarket(candidates=[])
    try:
        migrate(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_discovery_market=dex_market,
            dex_quote_market=dex_market,
            chain_ids=("eip155:1",),
            interval_seconds=60,
        )
        ingested = ingest.ingest_event(
            make_event(
                "event-fresh-1",
                text="$FRESH is waking up",
                received_at_ms=now_ms,
                is_watched=True,
            ),
            is_watched=True,
        )

        first = worker.run_once(now_ms=now_ms + 60_000)
        before = repositories_for_connection(conn).intent_resolutions.active_resolution_for_intent(
            ingested.token_intents[0]["intent_id"]
        )
        dex_market.candidates = [
            DexTokenCandidate(
                chain_id="eip155:1",
                address=address,
                symbol="FRESH",
                name="Fresh",
                price_usd=0.5,
                market_cap_usd=500_000.0,
                liquidity_usd=50_000.0,
                holders=500,
                community_recognized=True,
                raw={"tokenSymbol": "FRESH"},
            )
        ]

        second = worker.run_once(now_ms=now_ms + 120_000)
        repos = repositories_for_connection(conn)
        after = repos.intent_resolutions.active_resolution_for_intent(ingested.token_intents[0]["intent_id"])
    finally:
        conn.close()

    assert first["lookups_done"] == 1
    assert first["search_hits"] == 0
    assert before["resolution_status"] == "NIL"
    assert second["lookups_done"] == 1
    assert second["search_hits"] == 1
    assert second["reprocessed_intents"] == 1
    assert second["anchor"] is None
    assert after["resolution_status"] == "UNIQUE_BY_CONTEXT"
    assert after["target_id"] == f"asset:eip155:1:erc20:{address}"


@pytest.mark.skip(
    reason="registry_assets.symbol dropped by token-identity-evidence hard-cut "
    "(migration 20260510_0021); test asserts demoted_search by symbol selector. "
    "Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'."
)
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
        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_discovery_market=FakeDexMarket(
                candidates=[
                    _dex_candidate(
                        chain_id="solana",
                        address="SoLow111111111111111111111111111111111111",
                        market_cap_usd=1,
                        liquidity_usd=1,
                        holders=1,
                    ),
                    _dex_candidate(
                        chain_id="solana",
                        address="SoTop111111111111111111111111111111111111",
                        market_cap_usd=1_000_000,
                        liquidity_usd=50_000,
                        holders=5_000,
                    ),
                    _dex_candidate(
                        chain_id="solana",
                        address="SoTop222222222222222222222222222222222222",
                        market_cap_usd=900_000,
                        liquidity_usd=60_000,
                        holders=4_000,
                    ),
                    _dex_candidate(
                        chain_id="solana",
                        address="SoTop333333333333333333333333333333333333",
                        market_cap_usd=800_000,
                        liquidity_usd=70_000,
                        holders=3_000,
                    ),
                    _dex_candidate(
                        chain_id="solana",
                        address="SoLow222222222222222222222222222222222222",
                        market_cap_usd=2,
                        liquidity_usd=2,
                        holders=2,
                    ),
                    _dex_candidate(
                        chain_id="solana",
                        address="SoLow333333333333333333333333333333333333",
                        market_cap_usd=3,
                        liquidity_usd=3,
                        holders=3,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(1),
                        market_cap_usd=10,
                        liquidity_usd=10,
                        holders=10,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(2),
                        market_cap_usd=700_000,
                        liquidity_usd=20_000,
                        holders=2_000,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(3),
                        market_cap_usd=600_000,
                        liquidity_usd=30_000,
                        holders=1_500,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(4),
                        market_cap_usd=500_000,
                        liquidity_usd=40_000,
                        holders=1_000,
                    ),
                ]
            ),
            chain_ids=("solana", "eip155:56"),
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


@pytest.mark.skip(
    reason="upsert_chain_asset(symbol=…, name=…, decimals=…, source=…) signature removed by "
    "token-identity-evidence hard-cut; identity now lives in asset_identity_evidence/current. "
    "Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'."
)
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
        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_discovery_market=FakeDexMarket(
                candidates=[
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(1),
                        market_cap_usd=1_000_000,
                        liquidity_usd=10_000,
                        holders=1_000,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(2),
                        market_cap_usd=900_000,
                        liquidity_usd=10_000,
                        holders=900,
                    ),
                    _dex_candidate(
                        chain_id="eip155:56",
                        address=_evm_address(3),
                        market_cap_usd=800_000,
                        liquidity_usd=10_000,
                        holders=800,
                    ),
                ]
            ),
            chain_ids=("eip155:56",),
            interval_seconds=60,
        )

        worker.run_once(now_ms=now_ms + 60_000)
        row = conn.execute("SELECT status FROM registry_assets WHERE asset_id = %s", (old["asset_id"],)).fetchone()
    finally:
        conn.close()

    assert row["status"] == "demoted_search"


@pytest.mark.skip(
    reason="SELECT registry_assets.symbol references column dropped by hard-cut "
    "(migration 20260510_0021); should select via asset_identity_current. "
    "Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'."
)
def test_address_discovery_remains_uncapped(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    address = _evm_address(77)
    try:
        migrate(conn)
        result = _process_address_lookup(
            repos=repositories_for_connection(conn),
            lookup_key=f"address:eip155:56:{address}",
            dex_discovery_market=FakeDexMarket(
                candidates=[
                    _dex_candidate(chain_id="eip155:56", address=_evm_address(1), market_cap_usd=1, liquidity_usd=1),
                    _dex_candidate(chain_id="eip155:56", address=address, market_cap_usd=2, liquidity_usd=2),
                    _dex_candidate(chain_id="eip155:56", address=_evm_address(3), market_cap_usd=3, liquidity_usd=3),
                ]
            ),
            chain_ids=("eip155:56",),
            now_ms=1_000,
        )
        row = conn.execute("SELECT address, status FROM registry_assets WHERE upper(symbol) = 'HANTA'").fetchone()
    finally:
        conn.close()

    assert result["assets_written"] == 1
    assert row["address"] == address
    assert row["status"] == "candidate"


class FakeDexMarket:
    def __init__(self, *, candidates):
        self.candidates = candidates
        self.search_requests = []
        self.price_requests = []

    def search_tokens(self, *, query, chain_ids):
        self.search_requests.append({"query": query, "chain_ids": tuple(chain_ids)})
        return list(self.candidates)

    def token_quotes(self, requests):
        self.price_requests.append(list(requests))
        prices = []
        for request in requests:
            prices.extend(
                DexTokenQuote(
                    chain_id=candidate.chain_id,
                    address=candidate.address,
                    observed_at_ms=1_778_145_220_000,
                    price_usd=candidate.price_usd,
                    market_cap_usd=candidate.market_cap_usd,
                    liquidity_usd=candidate.liquidity_usd,
                    holders=candidate.holders,
                    raw={"priceUsd": candidate.price_usd},
                )
                for candidate in self.candidates
                if candidate.chain_id == request.chain_id and candidate.address.lower() == request.address.lower()
            )
        return prices


class FakeEnrichment:
    def enqueue_watched_event(self, *, event_id, received_at_ms, priority=None, commit=False):
        return None
