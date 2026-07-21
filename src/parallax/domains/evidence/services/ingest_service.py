from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from parallax.domains.asset_market.interfaces import (
    CONFIDENCE_MENTION_ONLY,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_TWEET_CONTRACT_MENTION,
    CaptureResult,
    DiscoveryRepository,
    EnrichedEventCapture,
    EnrichedEventRepository,
    EventAnchorBackfillJobRepository,
    IdentityEvidenceRepository,
    MarketTick,
    MarketTickCurrentDirtyTargetRepository,
    MarketTickPersistenceService,
    MarketTickRepository,
    RegistryRepository,
)
from parallax.domains.evidence.interfaces import (
    TextSurface,
    TwitterEvent,
    event_to_row,
    extract_entities_from_surfaces,
)
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.ingestion.interfaces import IngestedEvent
from parallax.domains.token_intel.interfaces import (
    IntentResolutionRepository,
    SignalRepository,
    TokenEvidenceRepository,
    TokenIntentInput,
    TokenIntentLookupRepository,
    TokenIntentRepository,
    TokenIntentResolutionDecision,
    TokenIntentResolver,
    TokenRadarSourceDirtyEventRepository,
    build_token_evidence,
    build_token_intents,
    token_intent_resolution_id,
)


@dataclass(frozen=True, slots=True)
class PreparedIngest:
    raw_event: TwitterEvent
    event_id: str
    event_ms: int
    event_row: dict[str, Any]
    entities: list[Any]
    evidence_inputs: list[Any]
    intents: list[TokenIntentInput]
    is_watched: bool


IngestCaptureInput = CaptureResult | EnrichedEventCapture


