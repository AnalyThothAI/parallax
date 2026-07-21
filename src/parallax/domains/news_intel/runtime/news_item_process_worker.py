from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_page_reprojection,
    enqueue_story_brief_work,
)
from parallax.domains.news_intel.services.news_content_classification import classify_news_item_content
from parallax.domains.news_intel.services.news_entity_extraction import extract_news_entities
from parallax.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from parallax.domains.news_intel.services.news_item_agent_admission import (
    decide_news_item_agent_admission,
)
from parallax.domains.news_intel.services.news_market_scope import classify_news_market_scope
from parallax.domains.news_intel.services.news_story_agent_policy import (
    news_story_brief_priority,
)
from parallax.domains.news_intel.services.news_story_identity import build_news_story_identity
from parallax.domains.news_intel.services.news_token_mentions import build_news_token_mentions
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmissionContext
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_story_identity import NewsStoryIdentity
from parallax.domains.token_intel.interfaces import TokenIdentityLookup
from parallax.platform.config.settings import NewsItemProcessWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class NewsItemProcessWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: NewsItemProcessWorkerSettings,
        db: Any,
        telemetry: Any,
        identity_lookup: TokenIdentityLookup | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "news_item_process",
    ) -> None:
        if db is None:
            raise RuntimeError("news_item_process_db_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
        )
        self.identity_lookup = identity_lookup
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        if self.identity_lookup is None:
            return WorkerResult(skipped=1, notes={"reason": "missing_identity_lookup"})

        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos, repos.transaction():
            repos.news_items.release_expired_processing_items(now_ms=now)
            items = repos.news_items.claim_unprocessed_items(
                limit=self._batch_size(),
                lease_owner=self.name,
                lease_ms=self._lease_ms(),
                now_ms=now,
            )
        if not items:
            return WorkerResult(skipped=1, notes={"reason": "no_unprocessed_items"})

        processed = 0
        failed = 0
        stale_claims = 0
        for item in items:
            item_payload = dict(item)
            news_item_id = _required_text(item_payload, "news_item_id")
            claim_attempt = _processing_attempts(item_payload)
            claim_lease_owner = _processing_lease_owner(item_payload)
            try:
                entities = extract_news_entities(
                    news_item_id=news_item_id,
                    title=_text(item_payload, "title"),
                    summary=_text(item_payload, "summary"),
                    body_text=_text(item_payload, "body_text"),
                    now_ms=now,
                )
                mentions = build_news_token_mentions(
                    news_item_id=news_item_id,
                    entities=entities,
                    identity_lookup=self.identity_lookup,
                    now_ms=now,
                )
                candidates = build_fact_candidates(
                    news_item_id=news_item_id,
                    source_role=_text(item_payload, "source_role") or "observed_source",
                    source_domain=_text(item_payload, "source_domain"),
                    authority_scope=_optional_item_process_mapping(
                        item_payload.get("authority_scope_json"),
                        "authority_scope_json",
                    ),
                    title=_text(item_payload, "title"),
                    summary=_text(item_payload, "summary"),
                    body_text=_text(item_payload, "body_text"),
                    token_mentions=mentions,
                    now_ms=now,
                )
                classification = classify_news_item_content(
                    headline=_text(item_payload, "title"),
                    summary=_text(item_payload, "summary"),
                    source_domain=_text(item_payload, "source_domain"),
                    fact_event_types=[candidate.event_type for candidate in candidates],
                )
                processed_item = {
                    **item_payload,
                    "lifecycle_status": "processed",
                    "content_class": classification.content_class,
                    "content_tags_json": classification.content_tags,
                    "content_classification_json": classification.classification_payload,
                }
                mention_payloads = [_object_payload(mention) for mention in mentions]
                candidate_payloads = [_object_payload(candidate) for candidate in candidates]
                market_scope = classify_news_market_scope(
                    item=processed_item,
                    token_mentions=mention_payloads,
                    fact_candidates=candidate_payloads,
                )
                market_scope_payload = _market_scope_payload(market_scope)
                story_identity = build_news_story_identity(
                    item=processed_item,
                    token_mentions=mention_payloads,
                    fact_candidates=candidate_payloads,
                    market_scope=market_scope_payload,
                )
                story_identity_payload = _story_identity_payload(story_identity)
                processed_item.update(
                    {
                        "market_scope_json": market_scope_payload,
                        "story_key": story_identity_payload["story_key"],
                        "story_identity_json": story_identity_payload,
                        "story_identity_version": story_identity_payload["version"],
                    }
                )
                with self._repository_session() as repos, repos.transaction():
                    repos.news_items.replace_item_entities(news_item_id=news_item_id, entities=entities)
                    repos.news_items.replace_token_mentions(news_item_id=news_item_id, mentions=mentions)
                    repos.news_items.replace_fact_candidates(
                        news_item_id=news_item_id,
                        candidates=candidates,
                    )
                    repos.news_items.update_item_content_classification(
                        news_item_id=news_item_id,
                        content_class=classification.content_class,
                        content_tags=classification.content_tags,
                        classification_payload=classification.classification_payload,
                        now_ms=now,
                    )
                    repos.news_items.update_item_market_scope_and_story_identity(
                        news_item_id=news_item_id,
                        market_scope=market_scope,
                        story_identity=story_identity,
                        now_ms=now,
                    )
                    marked = repos.news_items.mark_item_processed(
                        news_item_id=news_item_id,
                        processed_at_ms=now,
                        lease_owner=claim_lease_owner,
                        processing_attempts=claim_attempt,
                    )
                    if marked == 0:
                        raise _StaleClaimError(news_item_id)
                    enqueue_page_reprojection(
                        repos,
                        news_item_ids=[news_item_id],
                        reason="news_item_processed",
                        now_ms=now,
                        source_watermark_ms_by_news_item_id={news_item_id: _source_watermark_ms(processed_item)},
                    )
                    context_payload = _agent_admission_context(
                        repos.news_items.load_agent_admission_contexts(news_item_ids=[news_item_id], now_ms=now),
                        news_item_id=news_item_id,
                    )
                    context_item = context_payload["item"]
                    context_token_mentions = context_payload["token_mentions"]
                    context_fact_candidates = context_payload["fact_candidates"]
                    agent_admission = decide_news_item_agent_admission(
                        item=context_item,
                        entities=context_payload["entities"],
                        token_mentions=context_token_mentions,
                        fact_candidates=context_fact_candidates,
                        context=NewsItemAgentAdmissionContext.from_repository_context(context_payload),
                        now_ms=now,
                    )
                    repos.news_items.update_item_agent_admission(
                        news_item_id=news_item_id,
                        admission=agent_admission,
                        now_ms=now,
                    )
                    if agent_admission.eligible:
                        story_key = _required_text(context_item, "story_key")
                        brief_priority = news_story_brief_priority(
                            item=context_item,
                            admission=agent_admission,
                        )
                        source_watermark_ms = _source_watermark_ms(processed_item)
                        enqueue_story_brief_work(
                            repos,
                            story_keys=[story_key],
                            priority_by_story_key={story_key: brief_priority},
                            source_watermark_ms_by_story_key={story_key: source_watermark_ms},
                            reason="news_item_processed",
                            now_ms=now,
                        )
                processed += 1
            except _StaleClaimError:
                stale_claims += 1
                continue
            except Exception as exc:  # pragma: no cover - exercised by integration/ops paths.
                marked = self._mark_item_failed(
                    news_item_id=news_item_id,
                    error=exc,
                    lease_owner=claim_lease_owner,
                    attempt_after_claim=claim_attempt,
                )
                if marked == 0:
                    stale_claims += 1
                    continue
                failed += 1

        notes = {"claimed": len(items)}
        if stale_claims > 0:
            notes["stale_claims"] = stale_claims
        return WorkerResult(processed=processed, failed=failed, notes=notes)

    def _mark_item_failed(
        self,
        *,
        news_item_id: str,
        error: Exception,
        lease_owner: str,
        attempt_after_claim: int,
    ) -> int | None:
        failure_now_ms = int(self.clock_ms())
        error_text = str(error)[:2_000]
        try:
            with self._repository_session() as repos, repos.transaction():
                if attempt_after_claim >= self._max_attempts():
                    return int(
                        repos.news_items.mark_item_process_terminal_failed(
                            news_item_id=news_item_id,
                            error=error_text,
                            now_ms=failure_now_ms,
                            lease_owner=lease_owner,
                            processing_attempts=attempt_after_claim,
                        )
                    )
                return int(
                    repos.news_items.mark_item_process_retryable(
                        news_item_id=news_item_id,
                        error=error_text,
                        next_due_at_ms=failure_now_ms + self._retry_delay_ms(),
                        now_ms=failure_now_ms,
                        lease_owner=lease_owner,
                        processing_attempts=attempt_after_claim,
                    )
                )
        except Exception:
            return None

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _batch_size(self) -> int:
        return self.settings.batch_size

    def _lease_ms(self) -> int:
        return self.settings.lease_ms

    def _max_attempts(self) -> int:
        return self.settings.max_attempts

    def _retry_delay_ms(self) -> int:
        return self.settings.retry_delay_ms


