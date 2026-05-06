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
from .asset_attribution import persist_asset_decisions
from .asset_mention_builder import build_asset_mentions
from .asset_resolver import AssetResolutionDecision, AssetResolver
from .entity_extractor import extract_entities


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    event: TwitterEvent
    entities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    inserted: bool
    enrichment_job_id: str | None = None
    asset_attributions: list[dict[str, Any]] = field(default_factory=list)


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
        self.asset_resolver = AssetResolver(self.assets)

    def insert_raw_frame(self, **kwargs) -> bool:
        return self.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent:
        extracted = extract_entities(_event_text(event))
        with transaction(self.evidence.conn):
            row = event_to_row(event, is_watched=is_watched, now_ms=_now_ms())
            inserted = self.evidence.insert_event_without_commit(row)
            if not inserted:
                return IngestedEvent(
                    event=event,
                    entities=[],
                    alerts=[],
                    asset_attributions=[],
                    inserted=False,
                )
            self.entities.insert_event_entities(event, extracted, is_watched=is_watched, commit=False)
            mention_inputs = build_asset_mentions(
                event_id=event.event_id,
                entities=extracted,
                token_snapshot=event.token_snapshot,
                created_at_ms=event.received_at_ms,
            )
            asset_mentions = self.assets.insert_mentions(mention_inputs, commit=False)
            asset_decisions = self.asset_resolver.resolve_many(asset_mentions)
            asset_attributions = persist_asset_decisions(
                self.assets,
                asset_decisions,
                decision_time_ms=event.received_at_ms,
                created_at_ms=event.received_at_ms,
                commit=False,
            )
            self._insert_gmgn_payload_market_snapshot(
                event,
                asset_decisions,
                mentions_by_id={str(row["mention_id"]): row for row in asset_mentions},
            )
            alerts = self._insert_asset_alerts(
                event,
                asset_decisions,
                mentions_by_id={str(row["mention_id"]): row for row in asset_mentions},
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
            asset_attributions=asset_attributions,
            inserted=True,
            enrichment_job_id=enrichment_job_id,
        )

    def _insert_gmgn_payload_market_snapshot(
        self,
        event: TwitterEvent,
        decisions: list[AssetResolutionDecision],
        *,
        mentions_by_id: dict[str, dict[str, Any]],
    ) -> None:
        snapshot = event.token_snapshot
        if snapshot is None:
            return
        if snapshot.price is None and snapshot.market_cap is None:
            return
        for decision in decisions:
            mention = mentions_by_id.get(decision.mention_id, {})
            if mention.get("mention_type") != "gmgn_payload" or not decision.venue_id:
                continue
            self.assets.insert_market_snapshot(
                asset_id=decision.asset_id,
                venue_id=decision.venue_id,
                provider="gmgn_payload",
                observed_at_ms=event.received_at_ms,
                price_usd=snapshot.price,
                market_cap_usd=snapshot.market_cap,
                source_payload_hash=_payload_hash(snapshot.raw),
                created_at_ms=event.received_at_ms,
                commit=False,
            )
            return

    def _insert_asset_alerts(
        self,
        event: TwitterEvent,
        decisions: list[AssetResolutionDecision],
        *,
        mentions_by_id: dict[str, dict[str, Any]],
        is_watched: bool,
    ) -> list[dict[str, Any]]:
        if not is_watched or not event.author.handle:
            return []
        alerts: list[dict[str, Any]] = []
        author_handle = event.author.handle.lower()
        for decision in decisions:
            mention = mentions_by_id.get(decision.mention_id, {})
            seen_global, seen_author = self.assets.asset_seen_before(
                asset_id=decision.asset_id,
                author_handle=author_handle,
                before_ms=event.received_at_ms,
            )
            alert = self.signals.insert_account_token_alert(
                event_id=event.event_id,
                author_handle=author_handle,
                entity_key=decision.asset_id,
                entity_type="asset",
                normalized_value=_alert_value(mention, decision),
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


def _alert_value(mention: dict[str, Any], decision: AssetResolutionDecision) -> str:
    value = mention.get("normalized_symbol") or mention.get("address_hint") or mention.get("raw_value")
    return str(value or decision.asset_id)


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