class IngestService:
    def __init__(
        self,
        *,
        evidence: EvidenceRepository,
        entities: EntityRepository,
        signals: SignalRepository,
        registry: RegistryRepository,
        identity_evidence: IdentityEvidenceRepository,
        token_intent_lookup: TokenIntentLookupRepository,
        token_evidence: TokenEvidenceRepository,
        token_intents: TokenIntentRepository,
        intent_resolutions: IntentResolutionRepository,
        discovery: DiscoveryRepository,
        market_ticks: MarketTickRepository,
        market_tick_current_dirty_targets: MarketTickCurrentDirtyTargetRepository,
        enriched_events: EnrichedEventRepository,
        event_anchor_jobs: EventAnchorBackfillJobRepository,
        token_radar_source_dirty_events: TokenRadarSourceDirtyEventRepository,
        event_anchor_active_window_ms: int,
    ) -> None:
        self.conn = evidence.conn
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.registry = registry
        self.identity_evidence = identity_evidence
        self.token_intent_lookup = token_intent_lookup
        self.token_evidence = token_evidence
        self.token_intents = token_intents
        self.intent_resolutions = intent_resolutions
        self.discovery = discovery
        self.market_ticks = market_ticks
        self.market_tick_current_dirty_targets = market_tick_current_dirty_targets
        self.enriched_events = enriched_events
        self.event_anchor_jobs = event_anchor_jobs
        self.token_radar_source_dirty_events = token_radar_source_dirty_events
        self.event_anchor_active_window_ms = require_event_anchor_active_window_ms(event_anchor_active_window_ms)

    def require_transaction(self, *, operation: str) -> None:
        self.evidence.require_transaction(operation=operation)

    def insert_raw_frame(self, **kwargs: Any) -> bool:
        result: bool = self.evidence.insert_raw_frame(**kwargs)
        return result

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        prepared = self.prepare_event(event, is_watched=is_watched)
        # Registry preparation participates in the same unit of work as the
        # material event facts.  Otherwise an autocommit connection can leave
        # orphan registry assets when a later event write fails.
        with self.evidence.unit_of_work():
            if self.event_already_exists(prepared):
                return self.duplicate_result(prepared)
            self.prepare_registry_for_resolution(prepared)
            decisions = self.resolve_prepared(prepared, persist=False)
            captures = [
                _unavailable_capture(prepared, market_resolution, reason="missing_capture_service")
                for decision in decisions
                if (market_resolution := self.market_resolution_for_decision(decision)) is not None
            ]
            return self.commit_prepared_event(prepared, resolutions=decisions, captures=captures)

    @staticmethod
    def prepare_event(event: TwitterEvent, *, is_watched: bool) -> PreparedIngest:
        extracted = extract_entities_from_surfaces(_event_surfaces(event))
        evidence_inputs = build_token_evidence(
            event_id=event.event_id,
            entities=extracted,
            token_snapshot=event.token_snapshot,
            created_at_ms=event.received_at_ms,
        )
        intent_inputs = build_token_intents(
            event_id=event.event_id,
            evidence=evidence_inputs,
            created_at_ms=event.received_at_ms,
        )
        return PreparedIngest(
            raw_event=event,
            event_id=event.event_id,
            event_ms=event.received_at_ms,
            event_row=event_to_row(event, is_watched=is_watched, now_ms=_now_ms()),
            entities=extracted,
            evidence_inputs=evidence_inputs,
            intents=intent_inputs,
            is_watched=is_watched,
        )

    def event_already_exists(self, prepared: PreparedIngest) -> bool:
        return self.evidence.event_exists(
            event_id=prepared.event_id,
            logical_dedup_key=str(prepared.event_row["logical_dedup_key"]),
        )

    def duplicate_result(self, prepared: PreparedIngest) -> IngestedEvent:
        return IngestedEvent(
            event=prepared.raw_event,
            entities=[],
            alerts=[],
            token_intents=[],
            token_resolutions=[],
            inserted=False,
        )

    def prepare_registry_for_resolution(self, prepared: PreparedIngest) -> None:
        self._upsert_gmgn_payload_registry_asset(prepared.raw_event)
        self._upsert_chain_intent_registry_assets(prepared.raw_event, prepared.intents)

    def resolve_prepared(
        self,
        prepared: PreparedIngest,
        *,
        persist: bool = False,
    ) -> list[TokenIntentResolutionDecision]:
        resolver = TokenIntentResolver(
            registry=self.registry,
            resolutions=self.intent_resolutions,
        )
        return [
            resolver.resolve(
                self._intent_with_prepared_chain_hint(intent),
                prepared.evidence_inputs,
                decision_time_ms=prepared.event_ms,
                persist=persist,
            )
            for intent in prepared.intents
        ]

    def commit_prepared_event(
        self,
        prepared: PreparedIngest,
        *,
        resolutions: list[TokenIntentResolutionDecision],
        captures: Sequence[IngestCaptureInput],
    ) -> IngestedEvent:
        capture_results = [_require_capture_result(item) for item in captures]
        with self.evidence.unit_of_work():
            inserted = self.evidence.insert_event_without_commit(prepared.event_row)
            if not inserted:
                return self.duplicate_result(prepared)
            self.entities.insert_event_entities(
                prepared.raw_event,
                prepared.entities,
                is_watched=prepared.is_watched,
                commit=False,
            )
            self.token_evidence.insert_many(prepared.evidence_inputs, commit=False)
            token_intents = self.token_intents.insert_many(prepared.intents, commit=False)
            self._upsert_gmgn_payload_registry(prepared.raw_event)
            self._upsert_chain_intent_registry(prepared.raw_event, prepared.intents)
            for decision in resolutions:
                _require_resolution_decision(decision)
                self.intent_resolutions.insert_resolution(decision, commit=False)
                decision_intent_id = decision.intent_id
                intent = _token_intent_by_id(prepared.intents, decision_intent_id)
                self.token_intent_lookup.replace_lookup_keys(
                    intent_id=decision_intent_id,
                    event_id=decision.event_id,
                    keys=decision.lookup_keys,
                    source_evidence_id=intent.primary_evidence_id,
                    created_at_ms=prepared.event_ms,
                    commit=False,
                )
            discovery_lookup_keys = _discovery_lookup_keys_for_resolutions(resolutions)
            if discovery_lookup_keys:
                self.discovery.enqueue_lookup_keys(
                    discovery_lookup_keys,
                    reason="intent_resolution_unresolved",
                    now_ms=prepared.event_ms,
                    commit=False,
                )
            source_dirty_events = _source_dirty_events_for_resolutions(resolutions)
            if source_dirty_events:
                self.token_radar_source_dirty_events.enqueue_events(
                    source_dirty_events,
                    reason="ingest_resolution",
                    now_ms=prepared.event_ms,
                    commit=False,
                )
            capture_ticks = [item.tick for item in capture_results if item.tick is not None]
            if capture_ticks:
                MarketTickPersistenceService(self).insert_ticks_and_enqueue_current_dirty(
                    capture_ticks,
                    reason="event_capture_tick_inserted",
                    now_ms=prepared.event_ms,
                )
            for item in capture_results:
                self.enriched_events.insert_capture(item.capture)
                self.event_anchor_jobs.enqueue_for_capture(
                    item.capture,
                    active_window_ms=self.event_anchor_active_window_ms,
                )
            token_resolutions = self.intent_resolutions.resolutions_for_event(prepared.event_id)
            alerts = self._insert_token_alerts(
                prepared.raw_event,
                resolutions,
                resolutions=self.intent_resolutions,
                intents_by_id={item.intent_id: item for item in prepared.intents},
                is_watched=prepared.is_watched,
            )
        return IngestedEvent(
            event=prepared.raw_event,
            entities=[_entity_payload(entity) for entity in prepared.entities],
            alerts=alerts,
            token_intents=token_intents,
            token_resolutions=token_resolutions,
            inserted=True,
        )

    def market_resolution_for_decision(self, decision: TokenIntentResolutionDecision) -> dict[str, Any] | None:
        _require_resolution_decision(decision)
        target_type = decision.target_type
        target_id = decision.target_id
        if not target_type or not target_id:
            return None
        resolution_id = token_intent_resolution_id(decision)
        if target_type == "Asset":
            target = self.registry.chain_token_market_target(str(target_id))
            if target is None:
                return None
            return {
                "event_id": decision.event_id,
                "intent_id": decision.intent_id,
                "resolution_id": resolution_id,
                **target,
            }
        if target_type == "CexToken":
            pricefeed = self._cex_pricefeed_for_decision(decision)
            if not pricefeed:
                return None
            provider = str(pricefeed.get("provider") or "").strip().lower()
            native_market_id = str(pricefeed.get("native_market_id") or "").strip().upper()
            if not provider or not native_market_id:
                return None
            return {
                "event_id": decision.event_id,
                "intent_id": decision.intent_id,
                "resolution_id": resolution_id,
                "target_type": "cex_symbol",
                "target_id": f"{provider}:{native_market_id}",
                "exchange": provider,
                "provider": provider,
                "instrument": native_market_id,
                "native_market_id": native_market_id,
                "pricefeed_id": pricefeed.get("pricefeed_id"),
            }
        return None

    def _cex_pricefeed_for_decision(self, decision: TokenIntentResolutionDecision) -> dict[str, Any] | None:
        _require_resolution_decision(decision)
        target_id = decision.target_id
        pricefeed_id = decision.pricefeed_id
        return self.registry.cex_pricefeed_for_token(
            cex_token_id=str(target_id),
            pricefeed_id=str(pricefeed_id) if pricefeed_id else None,
        )

    def _upsert_gmgn_payload_registry(self, event: TwitterEvent) -> dict[str, Any] | None:
        asset = self._upsert_gmgn_payload_registry_asset(event)
        if asset is None:
            return None
        snapshot = event.token_snapshot
        if snapshot is None:
            return None
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

    def _upsert_gmgn_payload_registry_asset(self, event: TwitterEvent) -> dict[str, Any] | None:
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
        return asset

    def _upsert_chain_intent_registry_assets(self, event: TwitterEvent, intents: list[TokenIntentInput]) -> None:
        for item in intents:
            intent = _require_token_intent(item)
            if not intent.chain_hint or not intent.address_hint:
                continue
            self.registry.upsert_chain_asset(
                chain_id=str(intent.chain_hint),
                address=str(intent.address_hint),
                observed_at_ms=event.received_at_ms,
                commit=False,
            )

    def _intent_with_prepared_chain_hint(self, intent: TokenIntentInput) -> TokenIntentInput:
        _require_token_intent(intent)
        if intent.chain_hint or not intent.address_hint:
            return intent
        rows = self.registry.find_assets_by_address(
            chain_id=None,
            address=str(intent.address_hint),
        )
        if len(rows) != 1 or not rows[0].get("chain_id"):
            return intent
        return replace(intent, chain_hint=str(rows[0]["chain_id"]))

    def _upsert_chain_intent_registry(self, event: TwitterEvent, intents: list[TokenIntentInput]) -> None:
        for item in intents:
            intent = _require_token_intent(item)
            if not intent.chain_hint or not intent.address_hint:
                continue
            asset = self.registry.upsert_chain_asset(
                chain_id=str(intent.chain_hint),
                address=str(intent.address_hint),
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
                symbol=intent.display_symbol,
                name=None,
                decimals=None,
                confidence=CONFIDENCE_MENTION_ONLY,
                source_event_id=event.event_id,
                source_intent_id=intent.intent_id,
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
        intents_by_id: dict[str, TokenIntentInput],
        is_watched: bool,
    ) -> list[dict[str, Any]]:
        if not is_watched or not event.author.handle:
            return []
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower()
        for decision in decisions:
            if decision.target_type is None or decision.target_id is None:
                continue
            intent = _token_intent_by_id_map(intents_by_id, decision.intent_id)
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


