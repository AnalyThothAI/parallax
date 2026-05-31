from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefAgentConfig,
    NewsItemBriefConstraints,
    NewsItemBriefContextItem,
    NewsItemBriefFactLane,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefProviderSignalEvidence,
    NewsItemBriefProviderTokenImpact,
    NewsItemBriefSource,
    NewsItemBriefTokenLane,
)
from parallax.platform.agent_hashing import json_sha256

BODY_EXCERPT_MAX_CHARS = 2000
MAX_TOKEN_LANES = 50
MAX_FACT_LANES = 50
MAX_CONTEXT_ITEMS = 8
CONTEXT_BODY_EXCERPT_MAX_CHARS = 500
MAX_PROVIDER_TOKEN_IMPACTS = 12
MAX_PROVIDER_AGGREGATION_VALUES = 12
PROVIDER_SUMMARY_MAX_CHARS = 600


def build_news_item_brief_input_packet(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    agent_config: NewsItemBriefAgentConfig,
    context_items: Sequence[Mapping[str, Any]] = (),
) -> NewsItemBriefInputPacket:
    news_item = NewsItemBriefNewsItem(
        news_item_id=_str(item.get("news_item_id")),
        title=_bounded(item.get("title"), 500),
        summary=_bounded(item.get("summary"), 2000),
        body_excerpt=_bounded(item.get("body_text") or item.get("body_excerpt"), BODY_EXCERPT_MAX_CHARS),
        canonical_url=_bounded(item.get("canonical_url"), 2000),
        published_at_ms=_int(item.get("published_at_ms")),
        content_hash=_bounded(item.get("content_hash"), 160),
        source=NewsItemBriefSource(
            source_domain=_bounded(item.get("source_domain"), 255),
            source_name=_bounded(item.get("source_name"), 255),
            source_role=_bounded(item.get("source_role"), 64),
            trust_tier=_bounded(item.get("trust_tier"), 64),
        ),
    )
    token_lanes = [_token_lane(row) for row in sorted(token_mentions, key=_mention_sort_key)[:MAX_TOKEN_LANES]]
    fact_lanes = [_fact_lane(row) for row in sorted(fact_candidates, key=_fact_sort_key)[:MAX_FACT_LANES]]
    context_item_lanes = _context_items(context_items or _json_list(item.get("context_items")))
    provider_signal_evidence = _provider_signal_evidence(item)
    evidence_refs = _evidence_refs(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        context_items=context_item_lanes,
        provider_signal_evidence=provider_signal_evidence,
    )
    packet_id = _packet_id(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        context_items=context_item_lanes,
        provider_signal_evidence=provider_signal_evidence,
        agent_config=agent_config,
    )
    packet = NewsItemBriefInputPacket(
        packet_id=packet_id,
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        context_items=context_item_lanes,
        provider_signal_evidence=provider_signal_evidence,
        evidence_refs=evidence_refs,
        constraints=NewsItemBriefConstraints(),
        prompt_version=agent_config.prompt_version,
        schema_version=agent_config.schema_version,
    )
    return packet.model_copy(update={"input_hash": news_item_brief_material_input_hash(packet)})


def news_item_brief_material_input_payload(packet: NewsItemBriefInputPacket) -> dict[str, Any]:
    return packet.model_dump(
        mode="json",
        exclude={
            "input_hash",
        },
    )


def news_item_brief_material_input_hash(packet: NewsItemBriefInputPacket) -> str:
    return json_sha256(news_item_brief_material_input_payload(packet))


def _token_lane(row: Mapping[str, Any]) -> NewsItemBriefTokenLane:
    return NewsItemBriefTokenLane(
        mention_id=_str(row.get("mention_id")),
        observed_symbol=_bounded(row.get("observed_symbol"), 64),
        resolution_status=_bounded(row.get("resolution_status"), 64),
        target_type=_optional_bounded(row.get("target_type"), 80),
        target_id=_optional_bounded(row.get("target_id"), 160),
        display_symbol=_bounded(row.get("display_symbol") or row.get("observed_symbol"), 64),
        display_name=_optional_bounded(row.get("display_name"), 160),
        reason_codes=[_bounded(value, 80) for value in _json_list(row.get("reason_codes_json"))[:12]],
        candidate_targets=[_json_object(value) for value in _json_list(row.get("candidate_targets_json"))[:12]],
        evidence_strength=_optional_bounded(row.get("evidence_strength"), 64),
        confidence=_optional_float(row.get("confidence")),
    )


