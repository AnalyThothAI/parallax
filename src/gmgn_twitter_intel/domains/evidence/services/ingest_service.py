from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import (
    CONFIDENCE_MENTION_ONLY,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_TWEET_CONTRACT_MENTION,
    IdentityEvidenceRepository,
    RegistryRepository,
)
from gmgn_twitter_intel.domains.evidence.interfaces import (
    TextSurface,
    TwitterEvent,
    event_to_row,
    extract_entities_from_surfaces,
)
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.ingestion.interfaces import IngestedEvent
from gmgn_twitter_intel.domains.social_enrichment.interfaces import watched_social_event_priority
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    IntentResolutionRepository,
    SignalRepository,
    TokenEvidenceRepository,
    TokenIntentLookupRepository,
    TokenIntentRepository,
    TokenIntentResolutionDecision,
    TokenIntentResolver,
    build_token_evidence,
    build_token_intents,
)


class IngestService:
    def __init__(
        self,
        *,
        evidence: EvidenceRepository,
        entities: EntityRepository,
        signals: SignalRepository,
        enrichment: Any,
        registry: RegistryRepository | None = None,
        identity_evidence: IdentityEvidenceRepository | None = None,
        token_intent_lookup: TokenIntentLookupRepository | None = None,
    ) -> None:
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.registry = registry or RegistryRepository(evidence.conn)
        self.identity_evidence = identity_evidence or IdentityEvidenceRepository(evidence.conn)
        self.token_intent_lookup = token_intent_lookup or TokenIntentLookupRepository(evidence.conn)

    def insert_raw_frame(self, **kwargs: Any) -> bool:
        result: bool = self.evidence.insert_raw_frame(**kwargs)
        return result

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        extracted = extract_entities_from_surfaces(_event_surfaces(event))
        with self.evidence.unit_of_work():
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
            token_evidence_repo = TokenEvidenceRepository(self.evidence.conn)
            token_intent_repo = TokenIntentRepository(self.evidence.conn)
            intent_resolution_repo = IntentResolutionRepository(self.evidence.conn)
            self._upsert_gmgn_payload_registry(event)
            token_evidence_repo.insert_many(evidence_inputs, commit=False)
            intent_inputs = build_token_intents(
                event_id=event.event_id,
                evidence=evidence_inputs,
                created_at_ms=event.received_at_ms,
            )
            token_intents = token_intent_repo.insert_many(intent_inputs, commit=False)
            self._upsert_chain_intent_registry(event, intent_inputs)
            resolver = TokenIntentResolver(
                registry=self.registry,
                resolutions=intent_resolution_repo,
            )
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
            for decision in decisions:
                intent = next((item for item in intent_inputs if item.intent_id == decision.intent_id), None)
                self.token_intent_lookup.replace_lookup_keys(
                    intent_id=decision.intent_id,
                    event_id=decision.event_id,
                    keys=decision.lookup_keys,
                    source_evidence_id=getattr(intent, "primary_evidence_id", None),
                    created_at_ms=event.received_at_ms,
                    commit=False,
                )
            token_resolutions = intent_resolution_repo.resolutions_for_event(event.event_id)
            alerts = self._insert_token_alerts(
                event,
                decisions,
                resolutions=intent_resolution_repo,
                intents_by_id={item.intent_id: item for item in intent_inputs},
                is_watched=is_watched,
            )
            enrichment_job_id = None
            enrichment_priority = watched_social_event_priority(
                event=event,
                entities=extracted,
                token_resolutions=token_resolutions,
            )
            if is_watched and enrichment_priority is not None:
                enrichment_job_id = self.enrichment.enqueue_watched_event(
                    event_id=event.event_id,
                    received_at_ms=event.received_at_ms,
                    priority=enrichment_priority,
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

    def _upsert_gmgn_payload_registry(self, event: TwitterEvent) -> dict[str, Any] | None:
        snapshot = event.token_snapshot
        if snapshot is None:
            return None
        if not snapshot.address or not snapshot.chain:
            return None
        asset = self.registry.upsert_chain_asset(
            chain_id=snapshot.chain,
            address=snapshot.address,
            observed_at_ms=event.received_at_ms,
            commit=False,
        )
        self.identity_evidence.upsert_identity_evidence(
            asset_id=str(asset["asset_id"]),
            evidence_kind=EVIDENCE_GMGN_PAYLOAD_EXACT,
            provider="gmgn",
            lookup_mode="provider_payload",
            chain_id=str(asset["chain_id"]),
            address=str(asset["address"]),
            symbol=snapshot.symbol,
            name=None,
            decimals=None,
            confidence=CONFIDENCE_PROVIDER_EXACT,
            source_event_id=event.event_id,
            raw_payload={**snapshot.raw, "payload_hash": _payload_hash(snapshot.raw)},
            observed_at_ms=event.received_at_ms,
            commit=False,
        )
        self.identity_evidence.recompute_current_identity(
            str(asset["asset_id"]),
            now_ms=event.received_at_ms,
            commit=False,
        )
        return asset

    def _upsert_chain_intent_registry(self, event: TwitterEvent, intents: list[Any]) -> None:
        for intent in intents:
            chain_hint = getattr(intent, "chain_hint", None)
            address_hint = getattr(intent, "address_hint", None)
            if not chain_hint or not address_hint:
                continue
            asset = self.registry.upsert_chain_asset(
                chain_id=str(chain_hint),
                address=str(address_hint),
                observed_at_ms=event.received_at_ms,
                commit=False,
            )
            self.identity_evidence.upsert_identity_evidence(
                asset_id=str(asset["asset_id"]),
                evidence_kind=EVIDENCE_TWEET_CONTRACT_MENTION,
                provider="twitter",
                lookup_mode="tweet_mention",
                chain_id=str(asset["chain_id"]),
                address=str(asset["address"]),
                symbol=getattr(intent, "display_symbol", None),
                name=None,
                decimals=None,
                confidence=CONFIDENCE_MENTION_ONLY,
                source_event_id=event.event_id,
                source_intent_id=getattr(intent, "intent_id", None),
                observed_at_ms=event.received_at_ms,
                commit=False,
            )
            self.identity_evidence.recompute_current_identity(
                str(asset["asset_id"]),
                now_ms=event.received_at_ms,
                commit=False,
            )

    def _insert_token_alerts(
        self,
        event: TwitterEvent,
        decisions: list[TokenIntentResolutionDecision],
        *,
        resolutions: Any,
        intents_by_id: dict[str, Any],
        is_watched: bool,
    ) -> list[dict[str, Any]]:
        if not is_watched or not event.author.handle:
            return []
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower()
        for decision in decisions:
            intent = intents_by_id.get(decision.intent_id)
            if decision.target_type is None or decision.target_id is None:
                continue
            seen_global, seen_author = resolutions.target_seen_before(
                target_type=decision.target_type,
                target_id=decision.target_id,
                author_handle=author_handle,
                before_ms=event.received_at_ms,
            )
            alert = self.signals.insert_account_token_alert(
                event_id=event.event_id,
                author_handle=author_handle,
                entity_key=decision.target_id,
                entity_type=decision.target_type,
                normalized_value=_alert_value(intent, decision),
                chain=None,
                token_resolution_status=decision.resolution_status,
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
                        "entity_type": decision.target_type,
                        "normalized_value": alert.normalized_value,
                        "chain": None,
                        "token_resolution_status": decision.resolution_status,
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


def _entity_payload(entity: Any) -> dict[str, Any]:
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
    return str(value or decision.target_id)


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
