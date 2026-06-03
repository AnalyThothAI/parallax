from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_item_brief_work,
    enqueue_page_reprojection,
)
from parallax.domains.news_intel.services.news_content_classification import classify_news_item_content
from parallax.domains.news_intel.services.news_entity_extraction import NewsEntity, extract_news_entities
from parallax.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)
from parallax.domains.news_intel.services.news_token_mentions import build_news_token_mentions
from parallax.domains.token_intel.interfaces import TokenIdentityLookup


class NewsItemProcessWorker(WorkerBase):
    def __init__(
        self,
        *,
        identity_lookup: TokenIdentityLookup | None = None,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.identity_lookup = identity_lookup
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        if self.identity_lookup is None:
            return WorkerResult(skipped=1, notes={"reason": "missing_identity_lookup"})

        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos, repos.conn.transaction():
            repos.news.release_expired_processing_items(now_ms=now, commit=False)
            items = repos.news.claim_unprocessed_items(
                limit=self._batch_size(),
                lease_owner=self.name,
                lease_ms=self._lease_ms(),
                now_ms=now,
                commit=False,
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
                provider_impacts = _json_list(item_payload.get("provider_token_impacts_json"))
                if provider_impacts:
                    entities = _entities_from_provider_impacts(
                        news_item_id=news_item_id,
                        impacts=provider_impacts,
                        now_ms=now,
                    )
                else:
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
                    authority_scope=_json_dict(item_payload.get("authority_scope_json")),
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
                with self._repository_session() as repos, repos.conn.transaction():
                    repos.news.replace_item_entities(news_item_id=news_item_id, entities=entities, commit=False)
                    repos.news.replace_token_mentions(news_item_id=news_item_id, mentions=mentions, commit=False)
                    repos.news.replace_fact_candidates(
                        news_item_id=news_item_id,
                        candidates=candidates,
                        commit=False,
                    )
                    repos.news.update_item_content_classification(
                        news_item_id=news_item_id,
                        content_class=classification.content_class,
                        content_tags=classification.content_tags,
                        classification_payload=classification.classification_payload,
                        now_ms=now,
                        commit=False,
                    )
                    marked = repos.news.mark_item_processed(
                        news_item_id=news_item_id,
                        processed_at_ms=now,
                        lease_owner=claim_lease_owner,
                        processing_attempts=claim_attempt,
                        commit=False,
                    )
                    if marked == 0:
                        raise _StaleClaimError(news_item_id)
                    processed_item = {
                        **item_payload,
                        "lifecycle_status": "processed",
                        "content_class": classification.content_class,
                        "content_tags_json": classification.content_tags,
                        "content_classification_json": classification.classification_payload,
                    }
                    mention_payloads = [_object_payload(mention) for mention in mentions]
                    candidate_payloads = [_object_payload(candidate) for candidate in candidates]
                    enqueue_page_reprojection(
                        repos,
                        news_item_ids=[news_item_id],
                        reason="news_item_processed",
                        now_ms=now,
                        commit=False,
                    )
                    eligibility = news_item_agent_brief_eligibility(
                        item=processed_item,
                        token_mentions=mention_payloads,
                        fact_candidates=candidate_payloads,
                        context_items=[],
                        now_ms=now,
                    )
                    if eligibility.eligible:
                        enqueue_item_brief_work(
                            repos,
                            news_item_ids=[news_item_id],
                            priority_by_news_item_id={
                                news_item_id: news_item_agent_brief_priority(
                                    item=processed_item,
                                    token_mentions=mention_payloads,
                                    fact_candidates=candidate_payloads,
                                    context_items=[],
                                )
                            },
                            reason="news_item_processed",
                            now_ms=now,
                            commit=False,
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

        if processed > 0 and self.wake_bus is not None:
            self.wake_bus.notify_news_item_processed(count=processed)
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
            with self._repository_session() as repos, repos.conn.transaction():
                if attempt_after_claim >= self._max_attempts():
                    return repos.news.mark_item_process_terminal_failed(
                        news_item_id=news_item_id,
                        error=error_text,
                        now_ms=failure_now_ms,
                        lease_owner=lease_owner,
                        processing_attempts=attempt_after_claim,
                        commit=False,
                    )
                return repos.news.mark_item_process_retryable(
                    news_item_id=news_item_id,
                    error=error_text,
                    next_due_at_ms=failure_now_ms + self._retry_delay_ms(),
                    now_ms=failure_now_ms,
                    lease_owner=lease_owner,
                    processing_attempts=attempt_after_claim,
                    commit=False,
                )
        except Exception:
            return None

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 10)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", 120_000)))

    def _max_attempts(self) -> int:
        return max(1, int(getattr(self.settings, "max_attempts", 3)))

    def _retry_delay_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_delay_ms", 60_000)))


def _entities_from_provider_impacts(
    *,
    news_item_id: str,
    impacts: list[Any],
    now_ms: int,
) -> list[NewsEntity]:
    entities: list[NewsEntity] = []
    seen: set[str] = set()
    for impact in impacts:
        if not isinstance(impact, Mapping):
            continue
        symbol = str(impact.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        entities.append(
            NewsEntity(
                entity_id=_stable_id("news-provider-entity", news_item_id, symbol),
                news_item_id=news_item_id,
                entity_type="symbol",
                raw_value=symbol,
                normalized_value=symbol,
                chain=None,
                span_start=0,
                span_end=len(symbol),
                text_surface="provider_token_impacts",
                confidence=1.0,
                extraction_policy_version="opennews_provider_impacts_v1",
                created_at_ms=int(now_ms),
            )
        )
    return entities


def _required_text(item: Mapping[str, Any], key: str) -> str:
    value = _text(item, key)
    if not value:
        raise ValueError(f"news item missing required {key}")
    return value


def _text(item: Mapping[str, Any], key: str) -> str:
    return str(item.get(key) or "").strip()


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _processing_attempts(item: Mapping[str, Any]) -> int:
    try:
        return max(0, int(item.get("processing_attempts", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _processing_lease_owner(item: Mapping[str, Any]) -> str:
    return str(item.get("processing_lease_owner") or "").strip()


class _StaleClaimError(RuntimeError):
    pass


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return dict(asdict(value))
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump(mode="json"))
    return dict(getattr(value, "__dict__", {}) or {})


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


__all__ = ["NewsItemProcessWorker"]