def _fact_lane(row: Mapping[str, Any]) -> NewsItemBriefFactLane:
    return NewsItemBriefFactLane(
        fact_candidate_id=_str(row.get("fact_candidate_id")),
        event_type=_bounded(row.get("event_type"), 80),
        claim=_bounded(row.get("claim"), 800),
        realis=_bounded(row.get("realis"), 64),
        validation_status=_bounded(row.get("validation_status"), 64),
        affected_targets=[_json_object(value) for value in _json_list(row.get("affected_targets_json"))[:20]],
        rejection_reasons=[_bounded(value, 120) for value in _json_list(row.get("rejection_reasons_json"))[:12]],
        evidence_quote=_bounded(row.get("evidence_quote"), 500),
    )


def _context_items(rows: Sequence[Any]) -> list[NewsItemBriefContextItem]:
    context_items: list[NewsItemBriefContextItem] = []
    for row in sorted(rows, key=_context_item_sort_key)[:MAX_CONTEXT_ITEMS]:
        payload = _json_object(row)
        context_item_id = _str(payload.get("context_item_id"))
        if not context_item_id:
            continue
        context_items.append(
            NewsItemBriefContextItem(
                context_item_id=context_item_id,
                context_type=_bounded(payload.get("context_type"), 64),
                author=_optional_bounded(payload.get("author"), 255),
                canonical_url=_optional_bounded(payload.get("canonical_url"), 2000),
                body_excerpt=_bounded(
                    payload.get("body_text") or payload.get("body_excerpt"),
                    CONTEXT_BODY_EXCERPT_MAX_CHARS,
                ),
                published_at_ms=_optional_int(payload.get("published_at_ms")),
                engagement=_json_object(payload.get("engagement_json") or payload.get("engagement")),
            )
        )
    return context_items


def _context_item_sort_key(row: Any) -> tuple[int, int, str]:
    payload = _json_object(row)
    published_at_ms = _optional_int(payload.get("published_at_ms"))
    return (published_at_ms is None, -(published_at_ms or 0), _str(payload.get("context_item_id")))


def _provider_signal_evidence(item: Mapping[str, Any]) -> NewsItemBriefProviderSignalEvidence | None:
    provider_signal = _json_object(item.get("provider_signal_json") or item.get("provider_signal"))
    provider_impacts = [
        impact
        for impact in (
            _provider_token_impact(row)
            for row in _json_list(item.get("provider_token_impacts_json") or item.get("provider_token_impacts"))
        )
        if impact is not None
    ]
    has_provider_signal = str(provider_signal.get("source") or "").strip().lower() == "provider"
    if not has_provider_signal and not provider_impacts:
        return None
    return NewsItemBriefProviderSignalEvidence(
        source=_bounded(provider_signal.get("source") or "provider", 64),
        provider=_bounded(provider_signal.get("provider") or "opennews", 64),
        status=_bounded(provider_signal.get("status") or "partial", 32),
        direction=_provider_direction(provider_signal.get("direction") or provider_signal.get("signal")),
        signal=_optional_bounded(provider_signal.get("signal"), 32),
        score=_optional_score(provider_signal.get("score")),
        grade=_optional_bounded(provider_signal.get("grade"), 32),
        summary_zh=_bounded(provider_signal.get("summary_zh"), PROVIDER_SUMMARY_MAX_CHARS),
        summary_en=_bounded(provider_signal.get("summary_en"), PROVIDER_SUMMARY_MAX_CHARS),
        method=_bounded(provider_signal.get("method") or "provider.signal", 128),
        token_impacts=sorted(provider_impacts, key=_provider_impact_sort_key)[:MAX_PROVIDER_TOKEN_IMPACTS],
        duplicate_count=_bounded_count(item.get("duplicate_count")),
        source_ids=_bounded_string_list(item.get("source_ids_json") or item.get("source_ids"), 160),
        source_domains=_bounded_string_list(item.get("source_domains_json") or item.get("source_domains"), 255),
        provider_article_keys=_bounded_string_list(
            item.get("provider_article_keys_json") or item.get("provider_article_keys"),
            255,
        ),
    )


