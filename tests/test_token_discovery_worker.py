from __future__ import annotations

from gmgn_twitter_intel.market.okx_models import OkxDexTokenCandidate
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.token_discovery_worker import TokenDiscoveryWorker
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.repository_session import repositories_for_connection
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate


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
        rows = repos.token_radar.latest_rows(window="5m", scope="all", limit=10)
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


class FakeDexClient:
    def __init__(self, *, candidates):
        self.candidates = candidates
        self.search_requests = []

    def search_tokens(self, *, query, chain_indexes):
        self.search_requests.append({"query": query, "chain_indexes": tuple(chain_indexes)})
        return list(self.candidates)


class FakeEnrichment:
    def enqueue_watched_event(self, *, event_id, received_at_ms, commit=False):
        return None
