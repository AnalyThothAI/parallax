from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Any

from ..models import TwitterEvent
from ..storage.entity_repository import EntityRepository
from ..storage.evidence_repository import EvidenceRepository, event_to_row
from ..storage.signal_repository import SignalRepository
from ..storage.sqlite_client import transaction
from .entity_extractor import extract_entities
from .signal_builder import SignalBuilder


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    inserted: bool


class IngestService:
    def __init__(
        self,
        *,
        evidence: EvidenceRepository,
        entities: EntityRepository,
        signals: SignalRepository,
        watch_keywords: tuple[str, ...],
    ):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.watch_keywords = watch_keywords
        self.signal_builder = SignalBuilder(signals, commit=False)
        self._lock = RLock()

    def insert_raw_frame(self, **kwargs) -> bool:
        with self._lock:
            return self.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        with self._lock:
            extracted = extract_entities(_event_text(event), watch_keywords=self.watch_keywords)
            with transaction(self.evidence.conn):
                row = event_to_row(event, is_watched=is_watched, now_ms=_now_ms())
                inserted = self.evidence.insert_event_without_commit(row)
                if not inserted:
                    return IngestedEvent(event=event, entities=[], alerts=[], inserted=False)
                self.entities.insert_event_entities(event, extracted, is_watched=is_watched, commit=False)
                signal_result = self.signal_builder.build_for_event(event, extracted, is_watched=is_watched)
            return IngestedEvent(
                event=event,
                entities=[_entity_payload(entity) for entity in extracted],
                alerts=signal_result.alerts,
                inserted=True,
            )


def _event_text(event: TwitterEvent) -> str | None:
    parts = [event.content.text]
    if event.reference and event.reference.text:
        parts.append(event.reference.text)
    return "\n".join(part for part in parts if part)


def _entity_payload(entity) -> dict[str, Any]:
    return {
        "entity_type": entity.entity_type,
        "raw_value": entity.raw_value,
        "normalized_value": entity.normalized_value,
        "chain": entity.chain,
        "token_resolution_status": entity.token_resolution_status,
        "confidence": entity.confidence,
        "source": entity.source,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)
