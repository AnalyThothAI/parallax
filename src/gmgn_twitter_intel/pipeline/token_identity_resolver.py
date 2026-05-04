from __future__ import annotations

from dataclasses import dataclass

from ..models import TwitterEvent
from ..storage.token_repository import TokenRepository
from .entity_extractor import ExtractedEntity


@dataclass(frozen=True, slots=True)
class TokenMention:
    identity_key: str
    token_id: str | None
    identity_status: str
    chain: str | None
    address: str | None
    symbol: str
    source: str


class TokenIdentityResolver:
    def __init__(self, tokens: TokenRepository):
        self.tokens = tokens

    def resolve_event_mentions(
        self,
        event: TwitterEvent,
        entities: list[ExtractedEntity],
        *,
        commit: bool = False,
    ) -> list[TokenMention]:
        if event.token_snapshot is not None:
            identity = self.tokens.upsert_snapshot(
                event_id=event.event_id,
                snapshot=event.token_snapshot,
                received_at_ms=event.received_at_ms,
                source_channel=event.source.channel,
                commit=commit,
            )
            return [_mention_from_identity(identity, source="gmgn_token_payload")]

        ca_entities = [entity for entity in entities if entity.entity_type == "ca"]
        symbol_entities = [entity for entity in entities if entity.entity_type == "symbol"]
        symbol = symbol_entities[0].normalized_value if len(symbol_entities) == 1 else None
        if ca_entities:
            return [
                _mention_from_identity(
                    self.tokens.upsert_ca(
                        event_id=event.event_id,
                        chain=entity.chain or "unknown",
                        address=entity.normalized_value,
                        symbol=symbol,
                        received_at_ms=event.received_at_ms,
                        commit=commit,
                    ),
                    source=entity.source,
                )
                for entity in ca_entities
            ]

        mentions: list[TokenMention] = []
        for entity in symbol_entities:
            identity = self.tokens.resolve_symbol(entity.normalized_value)
            status = "symbol_only" if identity.candidate_token_ids else identity.identity_status
            mentions.append(
                TokenMention(
                    identity_key=f"symbol:{entity.normalized_value}",
                    token_id=None,
                    identity_status=status,
                    chain=None,
                    address=None,
                    symbol=entity.normalized_value,
                    source=entity.source,
                )
            )
        return mentions


def _mention_from_identity(identity, *, source: str) -> TokenMention:
    symbol = identity.symbol or identity.address or identity.token_id or "UNKNOWN"
    return TokenMention(
        identity_key=identity.token_id or f"symbol:{symbol}",
        token_id=identity.token_id,
        identity_status=identity.identity_status,
        chain=identity.chain,
        address=identity.address,
        symbol=symbol,
        source=source,
    )
