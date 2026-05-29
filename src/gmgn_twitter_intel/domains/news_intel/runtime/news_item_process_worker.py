from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.services.news_content_classification import classify_news_item_content
from gmgn_twitter_intel.domains.news_intel.services.news_entity_extraction import NewsEntity, extract_news_entities
from gmgn_twitter_intel.domains.news_intel.services.news_fact_candidates import build_fact_candidates
from gmgn_twitter_intel.domains.news_intel.services.news_item_agent_policy import (
    needs_news_item_agent_brief,
    news_item_agent_brief_priority,
)
from gmgn_twitter_intel.domains.news_intel.services.news_token_mentions import build_news_token_mentions
from gmgn_twitter_intel.domains.token_intel.interfaces import TokenIdentityLookup


class NewsItemProcessWorker(WorkerBase):
    def __init__(
        self,
        *,
        identity_lookup: TokenIdentityLookup | None = None,
        wake_bus: Any | None = None,
        source_quality_windows: Iterable[str] | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.identity_lookup = identity_lookup
        self.wake_bus = wake_bus
        self.source_quality_windows = _source_quality_windows(source_quality_windows)
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
                    repos.news.mark_item_processed(news_item_id=news_item_id, processed_at_ms=now, commit=False)
                    repos.news_projection_dirty_targets.enqueue_targets(
                        _dirty_targets_for_processed_item(
                            item=item_payload,
                            news_item_id=news_item_id,
                            source_quality_windows=self.source_quality_windows,
                        ),
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


def _dirty_targets_for_processed_item(
    *,
    item: Mapping[str, Any],
    news_item_id: str,
    source_quality_windows: Iterable[str],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = [
        {"projection_name": "story", "target_kind": "news_item", "target_id": news_item_id},
        {"projection_name": "page", "target_kind": "news_item", "target_id": news_item_id},
    ]
    if _needs_agent_brief(item):
        targets.append(
            {
                "projection_name": "brief_input",
                "target_kind": "news_item",
                "target_id": news_item_id,
                "priority": news_item_agent_brief_priority(item),
            }
        )
    targets.extend(
        {
            "projection_name": "source_quality",
            "target_kind": "source",
            "target_id": str(item["source_id"]),
            "window": window,
        }
        for window in source_quality_windows
    )
    return targets


def _needs_agent_brief(item: Mapping[str, Any]) -> bool:
    return needs_news_item_agent_brief(item)


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


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or ("24h", "7d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


__all__ = ["NewsItemProcessWorker"]
