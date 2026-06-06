from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefInputPacket

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,31}")
_SYNTHETIC_PLACEHOLDER_RE = re.compile(
    r"(?<![a-z0-9])(?:xyz|abc|test)(?:[-_ ]?[a-z0-9]{0,12})?(?![a-z0-9])",
    re.I,
)
_US_ENERGY_SECTOR_SOURCE_RE = re.compile(
    r"(?<![a-z0-9])(?:u\.?\s*s\.?|united states|american)\s+energy\s+"
    r"(?:firms?|companies|producers|sector|equities|stocks?)(?![a-z0-9])",
    re.I,
)
_KNOWN_DOMAINS = frozenset(
    {
        "crypto",
        "us_equity",
        "macro_rates",
        "energy_geopolitics",
        "ai_semiconductors",
        "regulation",
        "commodity",
        "fx",
    }
)
_ENTITY_TYPE_DOMAINS = {
    "crypto_asset": "crypto",
    "equity": "us_equity",
    "company": "us_equity",
    "regulator": "regulation",
    "country": "energy_geopolitics",
    "commodity": "commodity",
    "macro_factor": "macro_rates",
    "sector": "us_equity",
}
_GENERIC_MAPPING_VALUE_KEYS = frozenset(
    {
        "direction",
        "entity_type",
        "event_type",
        "grade",
        "impact_direction",
        "market_domain",
        "market_type",
        "realis",
        "resolution_status",
        "score",
        "signal",
        "status",
        "strength",
        "target_type",
        "validation_status",
    }
)
_DOMAIN_PROXY_ALIASES: dict[str, tuple[str, ...]] = {
    "commodity": (
        "WTI",
        "CL",
        "crude",
        "crude oil",
        "oil",
        "WTI crude",
        "WTI oil",
        "WTI原油",
        "WTI原油期货",
        "原油",
        "原油期货",
        "Brent",
        "布伦特原油",
    ),
    "energy_geopolitics": (
        "U.S.",
        "US",
        "USA",
        "United States",
        "美国",
        "Iran",
        "伊朗",
        "Israel",
        "以色列",
        "Gulf",
        "Strait of Hormuz",
        "Hormuz",
        "霍尔木兹",
        "霍尔木兹海峡",
        "Middle East",
        "中东",
        "geopolitical risk",
        "中东地缘政治风险",
    ),
    "crypto": (
        "BTC",
        "Bitcoin",
        "比特币",
    ),
    "macro_rates": (
        "Treasury yields",
        "US Treasury",
        "UST",
        "10Y",
        "Fed",
        "CPI",
        "inflation",
        "rates",
        "DXY",
        "USD",
        "美债收益率",
        "美国国债",
        "利率",
        "通胀",
        "美元",
        "美元指数",
    ),
    "us_equity": (
        "SPX",
        "S&P 500",
        "S&P500",
        "SP500",
        "Nasdaq",
        "NDX",
        "QQQ",
        "Dow",
        "美股",
        "标普500",
        "纳斯达克",
    ),
    "ai_semiconductors": (
        "NVIDIA",
        "NVDA",
        "AI semiconductor",
        "AI semiconductors",
        "semiconductor",
        "semiconductors",
        "AI半导体",
        "半导体",
    ),
    "regulation": (
        "SEC",
        "CFTC",
        "regulator",
        "regulators",
        "regulation",
        "监管",
        "监管机构",
    ),
    "fx": (
        "USD",
        "DXY",
        "EURUSD",
        "美元",
        "美元指数",
        "外汇",
        "FX",
    ),
}
_US_ENERGY_SECTOR_TRANSLATION_ALIASES = (
    "美国能源企业",
    "美国能源公司",
    "美国能源生产商",
    "美国能源板块",
    "美国能源股",
    "美国能源股票",
    "U.S. Energy Firms",
    "US Energy Firms",
    "American Energy Firms",
    "U.S. Energy Companies",
    "US Energy Companies",
    "American Energy Companies",
    "U.S. Energy Producers",
    "US Energy Producers",
    "American Energy Producers",
    "U.S. Energy Sector",
    "US Energy Sector",
    "American Energy Sector",
    "U.S. Energy Equities",
    "US Energy Equities",
    "American Energy Equities",
    "U.S. Energy Equities (sector proxy)",
    "US Energy Equities (sector proxy)",
    "U.S. Energy Stocks",
    "US Energy Stocks",
    "American Energy Stocks",
)


@dataclass(frozen=True, slots=True)
class EntitySupportDecision:
    supported: bool
    reason: str


