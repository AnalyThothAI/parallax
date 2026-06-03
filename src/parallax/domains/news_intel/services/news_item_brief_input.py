from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    NewsContextTargetRef,
    NewsItemBriefAgentConfig,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefConstraints,
    NewsItemBriefFactLane,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefProviderSignalEvidence,
    NewsItemBriefProviderTokenImpact,
    NewsItemBriefSource,
    NewsItemBriefSynthesisPacket,
    NewsItemBriefTokenLane,
    news_item_brief_base_material_identity,
    news_research_tool_material_identity,
)
from parallax.platform.agent_hashing import json_sha256

BODY_EXCERPT_MAX_CHARS = 2000
MAX_TOKEN_LANES = 50
MAX_FACT_LANES = 50
MAX_PROVIDER_TOKEN_IMPACTS = 12
MAX_PROVIDER_AGGREGATION_VALUES = 12
PROVIDER_SUMMARY_MAX_CHARS = 600
DEFAULT_BASE_MATERIAL_BUDGET_CHARS = 12_000
RESOLVED_TOKEN_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})


def build_news_item_brief_input_packet(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    agent_config: NewsItemBriefAgentConfig,
) -> NewsItemBriefInputPacket:
    news_item = NewsItemBriefNewsItem(
        news_item_id=_str(item.get("news_item_id")),
        title=_bounded(item.get("title"), 500),
        summary=_bounded(item.get("summary"), 2000),
        body_excerpt=_bounded(item.get("body_text"), BODY_EXCERPT_MAX_CHARS),
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
    provider_signal_evidence = _provider_signal_evidence(item)
    evidence_refs = _evidence_refs(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
    )
    packet_id = _packet_id(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
        agent_config=agent_config,
    )
    packet = NewsItemBriefInputPacket(
        packet_id=packet_id,
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
        evidence_refs=evidence_refs,
        constraints=NewsItemBriefConstraints(),
        prompt_version=agent_config.prompt_version,
        schema_version=agent_config.schema_version,
    )
    return packet.model_copy(update={"input_hash": news_item_brief_material_input_hash(packet)})


def build_news_item_brief_base_packet(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    agent_config: NewsItemBriefAgentConfig,
    material_budget_chars: int = DEFAULT_BASE_MATERIAL_BUDGET_CHARS,
) -> NewsItemBriefBasePacket:
    news_item = _news_item(item)
    original_token_count = len(token_mentions)
    original_fact_count = len(fact_candidates)
    token_lanes = [_token_lane(row) for row in sorted(token_mentions, key=_mention_sort_key)[:MAX_TOKEN_LANES]]
    fact_lanes = [_fact_lane(row) for row in sorted(fact_candidates, key=_fact_sort_key)[:MAX_FACT_LANES]]
    provider_signal_evidence = _provider_signal_evidence(item)
    truncation_reasons: list[str] = []
    if original_token_count > len(token_lanes):
        truncation_reasons.append("token_lanes_budget")
    if original_fact_count > len(fact_lanes):
        truncation_reasons.append("fact_lanes_budget")
    if any(
        not _is_resolved_token_status(row.get("resolution_status"))
        or not (_str(row.get("target_type")) and _str(row.get("target_id")))
        for row in token_mentions
    ):
        truncation_reasons.append("unresolved_mentions_excluded")

    material_budget = max(0, int(material_budget_chars))
    content_class = _content_class(item)
    packet_id = _packet_id(
        news_item=news_item,
        token_lanes=token_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
        agent_config=agent_config,
    ).replace("news-item-brief:", "news-item-brief-base:", 1)

    def make_packet(
        *,
        tokens: list[NewsItemBriefTokenLane],
        facts: list[NewsItemBriefFactLane],
        reasons: list[str],
        material_chars: int = 0,
    ) -> NewsItemBriefBasePacket:
        report = NewsItemBriefBudgetReport(
            material_budget_chars=material_budget,
            material_chars=material_chars,
            original_token_count=original_token_count,
            kept_token_count=len(tokens),
            original_fact_count=original_fact_count,
            kept_fact_count=len(facts),
            truncation_reasons=_stable_unique(reasons),
        )
        return NewsItemBriefBasePacket(
            packet_id=packet_id,
            news_item=news_item,
            token_lanes=tokens,
            fact_lanes=facts,
            provider_signal_evidence=provider_signal_evidence,
            evidence_refs=_evidence_refs(
                news_item=news_item,
                token_lanes=tokens,
                fact_lanes=facts,
                provider_signal_evidence=provider_signal_evidence,
            ),
            constraints=NewsItemBriefConstraints(),
            allowed_context_targets=_allowed_context_targets(tokens),
            content_class=content_class,
            base_budget_report=report,
            prompt_version=agent_config.prompt_version,
            schema_version=agent_config.schema_version,
        )

    kept_tokens = list(token_lanes)
    kept_facts = list(fact_lanes)
    packet = make_packet(tokens=kept_tokens, facts=kept_facts, reasons=truncation_reasons)
    material_chars = _material_chars(news_item_brief_base_material_identity(packet))
    if material_budget and material_chars > material_budget:
        truncation_reasons.append("material_budget")
        while material_chars > material_budget and (kept_facts or kept_tokens):
            if kept_facts:
                kept_facts = kept_facts[:-1]
            else:
                kept_tokens = kept_tokens[:-1]
            packet = make_packet(tokens=kept_tokens, facts=kept_facts, reasons=truncation_reasons)
            material_chars = _material_chars(news_item_brief_base_material_identity(packet))
    packet = make_packet(
        tokens=kept_tokens,
        facts=kept_facts,
        reasons=truncation_reasons,
        material_chars=material_chars,
    )
    for _ in range(5):
        final_chars = _material_chars(news_item_brief_base_material_identity(packet))
        if final_chars == packet.base_budget_report.material_chars:
            break
        if material_budget and final_chars > material_budget and (kept_facts or kept_tokens):
            truncation_reasons.append("material_budget")
            if kept_facts:
                kept_facts = kept_facts[:-1]
            else:
                kept_tokens = kept_tokens[:-1]
        packet = make_packet(
            tokens=kept_tokens,
            facts=kept_facts,
            reasons=truncation_reasons,
            material_chars=final_chars,
        )
    return packet.model_copy(update={"input_hash": news_item_brief_base_material_input_hash(packet)})


def news_item_brief_material_input_payload(packet: NewsItemBriefInputPacket) -> dict[str, Any]:
    return packet.model_dump(
        mode="json",
        exclude={
            "input_hash",
        },
    )


def news_item_brief_material_input_hash(packet: NewsItemBriefInputPacket) -> str:
    return json_sha256(news_item_brief_material_input_payload(packet))


def news_item_brief_base_material_input_hash(packet: NewsItemBriefBasePacket) -> str:
    return json_sha256(news_item_brief_base_material_identity(packet))


def news_item_brief_synthesis_material_payload(packet: NewsItemBriefSynthesisPacket) -> dict[str, Any]:
    research_material = {
        "research_plan": packet.research_plan.model_dump(mode="json"),
        "tool_results": [news_research_tool_material_identity(result) for result in packet.tool_results],
        "tool_catalog_version": NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    }
    return {
        "base_packet": news_item_brief_base_material_identity(packet.base_packet),
        "research_packet": {
            **research_material,
            "research_packet_hash": json_sha256(research_material),
        },
    }


def news_item_brief_synthesis_material_hash(packet: NewsItemBriefSynthesisPacket) -> str:
    return json_sha256(news_item_brief_synthesis_material_payload(packet))


def _news_item(item: Mapping[str, Any]) -> NewsItemBriefNewsItem:
    return NewsItemBriefNewsItem(
        news_item_id=_str(item.get("news_item_id")),
        title=_bounded(item.get("title"), 500),
        summary=_bounded(item.get("summary"), 2000),
        body_excerpt=_bounded(item.get("body_text"), BODY_EXCERPT_MAX_CHARS),
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


def _provider_signal_evidence(item: Mapping[str, Any]) -> NewsItemBriefProviderSignalEvidence | None:
    provider_signal = _json_object(item.get("provider_signal_json"))
    provider_impacts = [
        impact
        for impact in (
            _provider_token_impact(row) for row in _json_list(item.get("provider_token_impacts_json"))
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
        source_ids=_bounded_string_list(item.get("source_ids_json"), 160),
        source_domains=_bounded_string_list(item.get("source_domains_json"), 255),
        provider_article_keys=_bounded_string_list(
            item.get("provider_article_keys_json"),
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


def _allowed_context_targets(token_lanes: Sequence[NewsItemBriefTokenLane]) -> list[NewsContextTargetRef]:
    refs: list[NewsContextTargetRef] = []
    seen: set[tuple[str, str]] = set()
    for lane in token_lanes:
        resolution_status = _bounded(lane.resolution_status, 64)
        if not _is_resolved_token_status(resolution_status):
            continue
        target_type = _str(lane.target_type)
        target_id = _str(lane.target_id)
        if not target_type or not target_id:
            continue
        key = (target_type, target_id)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            NewsContextTargetRef(
                target_type=target_type,
                target_id=target_id,
                display_symbol=_bounded(lane.display_symbol or lane.observed_symbol, 64),
                resolution_status=resolution_status,
                confidence=lane.confidence,
                target_scope=_target_scope(target_type),
            )
        )
    return refs


def _is_resolved_token_status(value: Any) -> bool:
    return _str(value).lower() in RESOLVED_TOKEN_STATUSES


def _target_scope(target_type: str) -> str:
    lowered = target_type.strip().lower()
    if any(marker in lowered for marker in ("asset", "token", "cex", "crypto")):
        return "crypto"
    if lowered:
        return "non_crypto"
    return "unknown"


def _content_class(item: Mapping[str, Any]) -> str | None:
    direct = _optional_bounded(item.get("content_class"), 80)
    if direct:
        return direct
    classification = _json_object(item.get("content_classification_json"))
    for key in ("content_class", "class", "label"):
        value = _optional_bounded(classification.get(key), 80)
        if value:
            return value
    return None


def _material_chars(payload: Mapping[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _provider_impact_sort_key(row: NewsItemBriefProviderTokenImpact) -> tuple[int, str]:
    return (-(row.score if row.score is not None else -1), row.symbol)


def _evidence_refs(
    *,
    news_item: NewsItemBriefNewsItem,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
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
    if provider_signal_evidence is not None:
        refs.append("provider:signal")
        refs.extend(f"provider:token:{row.symbol}" for row in provider_signal_evidence.token_impacts if row.symbol)
    return _stable_unique(refs)


def _packet_id(
    *,
    news_item: NewsItemBriefNewsItem,
    token_lanes: list[NewsItemBriefTokenLane],
    fact_lanes: list[NewsItemBriefFactLane],
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None,
    agent_config: NewsItemBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "news_item_id": news_item.news_item_id,
            "content_hash": news_item.content_hash,
            "tokens": [row.mention_id for row in token_lanes],
            "facts": [row.fact_candidate_id for row in fact_lanes],
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
    "DEFAULT_BASE_MATERIAL_BUDGET_CHARS",
    "build_news_item_brief_base_packet",
    "build_news_item_brief_input_packet",
    "news_item_brief_base_material_input_hash",
    "news_item_brief_material_input_hash",
    "news_item_brief_material_input_payload",
    "news_item_brief_synthesis_material_hash",
    "news_item_brief_synthesis_material_payload",
]
