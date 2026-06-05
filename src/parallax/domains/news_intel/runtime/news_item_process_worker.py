from __future__ import annotations

import asyncio
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
from parallax.domains.news_intel.services.news_analysis_admission import (
    NewsAnalysisAdmission,
    decide_news_analysis_admission,
)
from parallax.domains.news_intel.services.news_content_classification import classify_news_item_content
from parallax.domains.news_intel.services.news_entity_extraction import extract_news_entities
from parallax.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)
from parallax.domains.news_intel.services.news_story_identity import NewsStoryIdentity, build_news_story_identity
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
        with self._repository_session() as repos:
            items = repos.news.list_unprocessed_items(limit=self._batch_size(), now_ms=now)
        if not items:
            return WorkerResult(skipped=1, notes={"reason": "no_unprocessed_items"})

        processed = 0
        failed = 0
        for item in items:
            item_payload = dict(item)
            news_item_id = _required_text(item_payload, "news_item_id")
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
                processed_item = {
                    **item_payload,
                    "lifecycle_status": "processed",
                    "content_class": classification.content_class,
                    "content_tags_json": classification.content_tags,
                    "content_classification_json": classification.classification_payload,
                }
                mention_payloads = [_object_payload(mention) for mention in mentions]
                candidate_payloads = [_object_payload(candidate) for candidate in candidates]
                admission = decide_news_analysis_admission(
                    item=processed_item,
                    token_mentions=mention_payloads,
                    fact_candidates=candidate_payloads,
                )
                admission_payload = _analysis_admission_payload(admission)
                story_identity = build_news_story_identity(
                    item=processed_item,
                    token_mentions=mention_payloads,
                    fact_candidates=candidate_payloads,
                    admission=admission_payload,
                )
                story_identity_payload = _story_identity_payload(story_identity)
                processed_item.update(
                    {
                        "analysis_admission_status": admission_payload["status"],
                        "analysis_admission_reason": admission_payload["reason"],
                        "analysis_admission_json": admission_payload,
                        "analysis_admission_version": admission_payload["version"],
                        "story_key": story_identity_payload["story_key"],
                        "story_identity_json": story_identity_payload,
                        "story_identity_version": story_identity_payload["version"],
                    }
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
                    repos.news.update_item_analysis_and_story_identity(
                        news_item_id=news_item_id,
                        admission=admission,
                        story_identity=story_identity,
                        now_ms=now,
                        commit=False,
                    )
                    repos.news.mark_item_processed(news_item_id=news_item_id, processed_at_ms=now, commit=False)
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
                                )
                            },
                            reason="news_item_processed",
                            now_ms=now,
                            commit=False,
                        )
                processed += 1
            except Exception as exc:  # pragma: no cover - exercised by integration/ops paths.
                failed += 1
                self._mark_item_failed(news_item_id=news_item_id, error=exc, now_ms=now)

        if processed > 0 and self.wake_bus is not None:
            self.wake_bus.notify_news_item_processed(count=processed)
        return WorkerResult(processed=processed, failed=failed, notes={"claimed": len(items)})

    def _mark_item_failed(self, *, news_item_id: str, error: Exception, now_ms: int) -> None:
        try:
            with self._repository_session() as repos:
                repos.news.mark_item_process_failed(
                    news_item_id=news_item_id,
                    error=str(error)[:2_000],
                    now_ms=now_ms,
                )
        except Exception:
            return

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 10)))


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


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return dict(asdict(value))
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump(mode="json"))
    return dict(getattr(value, "__dict__", {}) or {})


def _analysis_admission_payload(value: NewsAnalysisAdmission | Mapping[str, object]) -> dict[str, object]:
    payload = _strict_current_payload(
        value,
        expected_type=NewsAnalysisAdmission,
        label="analysis admission payload",
        required_fields=("status", "reason", "basis", "version"),
    )
    return {
        "status": _required_payload_text(payload, "status", label="analysis admission payload"),
        "reason": _required_payload_text(payload, "reason", label="analysis admission payload"),
        "basis": _required_payload_mapping(payload, "basis", label="analysis admission payload"),
        "version": _required_payload_text(payload, "version", label="analysis admission payload"),
    }


def _story_identity_payload(value: NewsStoryIdentity | Mapping[str, object]) -> dict[str, object]:
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
    value: NewsAnalysisAdmission | NewsStoryIdentity | Mapping[str, object],
    *,
    expected_type: type[NewsAnalysisAdmission] | type[NewsStoryIdentity],
    label: str,
    required_fields: tuple[str, ...],
) -> dict[str, object]:
    if isinstance(value, Mapping):
        payload = dict(value)
    elif isinstance(value, expected_type):
        payload = dict(asdict(value))
    else:
        raise ValueError(f"unsupported {label} shape")
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


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["NewsItemProcessWorker"]
