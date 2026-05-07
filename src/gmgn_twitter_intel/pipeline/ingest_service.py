from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..models import TwitterEvent
from ..storage.asset_repository import AssetRepository
from ..storage.entity_repository import EntityRepository
from ..storage.evidence_repository import EvidenceRepository, event_to_row
from ..storage.postgres_client import transaction
from ..storage.signal_repository import SignalRepository
from .entity_extractor import TextSurface, extract_entities_from_surfaces
from .token_evidence_builder import build_token_evidence
from .token_intent_builder import build_token_intents
from .token_intent_resolver import TokenIntentResolutionDecision, TokenIntentResolver


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    inserted: bool
    enrichment_job_id: str | None = None
    token_intents: list[dict[str, Any]] = field(default_factory=list)
    token_resolutions: list[dict[str, Any]] = field(default_factory=list)


class IngestService:
    def __init__(
        self,
        *,
        evidence: EvidenceRepository,
        entities: EntityRepository,
        signals: SignalRepository,
        enrichment,
        assets: AssetRepository | None = None,
    ):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.assets = assets or AssetRepository(evidence.conn)
        self.intent_resolver = None

    def insert_raw_frame(self, **kwargs) -> bool:
        return self.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        extracted = extract_entities_from_surfaces(_event_surfaces(event))
        with transaction(self.evidence.conn):
            row = event_to_row(event, is_watched=is_watched, now_ms=_now_ms())
            inserted = self.evidence.insert_event_without_commit(row)
            if not inserted:
                return IngestedEvent(
                    event=event,
                    entities=[],
                    alerts=[],
                    token_intents=[],
                    token_resolutions=[],
                    inserted=False,
                )
            self.entities.insert_event_entities(event, extracted, is_watched=is_watched, commit=False)
            evidence_inputs = build_token_evidence(
                event_id=event.event_id,
                entities=extracted,
                token_snapshot=event.token_snapshot,
                created_at_ms=event.received_at_ms,
            )
            from ..storage.intent_resolution_repository import IntentResolutionRepository
            from ..storage.token_evidence_repository import TokenEvidenceRepository
            from ..storage.token_intent_repository import TokenIntentRepository

            token_evidence_repo = TokenEvidenceRepository(self.evidence.conn)
            token_intent_repo = TokenIntentRepository(self.evidence.conn)
            intent_resolution_repo = IntentResolutionRepository(self.evidence.conn)
            token_evidence_repo.insert_many(evidence_inputs, commit=False)
            intent_inputs = build_token_intents(
                event_id=event.event_id,
                evidence=evidence_inputs,
                created_at_ms=event.received_at_ms,
            )
            token_intents = token_intent_repo.insert_many(intent_inputs, commit=False)
            resolver = TokenIntentResolver(assets=self.assets, resolutions=intent_resolution_repo)
            decisions = [
                resolver.resolve(
                    intent,
                    evidence_inputs,
                    decision_time_ms=event.received_at_ms,
                    persist=True,
                    commit=False,
                )
                for intent in intent_inputs
            ]
            token_resolutions = intent_resolution_repo.resolutions_for_event(event.event_id)
            self._insert_gmgn_payload_market_snapshot(event, decisions)
            alerts = self._insert_token_alerts(
                event,
                decisions,
                resolutions=intent_resolution_repo,
                intents_by_id={item.intent_id: item for item in intent_inputs},
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
            alerts=alerts,
            token_intents=token_intents,
            token_resolutions=token_resolutions,
            inserted=True,
            enrichment_job_id=enrichment_job_id,
        )

    def _insert_gmgn_payload_market_snapshot(
        self,
        event: TwitterEvent,
        decisions: list[TokenIntentResolutionDecision],
    ) -> None:
        snapshot = event.token_snapshot
        if snapshot is None:
            return
        if snapshot.price is None and snapshot.market_cap is None:
            return
        for decision in decisions:
            if not decision.primary_venue_id or not decision.asset_id:
                continue
            self.assets.insert_market_snapshot(
                asset_id=decision.asset_id,
                venue_id=decision.primary_venue_id,
                provider="gmgn_payload",
                observed_at_ms=event.received_at_ms,
                price_usd=snapshot.price,
                market_cap_usd=snapshot.market_cap,
                source_payload_hash=_payload_hash(snapshot.raw),
                created_at_ms=event.received_at_ms,
                commit=False,
            )
            return

    def _insert_token_alerts(
        self,
        event: TwitterEvent,
        decisions: list[TokenIntentResolutionDecision],
        *,
        resolutions,
        intents_by_id: dict[str, Any],
        is_watched: bool,
    ) -> list[dict[str, Any]]:
        if not is_watched or not event.author.handle:
            return []
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower()
        for decision in decisions:
            intent = intents_by_id.get(decision.intent_id)
            if decision.asset_id is None:
                continue
            seen_global, seen_author = resolutions.asset_seen_before(
                asset_id=decision.asset_id,
                author_handle=author_handle,
                before_ms=event.received_at_ms,
            )
            alert = self.signals.insert_account_token_alert(
                event_id=event.event_id,
                author_handle=author_handle,
                entity_key=decision.asset_id,
                entity_type="asset",
                normalized_value=_alert_value(intent, decision),
                chain=None,
                token_resolution_status=decision.identity_status,
                is_first_seen_global=not seen_global,
                is_first_seen_by_author=not seen_author,
                received_at_ms=event.received_at_ms,
                commit=False,
            )
            if alert:
                alerts.append(
                    {
                        "alert_type": alert.alert_type,
                        "event_id": alert.event_id,
                        "author_handle": alert.author_handle,
                        "entity_key": alert.entity_key,
                        "entity_type": "asset",
                        "normalized_value": alert.normalized_value,
                        "chain": None,
                        "token_resolution_status": decision.identity_status,
                        "is_first_seen_global": alert.is_first_seen_global,
                        "is_first_seen_by_author": alert.is_first_seen_by_author,
                        "received_at_ms": alert.received_at_ms,
                    }
                )
        return alerts


def _event_text(event: TwitterEvent) -> str | None:
    parts = [event.content.text]
    if event.reference and event.reference.text:
        parts.append(event.reference.text)
    return "\n".join(part for part in parts if part)


def _event_surfaces(event: TwitterEvent) -> list[TextSurface]:
    surfaces = []
    if event.content.text:
        surfaces.append(TextSurface("primary", event.content.text))
    if event.reference and event.reference.text:
        surfaces.append(TextSurface("reference", event.reference.text))
    return surfaces


def _entity_payload(entity) -> dict[str, Any]:
    return {
        "entity_type": entity.entity_type,
        "raw_value": entity.raw_value,
        "normalized_value": entity.normalized_value,
        "chain": entity.chain,
        "token_resolution_status": entity.token_resolution_status,
        "confidence": entity.confidence,
        "source": entity.source,
        "text_surface": entity.text_surface,
        "span_start": entity.span_start,
        "span_end": entity.span_end,
        "sentence_id": entity.sentence_id,
        "local_group_key": entity.local_group_key,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _alert_value(intent: Any, decision: TokenIntentResolutionDecision) -> str:
    value = getattr(intent, "display_symbol", None) or getattr(intent, "address_hint", None)
    return str(value or decision.asset_id)


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
