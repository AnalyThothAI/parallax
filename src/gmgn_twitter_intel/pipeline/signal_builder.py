from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..models import TwitterEvent
from ..storage.signal_repository import SignalRepository
from .token_attribution import TokenAttributionBuilder
from .token_identity_resolver import TokenMention


@dataclass(frozen=True, slots=True)
class SignalBuildResult:
    alerts: list[dict[str, Any]]


class SignalBuilder:
    def __init__(self, repository: SignalRepository, tokens, *, commit: bool = True):
        self.repository = repository
        self.tokens = tokens
        self.commit = commit
        self.attribution_builder = TokenAttributionBuilder(signals=repository, tokens=tokens)

    def build_for_event(
        self,
        event: TwitterEvent,
        token_mentions: list[TokenMention],
        *,
        is_watched: bool,
    ) -> SignalBuildResult:
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower() if event.author.handle else None
        self.repository.insert_event_token_mentions(
            event_id=event.event_id,
            token_mentions=token_mentions,
            received_at_ms=event.received_at_ms,
            author_handle=author_handle,
            author_followers=event.author.followers,
            is_watched=is_watched,
            commit=self.commit,
        )
        mention_rows = self.repository.token_mentions_for_event(event.event_id)
        self.repository.replace_token_attributions(
            mention_ids=[str(row["mention_id"]) for row in mention_rows],
            attributions=self.attribution_builder.build_for_rows(mention_rows),
            commit=self.commit,
        )
        for symbol in _symbols_to_rebuild(mention_rows):
            self.attribution_builder.rebuild_symbol(symbol, commit=self.commit)
        for mention in token_mentions:
            seen_global, seen_author = self.repository.token_seen_before(
                identity_key=mention.identity_key,
                author_handle=author_handle,
                before_ms=event.received_at_ms,
            )
            if is_watched and author_handle:
                alert = self.repository.insert_account_token_alert(
                    event_id=event.event_id,
                    author_handle=author_handle,
                    entity_key=mention.identity_key,
                    entity_type="token",
                    normalized_value=mention.symbol,
                    chain=mention.chain,
                    token_resolution_status=mention.identity_status,
                    is_first_seen_global=not seen_global,
                    is_first_seen_by_author=not seen_author,
                    received_at_ms=event.received_at_ms,
                    commit=self.commit,
                )
                if alert:
                    alerts.append(asdict(alert))
        return SignalBuildResult(alerts=alerts)


def _symbols_to_rebuild(mention_rows: list[dict[str, Any]]) -> set[str]:
    symbols = set()
    for row in mention_rows:
        if row.get("token_id") and row.get("symbol"):
            symbols.add(str(row["symbol"]))
    return symbols