def require_event_anchor_active_window_ms(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("event_anchor_active_window_ms_required")
    return int(value)


def _alert_value(intent: TokenIntentInput, decision: TokenIntentResolutionDecision) -> str:
    formal_intent = _require_token_intent(intent)
    value = formal_intent.display_symbol or formal_intent.address_hint
    _require_resolution_decision(decision)
    return str(value or decision.target_id)


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_resolution_decision(decision: Any) -> TokenIntentResolutionDecision:
    if not isinstance(decision, TokenIntentResolutionDecision):
        raise RuntimeError("ingest_resolution_decision_contract_required")
    return decision


def _require_token_intent(intent: Any) -> TokenIntentInput:
    if not isinstance(intent, TokenIntentInput):
        raise RuntimeError("ingest_token_intent_contract_required")
    return intent


def _token_intent_by_id(intents: list[TokenIntentInput], intent_id: str) -> TokenIntentInput:
    for intent in intents:
        formal_intent = _require_token_intent(intent)
        if formal_intent.intent_id == intent_id:
            return formal_intent
    raise RuntimeError("ingest_token_intent_contract_required")


def _token_intent_by_id_map(intents_by_id: dict[str, TokenIntentInput], intent_id: str) -> TokenIntentInput:
    intent = intents_by_id.get(intent_id)
    if intent is None:
        raise RuntimeError("ingest_token_intent_contract_required")
    return _require_token_intent(intent)


def _require_capture_result(item: Any) -> CaptureResult:
    if isinstance(item, EnrichedEventCapture):
        return CaptureResult(tick=None, capture=item)
    if not isinstance(item, CaptureResult):
        raise RuntimeError("ingest_capture_result_contract_required")
    if item.tick is not None and not isinstance(item.tick, MarketTick):
        raise RuntimeError("ingest_capture_result_contract_required")
    if not isinstance(item.capture, EnrichedEventCapture):
        raise RuntimeError("ingest_capture_result_contract_required")
    return item


def _source_dirty_events_for_resolutions(
    resolutions: list[TokenIntentResolutionDecision],
) -> list[dict[str, Any]]:
    dirty_events: list[dict[str, Any]] = []
    for decision in resolutions:
        formal_decision = _require_resolution_decision(decision)
        event_id = str(formal_decision.event_id or "")
        target_type = formal_decision.target_type
        target_id = formal_decision.target_id
        if event_id and target_type in {"Asset", "CexToken"} and target_id:
            dirty_events.append(
                {
                    "source_event_id": event_id,
                    "target_type_key": str(target_type),
                    "identity_id": str(target_id),
                }
            )
    return dirty_events


def _discovery_lookup_keys_for_resolutions(
    resolutions: list[TokenIntentResolutionDecision],
) -> list[str]:
    lookup_keys: set[str] = set()
    for decision in resolutions:
        formal_decision = _require_resolution_decision(decision)
        status = str(formal_decision.resolution_status or "")
        target_type = formal_decision.target_type
        target_id = formal_decision.target_id
        if status not in {"NIL", "AMBIGUOUS"} and target_type and target_id:
            continue
        for key in formal_decision.lookup_keys:
            text = str(key or "").strip()
            if text.startswith(("symbol:", "address:")):
                lookup_keys.add(text)
    return sorted(lookup_keys)


def _unavailable_capture(
    prepared: PreparedIngest,
    market_resolution: dict[str, Any],
    *,
    reason: str,
) -> EnrichedEventCapture:
    return EnrichedEventCapture(
        event_id=prepared.event_id,
        intent_id=str(market_resolution["intent_id"]),
        resolution_id=str(market_resolution["resolution_id"]),
        target_type=market_resolution["target_type"],
        target_id=str(market_resolution["target_id"]),
        t_event_ms=prepared.event_ms,
        tick_observed_at_ms=None,
        tick_id=None,
        tick_lag_ms=None,
        capture_method="unavailable",
        capture_reason=reason,
        created_at_ms=_now_ms(),
    )
