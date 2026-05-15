from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.asset_market.interfaces import (
    CONFIDENCE_MENTION_ONLY,
    CONFIDENCE_PROVIDER_EXACT,
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_TWEET_CONTRACT_MENTION,
    EnrichedEventRepository,
    IdentityEvidenceRepository,
    MarketTickRepository,
    RegistryRepository,
)
from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture
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
from gmgn_twitter_intel.domains.token_intel.repositories.intent_resolution_repository import (
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
    intents: list[Any]
    is_watched: bool


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
        token_evidence: TokenEvidenceRepository | None = None,
        token_intents: TokenIntentRepository | None = None,
        intent_resolutions: IntentResolutionRepository | None = None,
        market_ticks: MarketTickRepository | None = None,
        enriched_events: EnrichedEventRepository | None = None,
    ) -> None:
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.registry = registry or RegistryRepository(evidence.conn)
        self.identity_evidence = identity_evidence or IdentityEvidenceRepository(evidence.conn)
        self.token_intent_lookup = token_intent_lookup or TokenIntentLookupRepository(evidence.conn)
        self.token_evidence = token_evidence or TokenEvidenceRepository(evidence.conn)
        self.token_intents = token_intents or TokenIntentRepository(evidence.conn)
        self.intent_resolutions = intent_resolutions or IntentResolutionRepository(evidence.conn)
        self.market_ticks = market_ticks or MarketTickRepository(evidence.conn)
        self.enriched_events = enriched_events or EnrichedEventRepository(evidence.conn)

    def insert_raw_frame(self, **kwargs: Any) -> bool:
        result: bool = self.evidence.insert_raw_frame(**kwargs)
        return result

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        prepared = self.prepare_event(event, is_watched=is_watched)
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
        row = self.evidence.conn.execute(
            """
            SELECT 1 AS found
            FROM events
            WHERE event_id = %s OR logical_dedup_key = %s
            LIMIT 1
            """,
            (prepared.event_id, prepared.event_row["logical_dedup_key"]),
        ).fetchone()
        return bool(row)

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
                intent,
                prepared.evidence_inputs,
                decision_time_ms=prepared.event_ms,
                persist=persist,
                commit=False,
            )
            for intent in prepared.intents
        ]

    def commit_prepared_event(
        self,
        prepared: PreparedIngest,
        *,
        resolutions: list[Any],
        captures: list[Any],
    ) -> IngestedEvent:
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
                self.intent_resolutions.insert_resolution(decision, commit=False)
                decision_intent_id = _decision_value(decision, "intent_id")
                intent = next((item for item in prepared.intents if item.intent_id == decision_intent_id), None)
                self.token_intent_lookup.replace_lookup_keys(
                    intent_id=decision_intent_id,
                    event_id=_decision_value(decision, "event_id"),
                    keys=_decision_value(decision, "lookup_keys") or [],
                    source_evidence_id=getattr(intent, "primary_evidence_id", None),
                    created_at_ms=prepared.event_ms,
                    commit=False,
                )
            for item in captures:
                tick = getattr(item, "tick", None)
                capture = getattr(item, "capture", item)
                if tick is not None:
                    self.market_ticks.insert_tick(tick)
                self.enriched_events.insert_capture(capture)
            token_resolutions = self.intent_resolutions.resolutions_for_event(prepared.event_id)
            alerts = self._insert_token_alerts(
                prepared.raw_event,
                resolutions,
                resolutions=self.intent_resolutions,
                intents_by_id={item.intent_id: item for item in prepared.intents},
                is_watched=prepared.is_watched,
            )
            enrichment_job_id = None
            enrichment_priority = watched_social_event_priority(
                event=prepared.raw_event,
                entities=prepared.entities,
                token_resolutions=token_resolutions,
            )
            if prepared.is_watched and enrichment_priority is not None:
                enrichment_job_id = self.enrichment.enqueue_watched_event(
                    event_id=prepared.event_id,
                    received_at_ms=prepared.event_ms,
                    priority=enrichment_priority,
                    commit=False,
                )
        return IngestedEvent(
            event=prepared.raw_event,
            entities=[_entity_payload(entity) for entity in prepared.entities],
            alerts=alerts,
            token_intents=token_intents,
            token_resolutions=token_resolutions,
            inserted=True,
            enrichment_job_id=enrichment_job_id,
        )

    def market_resolution_for_decision(self, decision: Any) -> dict[str, Any] | None:
        target_type = _decision_value(decision, "target_type")
        target_id = _decision_value(decision, "target_id")
        if not target_type or not target_id:
            return None
        resolution_id = token_intent_resolution_id(decision)
        if target_type == "Asset":
            row = self.registry.conn.execute(
                """
                SELECT chain_id, address
                FROM registry_assets
                WHERE asset_id = %s
                """,
                (target_id,),
            ).fetchone()
            if not row or not row.get("chain_id") or not row.get("address"):
                return None
            chain_id = str(row["chain_id"])
            address = str(row["address"])
            return {
                "event_id": _decision_value(decision, "event_id"),
                "intent_id": _decision_value(decision, "intent_id"),
                "resolution_id": resolution_id,
                "target_type": "chain_token",
                "target_id": f"{chain_id}:{address}",
                "chain_id": chain_id,
                "token_address": address,
                "address": address,
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
                "event_id": _decision_value(decision, "event_id"),
                "intent_id": _decision_value(decision, "intent_id"),
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

    def _cex_pricefeed_for_decision(self, decision: Any) -> dict[str, Any] | None:
        target_id = _decision_value(decision, "target_id")
        pricefeed_id = _decision_value(decision, "pricefeed_id")
        if pricefeed_id:
            row = self.registry.conn.execute(
                """
                SELECT *
                FROM price_feeds
                WHERE pricefeed_id = %s
                  AND subject_type = 'CexToken'
                  AND subject_id = %s
                  AND feed_type LIKE 'cex_%%'
                  AND status IN ('candidate', 'canonical')
                """,
                (pricefeed_id, target_id),
            ).fetchone()
            if row:
                return dict(row)
        row = self.registry.conn.execute(
            """
            SELECT *
            FROM price_feeds
            WHERE subject_type = 'CexToken'
              AND subject_id = %s
              AND feed_type LIKE 'cex_%%'
              AND status IN ('candidate', 'canonical')
            ORDER BY
              CASE
                WHEN feed_type = 'cex_spot' THEN 0
                WHEN feed_type = 'cex_swap' THEN 1
                ELSE 2
              END,
              CASE
                WHEN quote_symbol = 'USDT' THEN 0
                WHEN quote_symbol = 'USD' THEN 1
                WHEN quote_symbol = 'USDC' THEN 2
                ELSE 9
              END,
              updated_at_ms DESC,
              native_market_id ASC
            LIMIT 1
            """,
            (target_id,),
        ).fetchone()
        return dict(row) if row else None

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

    def _upsert_chain_intent_registry_assets(self, event: TwitterEvent, intents: list[Any]) -> None:
        for intent in intents:
            chain_hint = getattr(intent, "chain_hint", None)
            address_hint = getattr(intent, "address_hint", None)
            if not chain_hint or not address_hint:
                continue
            self.registry.upsert_chain_asset(
                chain_id=str(chain_hint),
                address=str(address_hint),
                observed_at_ms=event.received_at_ms,
                commit=False,
            )

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
    return str(value or _decision_value(decision, "target_id"))


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decision_value(decision: Any, key: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(key)
    return getattr(decision, key)


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
        tick_id=None,
        tick_lag_ms=None,
        capture_method="unavailable",
        capture_reason=reason,
        created_at_ms=_now_ms(),
    )
