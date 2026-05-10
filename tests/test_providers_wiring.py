from __future__ import annotations

from gmgn_twitter_intel.app.runtime.providers_wiring import OkxDexMarketProvider, okx_chain_indexes_to_chain_ids
from gmgn_twitter_intel.integrations.okx.models import OkxDexTokenCandidate


def test_unknown_numeric_okx_dex_chain_indexes_round_trip_through_domain_provider() -> None:
    client = FakeOkxDexClient()
    provider = OkxDexMarketProvider(client)

    chain_ids = okx_chain_indexes_to_chain_ids(("137",))
    provider.search_tokens(query="POL", chain_ids=chain_ids)

    assert chain_ids == ("137",)
    assert client.search_requests == [{"query": "POL", "chain_indexes": ("137",)}]


class FakeOkxDexClient:
    def __init__(self) -> None:
        self.search_requests: list[dict[str, object]] = []

    def search_tokens(self, *, query: str, chain_indexes: tuple[str, ...]):
        self.search_requests.append({"query": query, "chain_indexes": tuple(chain_indexes)})
        return [
            OkxDexTokenCandidate(
                chain_index="137",
                chain=None,
                address="0x0000000000000000000000000000000000000137",
                symbol="POL",
                name="Polygon Ecosystem Token",
                price_usd=1.0,
                market_cap_usd=None,
                liquidity_usd=None,
                holders=None,
                community_recognized=None,
                raw={"chainIndex": "137", "tokenSymbol": "POL"},
            )
        ]

    def token_prices(self, tokens):
        return []
