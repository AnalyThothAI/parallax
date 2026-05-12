from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.providers import DexTokenCandidate
from gmgn_twitter_intel.domains.asset_market.runtime.token_discovery_worker import (
    FOUND_ADDRESS_REFRESH_MS,
    FOUND_SYMBOL_REFRESH_MS,
    NOT_FOUND_ADDRESS_REFRESH_MS,
    NOT_FOUND_SYMBOL_REFRESH_MS,
    _process_dex_symbol_lookup,
    _refresh_ms,
)


def test_discovery_error_refresh_uses_exponential_backoff_by_error_count():
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=0) == 30_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=1) == 60_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=3) == 1_800_000
    assert _refresh_ms(lookup_key="symbol:UPEG", status="error", error_count=10) == 3_600_000


def test_discovery_refresh_keeps_found_and_not_found_cadences():
    assert _refresh_ms(lookup_key="symbol:UPEG", status="found", error_count=10) == FOUND_SYMBOL_REFRESH_MS
    assert _refresh_ms(lookup_key="symbol:UPEG", status="not_found", error_count=10) == NOT_FOUND_SYMBOL_REFRESH_MS
    assert _refresh_ms(lookup_key="address:eip155:1:0xabc", status="found", error_count=10) == FOUND_ADDRESS_REFRESH_MS
    assert (
        _refresh_ms(lookup_key="address:eip155:1:0xabc", status="not_found", error_count=10)
        == NOT_FOUND_ADDRESS_REFRESH_MS
    )


def test_symbol_lookup_writes_provider_rank_to_identity_payload():
    repos = FakeRepos()

    result = _process_dex_symbol_lookup(
        repos=repos,
        lookup_key="symbol:SPARSE",
        dex_market=FakeDexMarket(
            candidates=[
                _candidate(chain_id="eip155:1", address="0x1111111111111111111111111111111111111111"),
                _candidate(chain_id="eip155:56", address="0x2222222222222222222222222222222222222222"),
            ]
        ),
        chain_ids=("eip155:1", "eip155:56"),
        now_ms=1_778_200_000_000,
    )

    assert result["search_hits"] == 2
    by_asset_id = {item["asset_id"]: item["raw_payload"] for item in repos.identity_evidence.writes}
    assert by_asset_id["asset:eip155:1:erc20:0x1111111111111111111111111111111111111111"]["provider_rank"] == 0
    assert by_asset_id["asset:eip155:56:erc20:0x2222222222222222222222222222222222222222"]["provider_rank"] == 1


def _candidate(*, chain_id: str, address: str, symbol: str = "SPARSE") -> DexTokenCandidate:
    return DexTokenCandidate(
        chain_id=chain_id,
        address=address,
        symbol=symbol,
        name=symbol,
        price_usd=None,
        market_cap_usd=None,
        liquidity_usd=None,
        holders=None,
        community_recognized=None,
        raw={"chain_id": chain_id, "tokenContractAddress": address, "tokenSymbol": symbol},
    )


class FakeDexMarket:
    def __init__(self, *, candidates: list[DexTokenCandidate]) -> None:
        self.candidates = candidates

    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]) -> list[DexTokenCandidate]:
        return list(self.candidates)


class FakeRepos:
    def __init__(self) -> None:
        self.registry = FakeRegistry()
        self.identity_evidence = FakeIdentityEvidence()


class FakeRegistry:
    def upsert_chain_asset(self, *, chain_id: str, address: str, observed_at_ms: int, commit: bool = False):
        standard = "erc20" if chain_id.startswith("eip155:") else "token"
        return {
            "asset_id": f"asset:{chain_id}:{standard}:{address}",
            "chain_id": chain_id,
            "address": address,
        }


class FakeIdentityEvidence:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def upsert_identity_evidence(self, **kwargs):
        self.writes.append(kwargs)

    def recompute_current_identity(self, asset_id: str, *, now_ms: int, commit: bool = False):
        return {}
