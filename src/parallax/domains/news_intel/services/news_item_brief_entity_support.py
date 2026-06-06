from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefInputPacket

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{1,31}")
_SYNTHETIC_PLACEHOLDER_RE = re.compile(
    r"(?<![a-z0-9])(?:xyz[-_]?[a-z0-9]{1,12}|abc[-_][a-z0-9]{1,12}|test[-_]?[a-z0-9]{0,12})(?![a-z0-9])",
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


@dataclass(frozen=True, slots=True)
class EntitySupportDecision:
    supported: bool
    reason: str


def source_backed_entity_keys(packet: NewsItemBriefInputPacket) -> set[str]:
    labels: set[str] = set()
    labels.update(_text_keys(packet.news_item.title))
    labels.update(_text_keys(packet.news_item.summary))
    labels.update(_text_keys(packet.news_item.body_excerpt))

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
    labels = _entity_labels(entity)
    if not labels:
        return EntitySupportDecision(supported=False, reason="missing_label")
    if _contains_synthetic_placeholder(labels):
        return EntitySupportDecision(supported=False, reason="synthetic_placeholder")
    if labels & source_backed_entity_keys(packet):
        return EntitySupportDecision(supported=True, reason="packet_key")

    source_domains = _source_backed_domains(packet)
    for domain in _entity_candidate_domains(entity=entity, payload=payload):
        if domain not in source_domains:
            continue
        if labels & _domain_proxy_keys(domain):
            return EntitySupportDecision(supported=True, reason=f"domain_proxy:{domain}")

    return EntitySupportDecision(supported=False, reason="unsupported")


def _source_backed_domains(packet: NewsItemBriefInputPacket) -> set[str]:
    domains = {_norm(domain) for domain in packet.market_scope}
    domains.update(_norm(entity.market_domain) for entity in packet.entity_lanes)
    for fact in packet.fact_lanes:
        for target in fact.affected_targets:
            domains.update(_domains_in_mapping(target))
    if packet.provider_signal_evidence is not None:
        domains.update(_norm(impact.market_type) for impact in packet.provider_signal_evidence.token_impacts)
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _entity_candidate_domains(*, entity: Mapping[str, Any], payload: Mapping[str, Any]) -> set[str]:
    domains = {_norm(entity.get("market_domain"))}
    domains.add(_ENTITY_TYPE_DOMAINS.get(_norm(entity.get("entity_type")), ""))
    domains.update(_norm(domain) for domain in payload.get("market_domains") or [] if isinstance(domain, str))
    for path in payload.get("transmission_paths") or []:
        if isinstance(path, Mapping):
            domains.add(_norm(path.get("market_domain")))
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _entity_labels(entity: Mapping[str, Any]) -> set[str]:
    labels = _string_keys(
        entity.get("label"),
        entity.get("symbol"),
        entity.get("name"),
        entity.get("target_id"),
    )
    return {label for label in labels if label}


def _contains_synthetic_placeholder(labels: set[str]) -> bool:
    return any(_SYNTHETIC_PLACEHOLDER_RE.search(label) for label in labels)


def _domain_proxy_keys(domain: str) -> set[str]:
    aliases: set[str] = set()
    for alias in _DOMAIN_PROXY_ALIASES.get(domain, ()):
        aliases.update(_string_keys(alias))
    return aliases


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
