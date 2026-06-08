from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import (
    NewsItemBriefAgentConfig,
    NewsItemBriefConstraints,
    NewsItemBriefEntityLane,
    NewsItemBriefFactLane,
    NewsItemBriefInputPacket,
    NewsItemBriefNewsItem,
    NewsItemBriefProviderMarketImpact,
    NewsItemBriefProviderSignalEvidence,
    NewsItemBriefSource,
)
from parallax.platform.agent_hashing import json_sha256

BODY_EXCERPT_MAX_CHARS = 2000
MAX_ENTITY_LANES = 50
MAX_FACT_LANES = 50
MAX_PROVIDER_MARKET_IMPACTS = 12
MAX_PROVIDER_AGGREGATION_VALUES = 12
PROVIDER_SUMMARY_MAX_CHARS = 600

_NEWS_MARKET_DOMAINS = frozenset(
    {
        "crypto",
        "us_equity",
        "macro_rates",
        "energy_geopolitics",
        "ai_semiconductors",
        "regulation",
        "private_company",
        "commodity",
        "fx",
        "unknown",
    }
)
_NEWS_ENTITY_TYPES = frozenset(
    {
        "crypto_asset",
        "equity",
        "company",
        "private_company",
        "regulator",
        "country",
        "commodity",
        "macro_factor",
        "sector",
        "other",
    }
)