def _required_text(item: Mapping[str, Any], key: str) -> str:
    value = _text(item, key)
    if not value:
        raise ValueError(f"news item missing required {key}")
    return value


def _text(item: Mapping[str, Any], key: str) -> str:
    return str(item.get(key) or "").strip()


def _optional_item_process_mapping(value: object, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"news_item_process_{field_name}_required")


def _agent_admission_context(
    rows: object,
    *,
    news_item_id: str,
) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ValueError(f"news item {news_item_id} missing agent admission context")
    normalized_rows: list[dict[str, Any]] = []
    for candidate in rows:
        if not isinstance(candidate, Mapping):
            raise ValueError(f"news_item_process_agent_admission_context_rows_required:{news_item_id}")
        normalized_rows.append(dict(candidate))
    row = next(iter(normalized_rows), None)
    if row is None:
        raise ValueError(f"news item {news_item_id} missing agent admission context")
    required_keys = (
        "item",
        "entities",
        "token_mentions",
        "fact_candidates",
        "exact_duplicate_candidates",
        "story_candidates",
    )
    missing = [key for key in required_keys if key not in row]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"news item {news_item_id} missing agent admission context fields: {missing_text}")
    return {
        **row,
        "item": _required_agent_context_mapping(row["item"], "item", news_item_id=news_item_id),
        "entities": _required_agent_context_mapping_list(row["entities"], "entities", news_item_id=news_item_id),
        "token_mentions": _required_agent_context_mapping_list(
            row["token_mentions"],
            "token_mentions",
            news_item_id=news_item_id,
        ),
        "fact_candidates": _required_agent_context_mapping_list(
            row["fact_candidates"],
            "fact_candidates",
            news_item_id=news_item_id,
        ),
        "exact_duplicate_candidates": _required_agent_context_mapping_list(
            row["exact_duplicate_candidates"],
            "exact_duplicate_candidates",
            news_item_id=news_item_id,
        ),
        "story_candidates": _required_agent_context_mapping_list(
            row["story_candidates"],
            "story_candidates",
            news_item_id=news_item_id,
        ),
    }


