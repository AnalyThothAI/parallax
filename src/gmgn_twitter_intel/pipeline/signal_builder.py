from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..models import TwitterEvent
from ..storage.signal_repository import SignalRepository
from .entity_extractor import ExtractedEntity, entity_key

WINDOWS_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


@dataclass(frozen=True, slots=True)
class SignalBuildResult:
    alerts: list[dict[str, Any]]


class SignalBuilder:
    def __init__(self, repository: SignalRepository, *, commit: bool = True):
        self.repository = repository
        self.commit = commit

    def build_for_event(
        self,
        event: TwitterEvent,
        entities: list[ExtractedEntity],
        *,
        is_watched: bool,
    ) -> SignalBuildResult:
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower() if event.author.handle else None
        for entity in entities:
            if entity.entity_type in {"ca", "symbol"}:
                key = entity_key(entity)
                seen_global, seen_author = self.repository.token_seen_before(
                    entity_key=key,
                    author_handle=author_handle,
                    before_ms=event.received_at_ms,
                )
                if is_watched and author_handle:
                    alert = self.repository.insert_account_token_alert(
                        event_id=event.event_id,
                        author_handle=author_handle,
                        entity_key=key,
                        entity_type=entity.entity_type,
                        normalized_value=entity.normalized_value,
                        chain=entity.chain,
                        token_resolution_status=entity.token_resolution_status,
                        is_first_seen_global=not seen_global,
                        is_first_seen_by_author=not seen_author,
                        received_at_ms=event.received_at_ms,
                        commit=self.commit,
                    )
                    if alert:
                        alerts.append(asdict(alert))
                self._upsert_token_windows(event, entity, key, is_watched=is_watched)
        return SignalBuildResult(alerts=alerts)

    def _upsert_token_windows(
        self,
        event: TwitterEvent,
        entity: ExtractedEntity,
        key: str,
        *,
        is_watched: bool,
    ) -> None:
        for window, size_ms in WINDOWS_MS.items():
            start_ms = (event.received_at_ms // size_ms) * size_ms
            self.repository.upsert_token_window(
                entity_key=key,
                entity_type=entity.entity_type,
                normalized_value=entity.normalized_value,
                chain=entity.chain,
                window=window,
                window_start_ms=start_ms,
                window_end_ms=start_ms + size_ms,
                event_id=event.event_id,
                author_handle=event.author.handle.lower() if event.author.handle else None,
                author_followers=event.author.followers,
                is_watched=is_watched,
                commit=self.commit,
            )
