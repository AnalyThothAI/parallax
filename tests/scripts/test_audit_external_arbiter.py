from __future__ import annotations

from gmgn_twitter_intel.integrations.coingecko.search_client import CoingeckoSearchHit
from gmgn_twitter_intel.integrations.okx.models import OkxDexTokenCandidate
from scripts.audit_dedup.candidates import AssetCandidate
from scripts.audit_dedup.external_arbiter import (
    ExternalArbiter,
    ExternalArbiterResult,
)


class _StubOkx:
    def __init__(self, returns: list[OkxDexTokenCandidate]) -> None:
        self.returns = returns
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def search_tokens(self, *, query: str, chain_indexes):
        self.calls.append((query, tuple(chain_indexes)))
        return list(self.returns)


class _StubCg:
    def __init__(self, returns: list[CoingeckoSearchHit]) -> None:
        self.returns = returns
        self.calls: list[tuple[str, str]] = []

    def search(self, *, symbol: str, chain: str):
        self.calls.append((symbol, chain))
        return list(self.returns)


def _c(asset_id: str, address: str, *, holders=10, liq=1.0) -> AssetCandidate:
    return AssetCandidate(
        asset_id=asset_id,
        chain="solana",
        address=address,
        first_seen_at_ms=0,
        holders=holders,
        liquidity_usd=liq,
        market_cap_usd=None,
        volume_24h_usd=None,
        observed_at_ms=None,
    )


def _okx(address: str) -> OkxDexTokenCandidate:
    return OkxDexTokenCandidate(
        chain_index="501",
        chain="solana",
        address=address,
        symbol="TROLL",
        name=None,
        price_usd=None,
        market_cap_usd=None,
        liquidity_usd=None,
        holders=None,
        community_recognized=None,
        raw={},
    )


def test_okx_hit_short_circuits() -> None:
    okx = _StubOkx(returns=[_okx("AAA"), _okx("BBB")])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"), _c("asset:2", "ZZZ"))
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(
        winner_id="asset:1",
        source="okx_dex",
        external_address="AAA",
    )
    assert okx.calls == [("TROLL", ("501",))]
    assert cg.calls == []  # short-circuit


def test_okx_miss_falls_to_coingecko() -> None:
    okx = _StubOkx(returns=[_okx("NOPE")])  # not in candidates
    cg = _StubCg(returns=[CoingeckoSearchHit(coin_id="t", symbol="troll", chain="solana", address="bbb")])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"), _c("asset:2", "BBB"))
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id="asset:2", source="coingecko", external_address="BBB")
    assert cg.calls == [("TROLL", "solana")]


def test_no_hit_anywhere_returns_group_drop() -> None:
    okx = _StubOkx(returns=[])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"),)
    result = arb.arbitrate(chain="solana", symbol="TROLL", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id=None, source="none", external_address=None)


def test_unknown_chain_skips_external_entirely() -> None:
    okx = _StubOkx(returns=[_okx("AAA")])
    cg = _StubCg(returns=[])
    arb = ExternalArbiter(okx_client=okx, coingecko_client=cg)

    candidates = (_c("asset:1", "AAA"),)
    result = arb.arbitrate(chain="monad", symbol="X", candidates=candidates)

    assert result == ExternalArbiterResult(winner_id=None, source="unsupported_chain", external_address=None)
    assert okx.calls == []
    assert cg.calls == []