def build_news_item_brief_input_packet(
    *,
    item: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]] = (),
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
    entity_lanes = _entity_lanes(entities=entities, token_mentions=token_mentions)
    fact_lanes = [_fact_lane(row) for row in sorted(fact_candidates, key=_fact_sort_key)[:MAX_FACT_LANES]]
    provider_signal_evidence = _provider_signal_evidence(item)
    event_type = _optional_bounded(item.get("event_type"), 80)
    agent_admission = _agent_admission(item)
    similarity = _context_object(item, "similarity_json", "similarity", fallback=agent_admission.get("similarity"))
    material_delta = _context_object(
        item,
        "material_delta_json",
        "material_delta",
        fallback=agent_admission.get("material_delta"),
    )
    market_scope = _market_scope(
        item=item,
        agent_admission=agent_admission,
        provider_signal_evidence=provider_signal_evidence,
        entity_lanes=entity_lanes,
    )
    evidence_refs = _evidence_refs(
        news_item=news_item,
        entity_lanes=entity_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
    )
    packet_id = _packet_id(
        news_item=news_item,
        event_type=event_type,
        entity_lanes=entity_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
        market_scope=market_scope,
        agent_admission=agent_admission,
        similarity=similarity,
        material_delta=material_delta,
        agent_config=agent_config,
    )
    packet = NewsItemBriefInputPacket(
        packet_id=packet_id,
        news_item=news_item,
        event_type=event_type,
        entity_lanes=entity_lanes,
        fact_lanes=fact_lanes,
        provider_signal_evidence=provider_signal_evidence,
        market_scope=market_scope,
        agent_admission=agent_admission,
        similarity=similarity,
        material_delta=material_delta,
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


def _entity_lanes(
    *,
    entities: Sequence[Mapping[str, Any]],
    token_mentions: Sequence[Mapping[str, Any]],
) -> list[NewsItemBriefEntityLane]:
    lanes = [
        lane
        for lane in ([_entity_lane(row) for row in entities] + [_token_entity_lane(row) for row in token_mentions])
        if lane is not None
    ]
    result: list[NewsItemBriefEntityLane] = []
    seen: set[str] = set()
    for lane in sorted(lanes, key=lambda row: (row.entity_id, row.observed_label)):
        if lane.entity_id in seen:
            continue
        seen.add(lane.entity_id)
        result.append(lane)
        if len(result) >= MAX_ENTITY_LANES:
            break
    return result


def _entity_lane(row: Mapping[str, Any]) -> NewsItemBriefEntityLane | None:
    observed_label = _bounded(
        row.get("observed_label")
        or row.get("raw_value")
        or row.get("label")
        or row.get("display_name")
        or row.get("name")
        or row.get("normalized_value"),
        160,
    )
    entity_id = _bounded(row.get("entity_id") or row.get("target_id") or observed_label, 160)
    if not entity_id:
        return None
    entity_type = _entity_type(row.get("entity_type"))
    market_domain = _market_domain(row.get("market_domain")) or _domain_for_entity(entity_type, row)
    return NewsItemBriefEntityLane(
        entity_id=entity_id,
        observed_label=observed_label,
        display_symbol=_optional_bounded(row.get("display_symbol") or row.get("symbol"), 64),
        display_name=_optional_bounded(row.get("display_name") or row.get("name"), 160),
        entity_type=entity_type,
        market_domain=market_domain,
        resolution_status=_bounded(row.get("resolution_status") or "observed", 64),
        target_type=_optional_bounded(row.get("target_type"), 80),
        target_id=_optional_bounded(row.get("target_id"), 160),
        role=_bounded(row.get("role") or row.get("text_surface") or "mentioned", 64),
        confidence=_optional_float(row.get("confidence")),
        evidence_refs=[f"entity:{entity_id}"],
        candidate_targets=[_json_object(value) for value in _json_list(row.get("candidate_targets_json"))[:12]],
    )


def _token_entity_lane(row: Mapping[str, Any]) -> NewsItemBriefEntityLane | None:
    mention_id = _bounded(row.get("mention_id"), 160)
    if not mention_id:
        return None
    observed_symbol = _bounded(row.get("observed_symbol"), 64)
    target_type = _optional_bounded(row.get("target_type"), 80)
    target_id = _optional_bounded(row.get("target_id"), 160)
    candidate_targets = [_json_object(value) for value in _json_list(row.get("candidate_targets_json"))[:12]]
    market_domain = _token_mention_market_domain(
        target_id=target_id,
        target_type=target_type,
        candidate_targets=candidate_targets,
        resolution_status=row.get("resolution_status"),
    )
    return NewsItemBriefEntityLane(
        entity_id=mention_id,
        observed_label=observed_symbol,
        display_symbol=_optional_bounded(row.get("display_symbol") or observed_symbol, 64),
        display_name=_optional_bounded(row.get("display_name"), 160),
        entity_type=_token_mention_entity_type(market_domain),
        market_domain=market_domain,
        resolution_status=_bounded(row.get("resolution_status") or "unknown", 64),
        target_type=target_type,
        target_id=target_id,
        role="token_mention",
        confidence=_optional_float(row.get("confidence")),
        evidence_refs=[f"entity:{mention_id}"],
        candidate_targets=candidate_targets,
    )


def _token_mention_market_domain(
    *,
    target_id: str | None,
    target_type: str | None,
    candidate_targets: Sequence[Mapping[str, object]],
    resolution_status: Any,
) -> str:
    domains = _target_domains(target_id=target_id, target_type=target_type)
    for target in candidate_targets:
        domains.extend(_target_domains(target_id=target.get("target_id"), target_type=target.get("target_type")))
    for domain in domains:
        if domain != "unknown":
            return domain
    if _str(resolution_status).lower().replace("-", "_") == "non_crypto":
        return "unknown"
    return "crypto"


def _token_mention_entity_type(market_domain: str) -> str:
    if market_domain == "us_equity":
        return "equity"
    if market_domain == "private_company":
        return "private_company"
    if market_domain == "commodity":
        return "commodity"
    if market_domain == "fx":
        return "macro_factor"
    if market_domain == "crypto":
        return "crypto_asset"
    return "other"


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
        for impact in (_provider_market_impact(row) for row in _json_list(item.get("provider_token_impacts_json")))
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
        market_impacts=sorted(provider_impacts, key=_provider_impact_sort_key)[:MAX_PROVIDER_MARKET_IMPACTS],
        duplicate_count=_bounded_count(item.get("duplicate_count")),
        source_ids=_bounded_string_list(item.get("source_ids_json"), 160),
        source_domains=_bounded_string_list(item.get("source_domains_json"), 255),
        provider_article_keys=_bounded_string_list(
            item.get("provider_article_keys_json"),
            255,
        ),
    )


def _provider_market_impact(row: Any) -> NewsItemBriefProviderMarketImpact | None:
    payload = _json_object(row)
    label = _bounded(payload.get("label") or payload.get("symbol") or payload.get("name"), 160).upper()
    if not label:
        return None
    symbol = _optional_bounded(payload.get("symbol"), 64)
    signal = _optional_bounded(payload.get("signal"), 32)
    return NewsItemBriefProviderMarketImpact(
        label=label,
        symbol=symbol.upper() if symbol else None,
        market_type=_optional_bounded(payload.get("market_type"), 64),
        score=_optional_score(payload.get("score")),
        direction=_provider_direction(payload.get("direction") or signal),
        signal=signal,
        grade=_optional_bounded(payload.get("grade"), 32),
    )


def _provider_impact_sort_key(row: NewsItemBriefProviderMarketImpact) -> tuple[int, str]:
    return (-(row.score if row.score is not None else -1), row.label)