def _provider_token_impact(row: Any) -> NewsItemBriefProviderTokenImpact | None:
    payload = _json_object(row)
    symbol = _bounded(payload.get("symbol"), 32).upper()
    if not symbol:
        return None
    signal = _optional_bounded(payload.get("signal"), 32)
    return NewsItemBriefProviderTokenImpact(
        symbol=symbol,
        market_type=_optional_bounded(payload.get("market_type"), 64),
        score=_optional_score(payload.get("score")),
        direction=_provider_direction(payload.get("direction") or signal),
        signal=signal,
        grade=_optional_bounded(payload.get("grade"), 32),
    )


def _provider_impact_sort_key(row: NewsItemBriefProviderTokenImpact) -> tuple[int, str]:
    return (-(row.score if row.score is not None else -1), row.symbol)


def _evidence_refs(
    *,
    news_item: NewsItemBriefNewsItem,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
    context_items: list[NewsItemBriefContextItem],
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None,
) -> list[str]:
    refs: list[str] = []
    if news_item.title:
        refs.append("item:title")
    if news_item.summary:
        refs.append("item:summary")
    if news_item.body_excerpt:
        refs.append("item:body_excerpt")
    refs.extend(f"fact:{row.fact_candidate_id}" for row in fact_lanes if row.fact_candidate_id)
    refs.extend(f"token:{row.mention_id}" for row in token_lanes if row.mention_id)
    refs.extend(f"context:{row.context_item_id}" for row in context_items if row.context_item_id)
    if provider_signal_evidence is not None:
        refs.append("provider:signal")
        refs.extend(f"provider:token:{row.symbol}" for row in provider_signal_evidence.token_impacts if row.symbol)
    return _stable_unique(refs)


def _packet_id(
    *,
    news_item: NewsItemBriefNewsItem,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
    context_items: list[NewsItemBriefContextItem],
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None,
    agent_config: NewsItemBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "news_item_id": news_item.news_item_id,
            "content_hash": news_item.content_hash,
            "tokens": [row.mention_id for row in token_lanes],
            "facts": [row.fact_candidate_id for row in fact_lanes],
            "context_items": [row.context_item_id for row in context_items],
            "provider_signal_evidence": provider_signal_evidence.model_dump(mode="json")
            if provider_signal_evidence is not None
            else None,
            "prompt_version": agent_config.prompt_version,
            "schema_version": agent_config.schema_version,
        }
    )
    return f"news-item-brief:{news_item.news_item_id}:{digest.removeprefix('sha256:')[:16]}"


def _mention_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_str(row.get("mention_id")), _str(row.get("observed_symbol")))


def _fact_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_str(row.get("fact_candidate_id")), _str(row.get("claim")))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return []


def _json_object(value: Any) -> dict[str, object]:
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return _json_object(parsed)
    if isinstance(value, Mapping):
        return {str(key): child for key, child in value.items() if child is not None}
    return {}


def _stable_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bounded(value: Any, max_length: int) -> str:
    return _str(value)[:max_length]


def _optional_bounded(value: Any, max_length: int) -> str | None:
    cleaned = _bounded(value, max_length)
    return cleaned or None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    parsed = _int(value)
    return parsed if parsed else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, parsed))


def _optional_score(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, parsed))


def _bounded_count(value: Any) -> int:
    return max(1, min(1000, _int(value) or 1))


def _provider_direction(value: Any) -> str:
    normalized = _str(value).lower()
    if normalized in {"bullish", "long"}:
        return "bullish"
    if normalized in {"bearish", "short"}:
        return "bearish"
    if normalized == "mixed":
        return "mixed"
    return "neutral"


def _bounded_string_list(value: Any, max_length: int) -> list[str]:
    return [cleaned for cleaned in (_bounded(item, max_length) for item in _json_list(value)) if cleaned][
        :MAX_PROVIDER_AGGREGATION_VALUES
    ]


__all__ = [
    "BODY_EXCERPT_MAX_CHARS",
    "build_news_item_brief_input_packet",
    "news_item_brief_material_input_hash",
    "news_item_brief_material_input_payload",
]
