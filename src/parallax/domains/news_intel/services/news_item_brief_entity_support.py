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
_DOMAIN_PROXY_ALIAS_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "commodity": (
        (
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
    ),
    "energy_geopolitics": (
        ("U.S.", "US", "USA", "United States", "美国"),
        ("Iran", "伊朗"),
        ("Israel", "以色列"),
        (
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
    ),
    "crypto": (
        ("BTC", "Bitcoin", "比特币"),
    ),
    "macro_rates": (
        ("Treasury yields", "US Treasury", "UST", "10Y", "美债收益率", "美国国债"),
        ("Fed", "CPI", "inflation", "rates", "利率", "通胀"),
        ("DXY", "USD", "美元", "美元指数"),
    ),
    "us_equity": (
        ("SPX", "S&P 500", "S&P500", "SP500", "标普500"),
        ("Nasdaq", "NDX", "QQQ", "纳斯达克"),
        ("Dow",),
        ("美股",),
    ),
    "ai_semiconductors": (
        (
            "NVIDIA",
            "NVDA",
            "AI semiconductor",
            "AI semiconductors",
            "semiconductor",
            "semiconductors",
            "AI半导体",
            "半导体",
        ),
    ),
    "regulation": (
        ("SEC",),
        ("CFTC",),
        ("regulator", "regulators", "regulation", "监管", "监管机构"),
    ),
    "fx": (
        ("USD", "DXY", "美元", "美元指数"),
        ("EURUSD",),
        ("外汇", "FX"),
    ),
}
_GENERIC_DESCRIPTOR_ALIASES_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "crypto": (
        "token",
        "coin",
        "spot",
        "perp",
        "perpetual",
        "contract",
        "exchange",
        "代币",
        "币",
        "现货",
        "永续",
        "合约",
        "交易所",
    ),
    "commodity": (
        "future",
        "futures",
        "contract",
        "commodity",
        "期货",
        "合约",
        "商品",
    ),
    "us_equity": (
        "stock",
        "stocks",
        "equity",
        "equities",
        "share",
        "shares",
        "sector",
        "company",
        "companies",
        "firm",
        "firms",
        "index",
        "etf",
        "fund",
        "股票",
        "股",
        "权益",
        "板块",
        "公司",
        "企业",
        "指数",
        "基金",
    ),
    "energy_geopolitics": (
        "country",
        "region",
        "risk",
        "sector",
        "国家",
        "地区",
        "风险",
        "板块",
    ),
    "macro_rates": (
        "rate",
        "rates",
        "yield",
        "yields",
        "index",
        "factor",
        "利率",
        "收益率",
        "指数",
        "因子",
    ),
    "ai_semiconductors": (
        "stock",
        "stocks",
        "equity",
        "equities",
        "sector",
        "company",
        "companies",
        "股票",
        "股",
        "板块",
        "公司",
        "企业",
    ),
    "regulation": (
        "regulator",
        "regulators",
        "agency",
        "agencies",
        "监管",
        "监管机构",
        "机构",
    ),
    "fx": (
        "spot",
        "index",
        "currency",
        "currencies",
        "现货",
        "指数",
        "货币",
        "外汇",
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


@dataclass(frozen=True, slots=True)
class _SourceBackedEntityKeySupport:
    text_keys: set[str]
    structured_keys_by_domain: dict[str, set[str]]
    domainless_structured_keys: set[str]

    @property
    def all_keys(self) -> set[str]:
        keys = set(self.text_keys)
        keys.update(self.domainless_structured_keys)
        for domain_keys in self.structured_keys_by_domain.values():
            keys.update(domain_keys)
        return {key for key in keys if key}


def source_backed_entity_keys(packet: NewsItemBriefInputPacket) -> set[str]:
    return _source_backed_entity_key_support(packet).all_keys


def _source_backed_entity_key_support(packet: NewsItemBriefInputPacket) -> _SourceBackedEntityKeySupport:
    labels: set[str] = set()
    labels.update(_text_keys(packet.news_item.title))
    labels.update(_text_keys(packet.news_item.summary))
    labels.update(_text_keys(packet.news_item.body_excerpt))
    labels.update(_translated_source_entity_keys(packet))
    structured_by_domain: dict[str, set[str]] = {}
    domainless_structured_keys: set[str] = set()

    for entity in packet.entity_lanes:
        _add_structured_source_keys(
            structured_by_domain,
            domainless_structured_keys,
            _string_keys(
                entity.entity_id,
                entity.observed_label,
                entity.display_symbol,
                entity.display_name,
                entity.target_id,
            ),
            domains=_entity_lane_domains(entity),
        )
        for target in entity.candidate_targets:
            target_domains = _domains_in_mapping(target) or _entity_lane_domains(entity)
            _add_structured_source_keys(
                structured_by_domain,
                domainless_structured_keys,
                _mapping_value_keys(target),
                domains=target_domains,
            )

    for fact in packet.fact_lanes:
        labels.update(_text_keys(fact.claim))
        labels.update(_text_keys(fact.evidence_quote))
        for target in fact.affected_targets:
            _add_structured_source_keys(
                structured_by_domain,
                domainless_structured_keys,
                _mapping_value_keys(target),
                domains=_domains_in_mapping(target),
            )

    if packet.provider_signal_evidence is not None:
        provider = packet.provider_signal_evidence
        labels.update(_text_keys(provider.summary_zh))
        labels.update(_text_keys(provider.summary_en))
        _add_structured_source_keys(
            structured_by_domain,
            domainless_structured_keys,
            _string_keys(provider.provider),
            domains=set(),
        )
        for impact in provider.token_impacts:
            _add_structured_source_keys(
                structured_by_domain,
                domainless_structured_keys,
                _string_keys(impact.symbol),
                domains=_provider_impact_domains(impact.market_type),
            )

    return _SourceBackedEntityKeySupport(
        text_keys={label for label in labels if label},
        structured_keys_by_domain={
            domain: {label for label in domain_labels if label}
            for domain, domain_labels in structured_by_domain.items()
            if domain in _KNOWN_DOMAINS
        },
        domainless_structured_keys={label for label in domainless_structured_keys if label},
    )


def _add_structured_source_keys(
    structured_by_domain: dict[str, set[str]],
    domainless_structured_keys: set[str],
    keys: set[str],
    *,
    domains: set[str],
) -> None:
    clean_keys = {key for key in keys if key}
    if not clean_keys:
        return
    clean_domains = {domain for domain in domains if domain in _KNOWN_DOMAINS}
    if not clean_domains:
        domainless_structured_keys.update(clean_keys)
        return
    for domain in clean_domains:
        structured_by_domain.setdefault(domain, set()).update(clean_keys)


def validate_affected_entity_support(
    entity: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    payload: Mapping[str, Any],
) -> EntitySupportDecision:
    source_key_support = _source_backed_entity_key_support(packet)
    source_keys = source_key_support.all_keys
    label_name_values = _entity_label_name_values(entity)
    label_name_keys = _entity_label_name_keys(entity)
    symbol_keys = _entity_symbol_keys(entity)
    target_id_keys = _entity_target_id_keys(entity)
    entity_keys = label_name_keys | symbol_keys | target_id_keys
    if not entity_keys:
        return EntitySupportDecision(supported=False, reason="missing_label")
    if _contains_unbacked_synthetic_placeholder(entity, source_keys=source_keys):
        return EntitySupportDecision(supported=False, reason="synthetic_placeholder")
    if _has_unsupported_entity_domain_conflict(entity):
        return EntitySupportDecision(supported=False, reason="unsupported_domain_conflict")

    source_domains = _source_backed_domains(packet)
    candidate_domains = _entity_candidate_domains(entity=entity, payload=payload)
    if target_id_keys and not _keys_supported_by_source_or_proxy(
        target_id_keys,
        source_key_support=source_key_support,
        source_domains=source_domains,
        candidate_domains=candidate_domains,
    ):
        return EntitySupportDecision(supported=False, reason="unsupported_target_id")

    if label_name_keys and not _label_name_supported_by_source_or_proxy(
        entity=entity,
        packet=packet,
        label_name_values=label_name_values,
        label_name_keys=label_name_keys,
        source_key_support=source_key_support,
        source_domains=source_domains,
        candidate_domains=candidate_domains,
    ):
        return EntitySupportDecision(supported=False, reason="unsupported_label")

    if _source_supports_keys(entity_keys, source_key_support=source_key_support, candidate_domains=candidate_domains):
        return EntitySupportDecision(supported=True, reason="packet_key")

    for domain in candidate_domains:
        if domain not in source_domains:
            continue
        if _domain_proxy_supports_keys(domain, entity_keys, source_keys=source_keys):
            return EntitySupportDecision(supported=True, reason=f"domain_proxy:{domain}")

    return EntitySupportDecision(supported=False, reason="unsupported")


def _source_backed_domains(packet: NewsItemBriefInputPacket) -> set[str]:
    domains = {_norm(domain) for domain in packet.market_scope if _norm(domain) != "crypto"}
    domains.update(_norm(entity.market_domain) for entity in packet.entity_lanes)
    for fact in packet.fact_lanes:
        for target in fact.affected_targets:
            domains.update(_domains_in_mapping(target))
    if packet.provider_signal_evidence is not None:
        for impact in packet.provider_signal_evidence.token_impacts:
            domains.update(_provider_impact_domains(impact.market_type))
    proxy_source_keys = _domain_proxy_source_keys(packet, domain="crypto")
    if proxy_source_keys & _domain_proxy_keys("crypto"):
        domains.add("crypto")
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _entity_candidate_domains(*, entity: Mapping[str, Any], payload: Mapping[str, Any]) -> set[str]:
    del payload
    return _entity_own_domains(entity)


def _entity_own_domains(entity: Mapping[str, Any]) -> set[str]:
    explicit_domain = _norm(entity.get("market_domain"))
    if explicit_domain in _KNOWN_DOMAINS:
        return {explicit_domain}

    type_domain = _ENTITY_TYPE_DOMAINS.get(_norm(entity.get("entity_type")), "")
    if type_domain in _KNOWN_DOMAINS:
        return {type_domain}
    return set()


def _has_unsupported_entity_domain_conflict(entity: Mapping[str, Any]) -> bool:
    explicit_domain = _norm(entity.get("market_domain"))
    if explicit_domain not in _KNOWN_DOMAINS:
        return False
    return _norm(entity.get("entity_type")) == "crypto_asset" and explicit_domain != "crypto"


def _entity_label_name_values(entity: Mapping[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    for value in (entity.get("label"), entity.get("name")):
        label = str(value or "").strip()
        if label:
            labels.append(label)
    return tuple(labels)


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


def _label_name_supported_by_source_or_proxy(
    *,
    entity: Mapping[str, Any],
    packet: NewsItemBriefInputPacket,
    label_name_values: tuple[str, ...],
    label_name_keys: set[str],
    source_key_support: _SourceBackedEntityKeySupport,
    source_domains: set[str],
    candidate_domains: set[str],
) -> bool:
    if _keys_supported_by_source_or_proxy(
        label_name_keys,
        source_key_support=source_key_support,
        source_domains=source_domains,
        candidate_domains=candidate_domains,
    ):
        return True
    return any(
        _display_label_supported_by_source_descriptor(
            label,
            entity=entity,
            packet=packet,
            source_keys=source_key_support.all_keys,
            source_text_keys=source_key_support.text_keys,
            source_domains=source_domains,
            candidate_domains=candidate_domains,
        )
        for label in label_name_values
    )


def _keys_supported_by_source_or_proxy(
    keys: set[str],
    *,
    source_key_support: _SourceBackedEntityKeySupport,
    source_domains: set[str],
    candidate_domains: set[str],
) -> bool:
    if _source_supports_keys(keys, source_key_support=source_key_support, candidate_domains=candidate_domains):
        return True
    source_keys = source_key_support.all_keys
    return any(
        domain in source_domains and _domain_proxy_supports_keys(domain, keys, source_keys=source_keys)
        for domain in candidate_domains
    )


def _source_supports_keys(
    keys: set[str],
    *,
    source_key_support: _SourceBackedEntityKeySupport,
    candidate_domains: set[str],
) -> bool:
    if keys & source_key_support.text_keys:
        return True
    return any(keys & source_key_support.structured_keys_by_domain.get(domain, set()) for domain in candidate_domains)


def _domain_proxy_supports_keys(domain: str, keys: set[str], *, source_keys: set[str]) -> bool:
    return any(keys & proxy_keys and source_keys & proxy_keys for proxy_keys in _domain_proxy_key_groups(domain))


def _display_label_supported_by_source_descriptor(
    label: str,
    *,
    entity: Mapping[str, Any],
    packet: NewsItemBriefInputPacket,
    source_keys: set[str],
    source_text_keys: set[str],
    source_domains: set[str],
    candidate_domains: set[str],
) -> bool:
    normalized = _norm(label)
    if not normalized:
        return False

    descriptor_keys = _generic_descriptor_keys(candidate_domains)
    base_keys = _source_descriptor_base_keys(
        label=label,
        entity=entity,
        packet=packet,
        source_keys=source_keys,
        source_text_keys=source_text_keys,
        source_domains=source_domains,
        candidate_domains=candidate_domains,
    )
    base_keys = {key for key in base_keys if key and key not in descriptor_keys}
    for base_key in sorted(base_keys, key=len, reverse=True):
        for start, end in _key_spans(normalized, base_key):
            remaining = f"{normalized[:start]} {normalized[end:]}"
            if _only_generic_descriptor_text(remaining, descriptor_keys):
                return True
    return False


def _source_descriptor_base_keys(
    *,
    label: str,
    entity: Mapping[str, Any],
    packet: NewsItemBriefInputPacket,
    source_keys: set[str],
    source_text_keys: set[str],
    source_domains: set[str],
    candidate_domains: set[str],
) -> set[str]:
    descriptor_keys = _generic_descriptor_keys(candidate_domains)
    entity_keys = _entity_descriptor_candidate_keys(entity) - descriptor_keys
    entity_specific_source_keys = _entity_specific_descriptor_source_keys(
        packet,
        candidate_domains=candidate_domains,
    )
    base_keys = entity_keys & entity_specific_source_keys
    base_keys.update(_entity_symbol_keys(entity) & source_text_keys)
    normalized_label = _norm(label)
    for domain in candidate_domains:
        if domain not in source_domains:
            continue
        for proxy_keys in _domain_proxy_key_groups(domain):
            if source_keys & proxy_keys and (
                entity_keys & proxy_keys or _label_contains_any_key(normalized_label, proxy_keys)
            ):
                base_keys.update(proxy_keys)
    return base_keys


def _entity_descriptor_candidate_keys(entity: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    keys.update(_text_keys(entity.get("label")))
    keys.update(_text_keys(entity.get("name")))
    keys.update(_string_keys(entity.get("symbol")))
    return keys


def _entity_specific_descriptor_source_keys(
    packet: NewsItemBriefInputPacket,
    *,
    candidate_domains: set[str],
) -> set[str]:
    keys: set[str] = set()
    for entity in packet.entity_lanes:
        entity_domains = _entity_lane_domains(entity)
        if _domains_allow_descriptor_source(entity_domains, candidate_domains):
            keys.update(
                _string_keys(
                    entity.observed_label,
                    entity.display_symbol,
                    entity.display_name,
                    entity.target_id,
                )
            )
        for target in entity.candidate_targets:
            target_domains = _domains_in_mapping(target) or entity_domains
            if _domains_allow_descriptor_source(target_domains, candidate_domains):
                keys.update(_mapping_value_keys(target))
    for fact in packet.fact_lanes:
        for target in fact.affected_targets:
            target_domains = _domains_in_mapping(target)
            if _domains_allow_descriptor_source(target_domains, candidate_domains):
                keys.update(_mapping_value_keys(target))
    if packet.provider_signal_evidence is not None:
        for impact in packet.provider_signal_evidence.token_impacts:
            impact_domains = _provider_impact_domains(impact.market_type)
            if impact_domains & candidate_domains:
                keys.update(_string_keys(impact.symbol))
    return keys


def _domain_proxy_source_keys(packet: NewsItemBriefInputPacket, *, domain: str) -> set[str]:
    keys: set[str] = set()
    keys.update(_text_keys(packet.news_item.title))
    keys.update(_text_keys(packet.news_item.summary))
    keys.update(_text_keys(packet.news_item.body_excerpt))
    keys.update(_translated_source_entity_keys(packet))
    for entity in packet.entity_lanes:
        keys.update(
            _string_keys(
                entity.entity_id,
                entity.observed_label,
                entity.display_symbol,
                entity.display_name,
                entity.target_id,
            )
        )
        for target in entity.candidate_targets:
            keys.update(_mapping_value_keys(target))
    for fact in packet.fact_lanes:
        keys.update(_text_keys(fact.claim))
        keys.update(_text_keys(fact.evidence_quote))
        for target in fact.affected_targets:
            keys.update(_mapping_value_keys(target))
    if packet.provider_signal_evidence is not None:
        provider = packet.provider_signal_evidence
        keys.update(_text_keys(provider.summary_zh))
        keys.update(_text_keys(provider.summary_en))
        for impact in provider.token_impacts:
            if domain in _provider_impact_domains(impact.market_type):
                keys.update(_string_keys(impact.symbol))
    return keys


def _entity_lane_domains(entity: Any) -> set[str]:
    domains = {
        _norm(getattr(entity, "market_domain", "")),
        _ENTITY_TYPE_DOMAINS.get(_norm(getattr(entity, "entity_type", "")), ""),
    }
    return {domain for domain in domains if domain in _KNOWN_DOMAINS}


def _domains_allow_descriptor_source(source_domains: set[str], candidate_domains: set[str]) -> bool:
    return not source_domains or bool(source_domains & candidate_domains)


def _label_contains_any_key(label: str, keys: set[str]) -> bool:
    return any(_key_spans(label, key) for key in keys)


def _generic_descriptor_keys(candidate_domains: set[str]) -> set[str]:
    keys: set[str] = set()
    for domain in candidate_domains:
        for descriptor in _GENERIC_DESCRIPTOR_ALIASES_BY_DOMAIN.get(domain, ()):
            keys.update(_string_keys(descriptor))
    return keys


def _key_spans(text: str, key: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    if not key:
        return spans
    start = text.find(key)
    while start >= 0:
        end = start + len(key)
        if _key_span_has_boundaries(text, start, end, key):
            spans.append((start, end))
        start = text.find(key, start + 1)
    return spans


def _key_span_has_boundaries(text: str, start: int, end: int, key: str) -> bool:
    if not key.isascii() or not key.replace(" ", "").replace("-", "").replace(".", "").isalnum():
        return True
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not _is_ascii_alnum(before) and not _is_ascii_alnum(after)


def _is_ascii_alnum(value: str) -> bool:
    return bool(value) and value.isascii() and value.isalnum()


def _only_generic_descriptor_text(text: str, descriptor_keys: set[str]) -> bool:
    compact = _compact_label_residue(text)
    if not compact:
        return True
    for descriptor in sorted(descriptor_keys, key=len, reverse=True):
        compact = compact.replace(_compact_label_residue(descriptor), "")
        if not compact:
            return True
    return not compact


def _compact_label_residue(text: str) -> str:
    return re.sub(r"[\s._:/()（）\[\],，&+|'-]+", "", _norm(text))


def _domain_proxy_key_groups(domain: str) -> tuple[set[str], ...]:
    groups: list[set[str]] = []
    for aliases in _DOMAIN_PROXY_ALIAS_GROUPS.get(domain, ()):
        keys: set[str] = set()
        for alias in aliases:
            keys.update(_string_keys(alias))
        groups.append(keys)
    return tuple(groups)


def _provider_impact_domains(market_type: Any) -> set[str]:
    market = _norm(market_type).replace("-", "_").replace(" ", "_")
    if market in {"cex", "dex", "spot", "perp", "perpetual", "crypto"}:
        return {"crypto"}
    return {market}


def _domain_proxy_keys(domain: str) -> set[str]:
    aliases: set[str] = set()
    for keys in _domain_proxy_key_groups(domain):
        aliases.update(keys)
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
