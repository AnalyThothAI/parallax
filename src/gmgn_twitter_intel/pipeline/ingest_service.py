from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..models import TwitterEvent
from ..storage.entity_repository import EntityRepository
from ..storage.evidence_repository import EvidenceRepository, event_to_row
from ..storage.postgres_client import transaction
from ..storage.signal_repository import SignalRepository
from .entity_extractor import extract_entities
from .signal_builder import SignalBuilder
from .token_identity_resolver import TokenIdentityResolver


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    token_attributions: list[dict[str, Any]]
    inserted: bool
    enrichment_job_id: str | None = None


class IngestService:
    def __init__(
        self,
        *,
        evidence: EvidenceRepository,
        entities: EntityRepository,
        signals: SignalRepository,
        enrichment,
        tokens,
        market_observations=None,
    ):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.tokens = tokens
        self.signal_builder = SignalBuilder(
            signals,
            tokens,
            market_observations=market_observations,
            commit=False,
        )
        self.token_resolver = TokenIdentityResolver(tokens)

    def insert_raw_frame(self, **kwargs) -> bool:
        return self.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        extracted = extract_entities(_event_text(event))
        with transaction(self.evidence.conn):
            row = event_to_row(event, is_watched=is_watched, now_ms=_now_ms())
            inserted = self.evidence.insert_event_without_commit(row)
            if not inserted:
                return IngestedEvent(event=event, entities=[], alerts=[], token_attributions=[], inserted=False)
            self.entities.insert_event_entities(event, extracted, is_watched=is_watched, commit=False)
            token_mentions = self.token_resolver.resolve_event_mentions(event, extracted, commit=False)
            signal_result = self.signal_builder.build_for_event(
                event,
                token_mentions,
                is_watched=is_watched,
            )
            enrichment_job_id = None
            if is_watched and _event_text(event):
                enrichment_job_id = self.enrichment.enqueue_watched_event(
                    event_id=event.event_id,
                    received_at_ms=event.received_at_ms,
                    commit=False,
                )
        return IngestedEvent(
            event=event,
            entities=[_entity_payload(entity) for entity in extracted],
            alerts=signal_result.alerts,
            token_attributions=signal_result.token_attributions,
            inserted=True,
            enrichment_job_id=enrichment_job_id,
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
