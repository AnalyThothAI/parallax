from dataclasses import dataclass

from gmgn_twitter_intel.market.gmgn_openapi_client import GmgnTokenInfo
from gmgn_twitter_intel.pipeline.token_market_enricher import TokenMarketEnricher
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_sqlite_repositories import make_event


@dataclass(frozen=True, slots=True)
class Mention:
    identity_key: str
    token_id: str | None
    identity_status: str
    chain: str | None
    address: str | None
    symbol: str
    source: str


class FakeGmgnClient:
    def __init__(self, *, hit_chain: str = "sol"):
        self.calls: list[tuple[str, str]] = []
        self.hit_chain = hit_chain

    def get_token_info(self, *, chain: str, address: str):
        self.calls.append((chain, address))
        if chain != self.hit_chain:
            return None
        return GmgnTokenInfo(
            chain=chain,
            address=address,
            symbol="DOG",
            name="Dog",
            icon_url=None,
            price=0.2,
            previous_price=None,
            market_cap=200000.0,
            raw={"symbol": "DOG"},
        )


def test_token_market_enricher_fetches_once_per_unique_resolved_mention(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    tokens = TokenRepository(conn)
    client = FakeGmgnClient()
    enricher = TokenMarketEnricher(tokens=tokens, client=client)
    try:
        evidence.insert_event(make_event("event-1"), is_watched=True)
        mentions = [
            Mention("token:sol:dog", "token:sol:dog", "resolved_ca", "sol", "dog", "DOG", "regex"),
            Mention("token:sol:dog", "token:sol:dog", "resolved_ca", "sol", "dog", "DOG", "regex"),
            Mention("symbol:DOG", None, "unresolved_symbol", None, None, "DOG", "cashtag"),
        ]
        enriched = enricher.enrich_mentions(
            event_id="event-1",
            mentions=mentions,
            received_at_ms=1_700_000_000_000,
            source_channel="gmgn_openapi_token_info",
        )
        market = tokens.latest_market_snapshot("token:solana:dog")
    finally:
        conn.close()

    assert enriched == 1
    assert client.calls == [("sol", "dog")]
    assert market["price"] == 0.2
    assert market["source_channel"] == "gmgn_openapi_token_info"


def test_token_market_enricher_rewrites_evm_mention_to_openapi_resolved_chain(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    tokens = TokenRepository(conn)
    client = FakeGmgnClient(hit_chain="base")
    enricher = TokenMarketEnricher(tokens=tokens, client=client, evm_candidate_chains=("base", "bsc", "eth"))
    try:
        evidence.insert_event(make_event("event-1"), is_watched=True)
        mentions = [
            Mention("token:eth:0xabc", "token:eth:0xabc", "resolved_ca", "eth", "0xabc", "ABC", "regex"),
        ]
        resolved, enriched = enricher.resolve_and_enrich_mentions(
            event_id="event-1",
            mentions=mentions,
            received_at_ms=1_700_000_000_000,
            source_channel="gmgn_openapi_token_info",
        )
        market = tokens.latest_market_snapshot("token:base:0xabc")
    finally:
        conn.close()

    assert enriched == 1
    assert client.calls == [("eth", "0xabc"), ("base", "0xabc")]
    assert resolved[0].token_id == "token:base:0xabc"
    assert resolved[0].chain == "base"
    assert market["price"] == 0.2