def _required_agent_context_mapping(
    value: object,
    field_name: str,
    *,
    news_item_id: str,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        payload = dict(value)
        if payload:
            return payload
    raise ValueError(f"news_item_process_agent_admission_context_{field_name}_required:{news_item_id}")


def _required_agent_context_mapping_list(
    value: object,
    field_name: str,
    *,
    news_item_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"news_item_process_agent_admission_context_{field_name}_required:{news_item_id}")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError(f"news_item_process_agent_admission_context_{field_name}_required:{news_item_id}")
        rows.append(dict(row))
    return rows


def _processing_attempts(item: Mapping[str, Any]) -> int:
    try:
        attempts = int(item["processing_attempts"])
    except (TypeError, ValueError):
        raise ValueError("news_item_process_claim_attempt_required") from None
    except KeyError as exc:
        raise ValueError("news_item_process_claim_attempt_required") from exc
    if attempts <= 0:
        raise ValueError("news_item_process_claim_attempt_required")
    return attempts


def _processing_lease_owner(item: Mapping[str, Any]) -> str:
    try:
        lease_owner = str(item["processing_lease_owner"] or "").strip()
    except KeyError as exc:
        raise ValueError("news_item_process_claim_lease_owner_required") from exc
    if not lease_owner:
        raise ValueError("news_item_process_claim_lease_owner_required")
    return lease_owner


def _source_watermark_ms(item: Mapping[str, Any]) -> int:
    candidates = [
        _optional_int(item.get("fetched_at_ms")),
        _optional_int(item.get("published_at_ms")),
    ]
    source_values = [value for value in candidates if value is not None]
    if source_values:
        return max(source_values)
    news_item_id = str(item.get("news_item_id") or "").strip()
    suffix = f":{news_item_id}" if news_item_id else ""
    raise ValueError(f"news_item_process_source_watermark_required{suffix}")


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class _StaleClaimError(RuntimeError):
    pass


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    raise ValueError("unsupported news item process payload shape")


def _market_scope_payload(value: NewsMarketScope) -> dict[str, object]:
    payload = _strict_current_payload(
        value,
        expected_type=NewsMarketScope,
        label="market scope payload",
        required_fields=("scope", "primary", "status", "reason", "basis", "version"),
    )
    return {
        "scope": _required_payload_list(payload, "scope", label="market scope payload"),
        "primary": _required_payload_text(payload, "primary", label="market scope payload"),
        "status": _required_payload_text(payload, "status", label="market scope payload"),
        "reason": _required_payload_text(payload, "reason", label="market scope payload"),
        "basis": _required_payload_mapping(payload, "basis", label="market scope payload"),
        "version": _required_payload_text(payload, "version", label="market scope payload"),
    }


def _story_identity_payload(value: NewsStoryIdentity) -> dict[str, object]:
    payload = _strict_current_payload(
        value,
        expected_type=NewsStoryIdentity,
        label="story identity payload",
        required_fields=("story_key", "confidence", "basis", "version"),
    )
    return {
        "story_key": _required_payload_text(payload, "story_key", label="story identity payload"),
        "confidence": _required_payload_text(payload, "confidence", label="story identity payload"),
        "basis": _required_payload_mapping(payload, "basis", label="story identity payload"),
        "version": _required_payload_text(payload, "version", label="story identity payload"),
    }


def _strict_current_payload(
    value: NewsMarketScope | NewsStoryIdentity,
    *,
    expected_type: type[NewsMarketScope] | type[NewsStoryIdentity],
    label: str,
    required_fields: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(value, expected_type):
        raise ValueError(f"unsupported {label} shape")
    payload = {field.name: getattr(value, field.name) for field in fields(value)}
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"unsupported {label} shape: missing {', '.join(missing)}")
    return payload


def _required_payload_text(payload: Mapping[str, object], field: str, *, label: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"unsupported {label} shape: blank {field}")
    return value


def _required_payload_mapping(payload: Mapping[str, object], field: str, *, label: str) -> dict[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"unsupported {label} shape: {field} must be mapping")
    return dict(value)


def _required_payload_list(payload: Mapping[str, object], field: str, *, label: str) -> list[object]:
    value = payload.get(field)
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"unsupported {label} shape: {field} must be list")
    if not value:
        raise ValueError(f"unsupported {label} shape: {field} must be non-empty")
    return list(value)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsItemProcessWorker"]
