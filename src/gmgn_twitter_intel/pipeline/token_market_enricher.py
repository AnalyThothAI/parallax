from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from loguru import logger

from ..market.gmgn_openapi_client import GmgnOpenApiClient, GmgnOpenApiError, GmgnTokenInfo
from ..storage.token_repository import TokenRepository


class TokenMentionLike(Protocol):
    token_id: str | None
    chain: str | None
    address: str | None


class TokenMarketEnricher:
    def __init__(
        self,
        *,
        tokens: TokenRepository,
        client: GmgnOpenApiClient,
        evm_candidate_chains: tuple[str, ...] = ("base", "bsc", "eth"),
    ):
        self.tokens = tokens
        self.client = client
        self.evm_candidate_chains = evm_candidate_chains

    def enrich_mentions(
        self,
        *,
        event_id: str,
        mentions: list[TokenMentionLike],
        received_at_ms: int,
        source_channel: str,
        commit: bool = True,
    ) -> int:
        _, enriched = self.resolve_and_enrich_mentions(
            event_id=event_id,
            mentions=mentions,
            received_at_ms=received_at_ms,
            source_channel=source_channel,
            commit=commit,
        )
        return enriched

    def resolve_and_enrich_mentions(
        self,
        *,
        event_id: str,
        mentions: list[Any],
        received_at_ms: int,
        source_channel: str,
        commit: bool = True,
    ) -> tuple[list[Any], int]:
        enriched = 0
        resolved_mentions: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for mention in mentions:
            if not mention.chain or not mention.address:
                resolved_mentions.append(mention)
                continue
            key = (mention.chain.lower(), mention.address)
            if key in seen:
                resolved_mentions.append(mention)
                continue
            seen.add(key)
            info = self._lookup_candidates(chain=mention.chain, address=mention.address)
            if info is None:
                resolved_mentions.append(mention)
                continue
            self.tokens.upsert_openapi_token_info(
                event_id=event_id,
                info=info,
                received_at_ms=received_at_ms,
                source_channel=source_channel,
                commit=False,
            )
            resolved_mentions.append(_mention_from_token_info(mention, info))
            enriched += 1
        if commit:
            self.tokens.conn.commit()
        return resolved_mentions, enriched

    def _lookup_candidates(self, *, chain: str, address: str) -> GmgnTokenInfo | None:
        for candidate_chain in self._candidate_chains(chain):
            info = self._lookup(chain=candidate_chain, address=address)
            if info is not None:
                return info
        return None

    def _candidate_chains(self, chain: str) -> list[str]:
        normalized = chain.lower()
        if normalized not in {"eth", "evm", "evm_unknown"}:
            return [chain]
        candidates = [chain, *self.evm_candidate_chains]
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def _lookup(self, *, chain: str, address: str) -> GmgnTokenInfo | None:
        try:
            return self.client.get_token_info(chain=chain, address=address)
        except GmgnOpenApiError as exc:
            logger.debug(f"GMGN token info lookup failed chain={chain} address={address}: {exc}")
            return None
        except Exception as exc:
            logger.warning(f"GMGN token info lookup error chain={chain} address={address}: {exc}")
            return None


def no_token_market_enricher() -> Any:
    return None


def _mention_from_token_info(mention: Any, info: GmgnTokenInfo) -> Any:
    token_id = f"token:{info.chain}:{info.address}"
    try:
        return replace(
            mention,
            identity_key=token_id,
            token_id=token_id,
            identity_status="resolved_ca",
            chain=info.chain,
            address=info.address,
            symbol=info.symbol,
            source="gmgn_openapi_token_info",
        )
    except TypeError:
        return mention
