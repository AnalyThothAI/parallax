from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gmgn_twitter_intel.integrations.coingecko.search_client import CoingeckoSearchHit
from gmgn_twitter_intel.integrations.okx.chains import OKX_CHAIN_TO_CHAIN_INDEX
from gmgn_twitter_intel.integrations.okx.models import OkxDexTokenCandidate
from scripts.audit_dedup.candidates import AssetCandidate


class OkxSearchProto(Protocol):
    def search_tokens(self, *, query: str, chain_indexes) -> list[OkxDexTokenCandidate]: ...


class CoingeckoSearchProto(Protocol):
    def search(self, *, symbol: str, chain: str) -> list[CoingeckoSearchHit]: ...


@dataclass(frozen=True, slots=True)
class ExternalArbiterResult:
    winner_id: str | None
    source: str  # "okx_dex" | "coingecko" | "none" | "unsupported_chain"
    external_address: str | None


def _normalize_addr(address: str | None) -> str:
    if address is None:
        return ""
    return address.lower()


class ExternalArbiter:
    def __init__(self, *, okx_client: OkxSearchProto, coingecko_client: CoingeckoSearchProto) -> None:
        self._okx = okx_client
        self._cg = coingecko_client

    def arbitrate(
        self,
        *,
        chain: str,
        symbol: str,
        candidates: tuple[AssetCandidate, ...],
    ) -> ExternalArbiterResult:
        chain_index = OKX_CHAIN_TO_CHAIN_INDEX.get(chain)
        if chain_index is None:
            return ExternalArbiterResult(winner_id=None, source="unsupported_chain", external_address=None)

        # Map normalized address -> (asset_id, original_address)
        addr_map: dict[str, tuple[str, str]] = {_normalize_addr(c.address): (c.asset_id, c.address) for c in candidates}

        for okx_hit in self._okx.search_tokens(query=symbol, chain_indexes=[chain_index]):
            normalized = _normalize_addr(okx_hit.address)
            if normalized in addr_map:
                asset_id, original_addr = addr_map[normalized]
                return ExternalArbiterResult(
                    winner_id=asset_id,
                    source="okx_dex",
                    external_address=original_addr,
                )

        for cg_hit in self._cg.search(symbol=symbol, chain=chain):
            normalized = _normalize_addr(cg_hit.address)
            if normalized in addr_map:
                asset_id, original_addr = addr_map[normalized]
                return ExternalArbiterResult(
                    winner_id=asset_id,
                    source="coingecko",
                    external_address=original_addr,
                )

        return ExternalArbiterResult(winner_id=None, source="none", external_address=None)