def source_backed_entity_keys(packet: NewsItemBriefInputPacket) -> set[str]:
    labels: set[str] = set()
    labels.update(_text_keys(packet.news_item.title))
    labels.update(_text_keys(packet.news_item.summary))
    labels.update(_text_keys(packet.news_item.body_excerpt))
    labels.update(_translated_source_entity_keys(packet))

    for entity in packet.entity_lanes:
        labels.update(
            _string_keys(
                entity.entity_id,
                entity.observed_label,
                entity.display_symbol,
                entity.display_name,
                entity.target_id,
            )
        )
        for target in entity.candidate_targets:
            labels.update(_mapping_value_keys(target))

    for fact in packet.fact_lanes:
        labels.update(_text_keys(fact.claim))
        labels.update(_text_keys(fact.evidence_quote))
        for target in fact.affected_targets:
            labels.update(_mapping_value_keys(target))

    if packet.provider_signal_evidence is not None:
        provider = packet.provider_signal_evidence
        labels.update(_string_keys(provider.provider))
        labels.update(_text_keys(provider.summary_zh))
        labels.update(_text_keys(provider.summary_en))
        for impact in provider.token_impacts:
            labels.update(_string_keys(impact.symbol))

    return {label for label in labels if label}


def validate_affected_entity_support(
    entity: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    payload: Mapping[str, Any],
) -> EntitySupportDecision:
    source_keys = source_backed_entity_keys(packet)
    label_name_keys = _entity_label_name_keys(entity)
    symbol_keys = _entity_symbol_keys(entity)
    target_id_keys = _entity_target_id_keys(entity)
    entity_keys = label_name_keys | symbol_keys | target_id_keys
    if not entity_keys:
        return EntitySupportDecision(supported=False, reason="missing_label")
    if _contains_unbacked_synthetic_placeholder(entity, source_keys=source_keys):
        return EntitySupportDecision(supported=False, reason="synthetic_placeholder")
    if target_id_keys and not target_id_keys & source_keys:
        return EntitySupportDecision(supported=False, reason="unsupported_target_id")

    source_domains = _source_backed_domains(packet, source_keys=source_keys)
    candidate_domains = _entity_candidate_domains(entity=entity, payload=payload)
    if label_name_keys and not _keys_supported_by_source_or_proxy(
        label_name_keys,
        source_keys=source_keys,
        source_domains=source_domains,
        candidate_domains=candidate_domains,
    ):
        return EntitySupportDecision(supported=False, reason="unsupported_label")

    if entity_keys & source_keys:
        return EntitySupportDecision(supported=True, reason="packet_key")

    for domain in candidate_domains:
        if domain not in source_domains:
            continue
        if _domain_proxy_supports_keys(domain, entity_keys, source_keys=source_keys):
            return EntitySupportDecision(supported=True, reason=f"domain_proxy:{domain}")

    return EntitySupportDecision(supported=False, reason="unsupported")


def _source_backed_domains(packet: NewsItemBriefInputPacket, *, source_keys: set[str] | None = None) -> set[str]:
    domains = {_norm(domain) for domain in packet.market_scope if _norm(domain) != "crypto"}
    domains.update(_norm(entity.market_domain) for entity in packet.entity_lanes)
    for fact in packet.fact_lanes:
        for target in fact.affected_targets:
            domains.update(_domains_in_mapping(target))
    if packet.provider_signal_evidence is not None:
        for impact in packet.provider_signal_evidence.token_impacts:
            domains.update(_provider_impact_domains(impact.market_type))
            if impact.symbol:
                domains.add("crypto")
    source_keys = source_backed_entity_keys(packet) if source_keys is None else source_keys
    if source_keys & _domain_proxy_keys("crypto"):
        domains.add("crypto")
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _entity_candidate_domains(*, entity: Mapping[str, Any], payload: Mapping[str, Any]) -> set[str]:
    domains = {_norm(entity.get("market_domain"))}
    domains.add(_ENTITY_TYPE_DOMAINS.get(_norm(entity.get("entity_type")), ""))
    domains.update(_norm(domain) for domain in payload.get("market_domains") or [] if isinstance(domain, str))
    for path in payload.get("transmission_paths") or []:
        if isinstance(path, Mapping):
            domains.add(_norm(path.get("market_domain")))
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _entity_label_name_keys(entity: Mapping[str, Any]) -> set[str]:
    return _string_keys(entity.get("label"), entity.get("name"))


def _entity_symbol_keys(entity: Mapping[str, Any]) -> set[str]:
    return _string_keys(entity.get("symbol"))


def _entity_target_id_keys(entity: Mapping[str, Any]) -> set[str]:
    return _string_keys(entity.get("target_id"))


