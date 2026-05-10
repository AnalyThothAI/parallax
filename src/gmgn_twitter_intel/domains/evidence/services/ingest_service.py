from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import PriceObservationRepository, RegistryRepository
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
        enrichment,
        registry: RegistryRepository | None = None,
        price_observations: PriceObservationRepository | None = None,
        token_intent_lookup: TokenIntentLookupRepository | None = None,
    ):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.registry = registry or RegistryRepository(evidence.conn)
        self.price_observations = price_observations or PriceObservationRepository(evidence.conn)
        self.token_intent_lookup = token_intent_lookup or TokenIntentLookupRepository(evidence.conn)

    def insert_raw_frame(self, **kwargs) -> bool:
        return self.evidence.insert_raw_frame(**kwargs)

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
            self._insert_gmgn_payload_price_observation(event, token_resolutions)
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
        return self.registry.upsert_chain_asset(
            chain_id=snapshot.chain,
            address=snapshot.address,
            symbol=snapshot.symbol,
            name=None,
            decimals=None,
            source="gmgn_payload",
            observed_at_ms=event.received_at_ms,
            commit=False,
        )

    def _upsert_chain_intent_registry(self, event: TwitterEvent, intents: list[Any]) -> None:
        for intent in intents:
            chain_hint = getattr(intent, "chain_hint", None)
            address_hint = getattr(intent, "address_hint", None)
            if not chain_hint or not address_hint:
                continue
            self.registry.upsert_chain_asset(
                chain_id=str(chain_hint),
                address=str(address_hint),
                symbol=getattr(intent, "display_symbol", None),
                name=None,
                decimals=None,
                source="tweet_ca",
                observed_at_ms=event.received_at_ms,
                commit=False,
            )

    def _insert_gmgn_payload_price_observation(
        self,
        event: TwitterEvent,
        token_resolutions: list[dict[str, Any]],
    ) -> None:
        snapshot = event.token_snapshot
        if snapshot is None:
            return
        if snapshot.price is None and snapshot.market_cap is None:
            return
        asset = self._upsert_gmgn_payload_registry(event)
        if not asset:
            return
        for resolution in token_resolutions:
            if resolution.get("target_type") != "Asset" or resolution.get("target_id") != asset.get("asset_id"):
                continue
            pricefeed = self.registry.upsert_pricefeed(
                feed_type="dex_token",
                provider="gmgn_payload",
                subject_type="Asset",
                subject_id=str(asset["asset_id"]),
                observed_at_ms=event.received_at_ms,
                chain_id=str(asset["chain_id"]),
                address=str(asset["address"]),
                base_asset_id=str(asset["asset_id"]),
                base_symbol=str(asset["symbol"]) if asset.get("symbol") else snapshot.symbol,
                commit=False,
            )
            self.price_observations.insert_observation(
                provider="gmgn_payload",
                pricefeed_id=str(pricefeed["pricefeed_id"]),
                observed_at_ms=event.received_at_ms,
                subject_type="Asset",
                subject_id=str(asset["asset_id"]),
                price_usd=snapshot.price,
                price_basis="usd" if snapshot.price is not None else "unavailable",
                market_cap_usd=snapshot.market_cap,
                liquidity_usd=_raw_number(snapshot.raw, "liquidity", "liq", "pool_liquidity"),
                volume_24h_usd=_raw_number(snapshot.raw, "volume_24h", "v24h", ("stat", "volume_24h")),
                holders=_raw_int(snapshot.raw, "holder_count", "holders"),
                source_event_id=event.event_id,
                source_intent_id=str(resolution["intent_id"]),
                source_resolution_id=str(resolution["resolution_id"]),
                observation_kind="message_payload",
                event_received_at_ms=event.received_at_ms,
                raw_payload={**snapshot.raw, "payload_hash": _payload_hash(snapshot.raw)},
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
    return str(value or decision.target_id)


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _raw_number(payload: dict[str, Any], *keys: str | tuple[str, str]) -> float | None:
    for key in keys:
        value = _raw_value(payload, key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _raw_int(payload: dict[str, Any], *keys: str | tuple[str, str]) -> int | None:
    value = _raw_number(payload, *keys)
    return int(value) if value is not None else None


def _raw_value(payload: dict[str, Any], key: str | tuple[str, str]) -> Any:
    if isinstance(key, tuple):
        node: Any = payload
        for part in key:
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        return node
    return payload.get(key)