def _evidence_refs(
    *,
    news_item: NewsItemBriefNewsItem,
    entity_lanes: list[NewsItemBriefEntityLane],
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
    refs.extend(f"entity:{row.entity_id}" for row in entity_lanes if row.entity_id)
    if provider_signal_evidence is not None:
        refs.append("provider:signal")
        refs.extend(f"provider:impact:{row.label}" for row in provider_signal_evidence.market_impacts if row.label)
    return _stable_unique(refs)


def _packet_id(
    *,
    news_item: NewsItemBriefNewsItem,
    event_type: str | None,
    entity_lanes: list[NewsItemBriefEntityLane],
    fact_lanes: list[NewsItemBriefFactLane],
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None,
    market_scope: list[str],
    agent_admission: dict[str, object],
    similarity: dict[str, object],
    material_delta: dict[str, object],
    agent_config: NewsItemBriefAgentConfig,
) -> str:
    digest = json_sha256(
        {
            "news_item_id": news_item.news_item_id,
            "content_hash": news_item.content_hash,
            "event_type": event_type,
            "entities": [row.entity_id for row in entity_lanes],
            "facts": [row.fact_candidate_id for row in fact_lanes],
            "provider_signal_evidence": provider_signal_evidence.model_dump(mode="json")
            if provider_signal_evidence is not None
            else None,
            "market_scope": market_scope,
            "agent_admission": agent_admission,
            "similarity": similarity,
            "material_delta": material_delta,
            "prompt_version": agent_config.prompt_version,
            "schema_version": agent_config.schema_version,
        }
    )
    return f"news-item-brief:{news_item.news_item_id}:{digest.removeprefix('sha256:')[:16]}"


def _market_scope(
    *,
    item: Mapping[str, Any],
    agent_admission: Mapping[str, object],
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None,
    entity_lanes: list[NewsItemBriefEntityLane],
) -> list[str]:
    explicit = _market_domain_list(item.get("market_scope_json") or item.get("market_scope"))
    if explicit:
        return _stable_unique(explicit)[:12]
    admitted = _agent_admission_market_scope(agent_admission)
    provider_domains = _provider_market_scope(provider_signal_evidence)
    inferred = [lane.market_domain for lane in entity_lanes if lane.market_domain != "unknown"]
    return _stable_unique([*admitted, *provider_domains, *inferred])[:12]


def _agent_admission_market_scope(agent_admission: Mapping[str, object]) -> list[str]:
    basis = _json_object(agent_admission.get("basis"))
    return _market_domain_list(basis.get("market_scope"))


def _provider_market_scope(provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None) -> list[str]:
    if provider_signal_evidence is None:
        return []
    return [
        domain
        for domain in (_market_domain(impact.market_type) for impact in provider_signal_evidence.market_impacts)
        if domain
    ]


def _market_domain_list(value: Any) -> list[str]:
    if isinstance(value, str):
        direct = _market_domain(value)
        if direct:
            return [direct]
    return [domain for domain in (_market_domain(raw) for raw in _json_list(value)) if domain]


def _agent_admission(item: Mapping[str, Any]) -> dict[str, object]:
    admission = _context_object(item, "agent_admission_json", "agent_admission")
    status = _bounded(item.get("agent_admission_status"), 64)
    reason = _bounded(item.get("agent_admission_reason"), 160)
    if status and "status" not in admission:
        admission["status"] = status
    if reason and "reason" not in admission:
        admission["reason"] = reason
    representative = _bounded(item.get("agent_representative_news_item_id"), 160)
    if representative and "representative_news_item_id" not in admission:
        admission["representative_news_item_id"] = representative
    return admission


def _context_object(
    item: Mapping[str, Any],
    json_key: str,
    object_key: str,
    *,
    fallback: Any = None,
) -> dict[str, object]:
    value = item.get(json_key)
    if value is None:
        value = item.get(object_key)
    if value is None:
        value = fallback
    return _bounded_json_object(value)


def _entity_type(value: Any) -> str:
    normalized = _str(value).lower().replace("-", "_")
    if normalized in _NEWS_ENTITY_TYPES:
        return normalized
    aliases = {
        "asset": "crypto_asset",
        "ca": "crypto_asset",
        "contract": "crypto_asset",
        "contract_address": "crypto_asset",
        "coin": "crypto_asset",
        "token": "crypto_asset",
        "equity_symbol": "equity",
        "ticker": "equity",
        "stock": "equity",
        "public_company": "company",
        "org": "company",
        "organization": "company",
        "issuer": "company",
        "private": "private_company",
        "central_bank": "regulator",
        "agency": "regulator",
        "government_agency": "regulator",
        "nation": "country",
        "macro": "macro_factor",
        "macro_indicator": "macro_factor",
        "macro_index": "macro_factor",
        "indicator": "macro_factor",
        "industry": "sector",
    }
    return aliases.get(normalized, "other")


def _domain_for_entity(entity_type: str, row: Mapping[str, Any]) -> str:
    if entity_type == "crypto_asset":
        return "crypto"
    if entity_type == "equity":
        return "us_equity"
    if entity_type == "private_company":
        return "private_company"
    if entity_type == "regulator":
        return "regulation"
    if entity_type == "country":
        return "energy_geopolitics"
    if entity_type == "commodity":
        return "commodity"
    if entity_type == "macro_factor":
        return "macro_rates"
    if entity_type == "sector":
        label = _norm(row.get("raw_value") or row.get("label") or row.get("normalized_value"))
        if "semi" in label or "ai" in label:
            return "ai_semiconductors"
        return "us_equity"
    if entity_type == "company":
        label = _norm(row.get("raw_value") or row.get("label") or row.get("normalized_value"))
        if any(marker in label for marker in ("openai", "anthropic", "spacex")):
            return "private_company"
        return "us_equity"
    return "unknown"


def _market_domain(value: Any) -> str | None:
    normalized = _str(value).lower().replace("-", "_").replace(" ", "_")
    if normalized in _NEWS_MARKET_DOMAINS:
        return normalized
    aliases = {
        "equity": "us_equity",
        "equities": "us_equity",
        "us_equities": "us_equity",
        "stock": "us_equity",
        "stocks": "us_equity",
        "macro": "macro_rates",
        "rates": "macro_rates",
        "rate": "macro_rates",
        "fed": "macro_rates",
        "energy": "energy_geopolitics",
        "geopolitics": "energy_geopolitics",
        "geopolitical": "energy_geopolitics",
        "ai_semis": "ai_semiconductors",
        "semiconductors": "ai_semiconductors",
        "semis": "ai_semiconductors",
        "regulatory": "regulation",
        "private": "private_company",
        "commodities": "commodity",
        "cex": "crypto",
        "dex": "crypto",
    }
    return aliases.get(normalized)


def _target_domains(*, target_id: Any, target_type: Any) -> list[str]:
    target = _str(target_id).lower()
    target_kind = _str(target_type).lower().replace("-", "_").replace(" ", "_")
    domains: list[str] = []
    if target.startswith("market_instrument:us_equity:"):
        domains.append("us_equity")
    elif target.startswith("market_instrument:commodity:"):
        domains.append("commodity")
    elif target.startswith("market_instrument:fx:"):
        domains.append("fx")
    elif target.startswith(("asset:", "cex_token:", "token:")):
        domains.append("crypto")
    if target_kind in {"marketinstrument", "market_instrument", "equity", "stock"}:
        domains.append("us_equity")
    elif target_kind in {"commodity", "commodity_futures", "futures_contract"}:
        domains.append("commodity")
    elif target_kind in {"cextoken", "cex_token", "asset", "token", "crypto_asset"}:
        domains.append("crypto")
    return _stable_unique(domain for domain in domains if domain in _NEWS_MARKET_DOMAINS)


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


def _bounded_json_object(value: Any, *, max_keys: int = 32) -> dict[str, object]:
    payload = _json_object(value)
    result: dict[str, object] = {}
    for key, child in list(payload.items())[:max_keys]:
        bounded_key = _bounded(key, 80)
        if not bounded_key:
            continue
        result[bounded_key] = _bounded_json_value(child, depth=0)
    return result


def _bounded_json_value(value: Any, *, depth: int) -> object:
    if depth >= 3:
        return _bounded(value, 500)
    if isinstance(value, Mapping):
        return {
            _bounded(key, 80): _bounded_json_value(child, depth=depth + 1)
            for key, child in list(value.items())[:32]
            if _bounded(key, 80)
        }
    if isinstance(value, list | tuple | set):
        return [_bounded_json_value(child, depth=depth + 1) for child in list(value)[:20]]
    if isinstance(value, bool | int | float):
        return value
    if value is None:
        return ""
    return _bounded(value, 500)


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


def _norm(value: Any) -> str:
    return _str(value).lower()


__all__ = [
    "BODY_EXCERPT_MAX_CHARS",
    "build_news_item_brief_input_packet",
    "news_item_brief_material_input_hash",
    "news_item_brief_material_input_payload",
]
