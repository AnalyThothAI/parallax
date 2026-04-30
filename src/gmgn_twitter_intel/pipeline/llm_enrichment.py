from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError


class LlmClient(Protocol):
    def extract(self, events: list[dict[str, Any]]) -> dict[str, Any] | str: ...


class ClaimOut(BaseModel):
    event_id: str
    claim: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class EntityOut(BaseModel):
    event_id: str
    name: str
    entity_type: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class RelationOut(BaseModel):
    event_id: str
    subject: str
    predicate: str
    object: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class ExtractionOut(BaseModel):
    claims: list[ClaimOut] = Field(default_factory=list)
    entities: list[EntityOut] = Field(default_factory=list)
    relations: list[RelationOut] = Field(default_factory=list)


class LiteLlmJsonClient:
    def __init__(self, *, model: str, api_key: str | None = None):
        self.model = model
        self.api_key = api_key

    def extract(self, events: list[dict[str, Any]]) -> str:
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("litellm is not installed") from exc
        response = litellm.completion(
            model=self.model,
            api_key=self.api_key,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract claims/entities/relations as strict JSON with claims, entities, relations arrays. "
                        "Every item must include an exact quote copied from the tweet text."
                    ),
                },
                {"role": "user", "content": json.dumps({"events": events}, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


class LlmEnrichmentService:
    def __init__(self, repo, client: LlmClient):
        self.repo = repo
        self.client = client

    def enrich_events(self, events: list[dict[str, Any]], *, scope: str, model: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        now_ms = _now_ms()
        base = {
            "llm_run_id": run_id,
            "scope": scope,
            "model": model,
            "input_event_ids_json": _json([event.get("event_id") for event in events]),
            "created_at_ms": now_ms,
            "updated_at_ms": now_ms,
        }
        self.repo.upsert_run({**base, "status": "running", "error": None, "raw_response_json": None})
        try:
            raw = self.client.extract(events)
            payload = json.loads(raw) if isinstance(raw, str) else raw
            extraction = ExtractionOut.model_validate(payload)
            _validate_quotes(extraction, events)
        except (json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
            row = {
                **base,
                "status": "failed",
                "error": str(exc),
                "raw_response_json": _json(raw) if "raw" in locals() else None,
            }
            self.repo.upsert_run(row)
            return row

        for claim in extraction.claims:
            self.repo.insert_claim(_claim_row(run_id, claim, created_at_ms=now_ms))
        for entity in extraction.entities:
            self.repo.insert_entity(_entity_row(run_id, entity, created_at_ms=now_ms))
        for relation in extraction.relations:
            self.repo.insert_relation(_relation_row(run_id, relation, created_at_ms=now_ms))
        row = {**base, "status": "succeeded", "error": None, "raw_response_json": _json(payload)}
        self.repo.upsert_run(row)
        return row


def _validate_quotes(extraction: ExtractionOut, events: list[dict[str, Any]]) -> None:
    text_by_event_id = {
        str(event.get("event_id")): str((event.get("content") or {}).get("text") or "") for event in events
    }
    for item in [*extraction.claims, *extraction.entities, *extraction.relations]:
        text = text_by_event_id.get(item.event_id, "")
        if not item.quote or item.quote not in text:
            raise ValueError(f"quote_not_found event_id={item.event_id} quote={item.quote!r}")


def _claim_row(run_id: str, claim: ClaimOut, *, created_at_ms: int) -> dict[str, Any]:
    return {
        "claim_id": _row_id(run_id, claim.event_id, claim.quote, claim.claim),
        "llm_run_id": run_id,
        "event_id": claim.event_id,
        "claim": claim.claim,
        "quote": claim.quote,
        "confidence": claim.confidence,
        "created_at_ms": created_at_ms,
    }


def _entity_row(run_id: str, entity: EntityOut, *, created_at_ms: int) -> dict[str, Any]:
    return {
        "entity_id": _row_id(run_id, entity.event_id, entity.quote, entity.name, entity.entity_type),
        "llm_run_id": run_id,
        "event_id": entity.event_id,
        "name": entity.name,
        "entity_type": entity.entity_type,
        "quote": entity.quote,
        "confidence": entity.confidence,
        "created_at_ms": created_at_ms,
    }


def _relation_row(run_id: str, relation: RelationOut, *, created_at_ms: int) -> dict[str, Any]:
    return {
        "relation_id": _row_id(
            run_id,
            relation.event_id,
            relation.quote,
            relation.subject,
            relation.predicate,
            relation.object,
        ),
        "llm_run_id": run_id,
        "event_id": relation.event_id,
        "subject": relation.subject,
        "predicate": relation.predicate,
        "object": relation.object,
        "quote": relation.quote,
        "confidence": relation.confidence,
        "created_at_ms": created_at_ms,
    }


def _row_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now_ms() -> int:
    return int(time.time() * 1000)