def _contains_unbacked_synthetic_placeholder(
    entity: Mapping[str, Any],
    *,
    source_keys: set[str],
) -> bool:
    for value in (entity.get("label"), entity.get("name")):
        if not _SYNTHETIC_PLACEHOLDER_RE.search(str(value or "")):
            continue
        if _string_keys(value) & source_keys:
            continue
        return True
    return False


def _keys_supported_by_source_or_proxy(
    keys: set[str],
    *,
    source_keys: set[str],
    source_domains: set[str],
    candidate_domains: set[str],
) -> bool:
    if keys & source_keys:
        return True
    return any(
        domain in source_domains and _domain_proxy_supports_keys(domain, keys, source_keys=source_keys)
        for domain in candidate_domains
    )


def _domain_proxy_supports_keys(domain: str, keys: set[str], *, source_keys: set[str]) -> bool:
    proxy_keys = _domain_proxy_keys(domain)
    if not keys & proxy_keys:
        return False
    return domain != "crypto" or bool(source_keys & proxy_keys)


def _provider_impact_domains(market_type: Any) -> set[str]:
    market = _norm(market_type).replace("-", "_").replace(" ", "_")
    if market in {"cex", "dex", "spot", "perp", "perpetual", "crypto"}:
        return {"crypto"}
    return {market}


def _domain_proxy_keys(domain: str) -> set[str]:
    aliases: set[str] = set()
    for alias in _DOMAIN_PROXY_ALIASES.get(domain, ()):
        aliases.update(_string_keys(alias))
    return aliases


def _translated_source_entity_keys(packet: NewsItemBriefInputPacket) -> set[str]:
    if not _US_ENERGY_SECTOR_SOURCE_RE.search(_translated_entity_trigger_text(packet)):
        return set()
    labels: set[str] = set()
    for alias in _US_ENERGY_SECTOR_TRANSLATION_ALIASES:
        labels.update(_string_keys(alias))
    return labels


def _translated_entity_trigger_text(packet: NewsItemBriefInputPacket) -> str:
    texts = [
        packet.news_item.title,
        packet.news_item.summary,
        packet.news_item.body_excerpt,
    ]
    for fact in packet.fact_lanes:
        texts.extend((fact.claim, fact.evidence_quote))
        for target in fact.affected_targets:
            texts.extend(_mapping_string_values(target))
    if packet.provider_signal_evidence is not None:
        provider = packet.provider_signal_evidence
        texts.extend((provider.summary_zh, provider.summary_en))
    return " ".join(text for text in texts if text)


def _mapping_string_values(value: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    for key, child in value.items():
        if str(key).strip().lower() in _GENERIC_MAPPING_VALUE_KEYS:
            continue
        if isinstance(child, str):
            labels.append(child)
        elif isinstance(child, Mapping):
            labels.extend(_mapping_string_values(child))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, str):
                    labels.append(item)
                elif isinstance(item, Mapping):
                    labels.extend(_mapping_string_values(item))
    return labels


def _domains_in_mapping(value: Mapping[str, Any]) -> set[str]:
    domains: set[str] = set()
    for key, child in value.items():
        if key in {"market_domain", "market_type"}:
            domains.add(_norm(child))
        if isinstance(child, Mapping):
            domains.update(_domains_in_mapping(child))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, Mapping):
                    domains.update(_domains_in_mapping(item))
    return domains


def _mapping_value_keys(value: Mapping[str, Any]) -> set[str]:
    labels: set[str] = set()
    for key, child in value.items():
        if str(key).strip().lower() in _GENERIC_MAPPING_VALUE_KEYS:
            continue
        if isinstance(child, str):
            labels.update(_text_keys(child))
        elif isinstance(child, Mapping):
            labels.update(_mapping_value_keys(child))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, str):
                    labels.update(_text_keys(item))
                elif isinstance(item, Mapping):
                    labels.update(_mapping_value_keys(item))
    return labels


def _text_keys(value: Any) -> set[str]:
    text = str(value or "")
    labels = _string_keys(text)
    labels.update(_norm(token) for token in _ASCII_TOKEN_RE.findall(text))
    return labels


def _string_keys(*values: Any) -> set[str]:
    labels: set[str] = set()
    for value in values:
        normalized = _norm(value)
        if not normalized:
            continue
        labels.add(normalized)
        labels.add(normalized.replace(" ", ""))
        labels.add(normalized.replace("-", ""))
        labels.add(normalized.replace("_", ""))
        labels.add(normalized.replace(".", ""))
    return labels


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = [
    "EntitySupportDecision",
    "source_backed_entity_keys",
    "validate_affected_entity_support",
]
