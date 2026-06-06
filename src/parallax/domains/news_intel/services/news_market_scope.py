from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsMarketScope:
    domains: list[str]
    basis: dict[str, Any]


_DOMAIN_ORDER = (
    "macro_rates",
    "energy_geopolitics",
    "ai_semiconductors",
    "us_equity",
    "private_company",
    "regulation",
    "crypto",
    "commodity",
    "fx",
    "unknown",
)
_AI_SEMI_RE = re.compile(r"\b(?:nvidia|nvda|semiconductor|semiconductors|ai chip|gpu|hbm|dram)\b", re.I)
_US_EQUITY_RE = re.compile(r"\b(?:shares?|stocks?|equity|nasdaq|nyse|earnings|guidance|supplier)\b", re.I)
_PRIVATE_RE = re.compile(r"\b(?:private company|spacex|openai|anthropic|tender offer)\b", re.I)
_MACRO_RATES_RE = re.compile(r"\b(?:fed|federal reserve|rates?|inflation|cpi|treasury yields?|dollar)\b", re.I)
_ENERGY_GEO_RE = re.compile(r"\b(?:oil|crude|iran|hormuz|sanctions?|geopolitic|shipping risk)\b", re.I)
_REGULATION_RE = re.compile(r"\b(?:sec|cftc|regulator|regulation|lawsuit|probe|approval)\b", re.I)
_COMMODITY_RE = re.compile(r"\b(?:gold|copper|wheat|commodity|commodities)\b", re.I)
_FX_RE = re.compile(r"\b(?:fx|foreign exchange|yen|euro|usd|currency)\b", re.I)


def infer_news_market_scope(
    *,
    item: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> NewsMarketScope:
    hits: dict[str, list[str]] = {}

    for domain in _json_list(item.get("market_scope_json") or item.get("market_scope")):
        _add(hits, _domain_alias(domain), "item:market_scope")

    text = _item_text(item)
    _add_if(hits, "ai_semiconductors", "text:ai_semiconductors", _AI_SEMI_RE.search(text))
    _add_if(hits, "us_equity", "text:us_equity", _US_EQUITY_RE.search(text) or _AI_SEMI_RE.search(text))
    _add_if(hits, "private_company", "text:private_company", _PRIVATE_RE.search(text))
    _add_if(hits, "macro_rates", "text:macro_rates", _MACRO_RATES_RE.search(text))
    _add_if(hits, "energy_geopolitics", "text:energy_geopolitics", _ENERGY_GEO_RE.search(text))
    _add_if(hits, "regulation", "text:regulation", _REGULATION_RE.search(text))
    _add_if(hits, "commodity", "text:commodity", _COMMODITY_RE.search(text))
    _add_if(hits, "fx", "text:fx", _FX_RE.search(text))

    for mention in token_mentions:
        target_type = str(mention.get("target_type") or "").strip()
        resolution_status = str(mention.get("resolution_status") or "").strip()
        if target_type in {"Asset", "CexToken", "asset"} or resolution_status in {"known_symbol", "exact_address"}:
            _add(hits, "crypto", f"token:{mention.get('mention_id') or mention.get('display_symbol') or 'unknown'}")

    for entity in entities:
        entity_type = str(entity.get("entity_type") or "").strip().lower().replace("-", "_")
        label = _entity_label(entity)
        marker = f"entity:{entity.get('entity_id') or label or 'unknown'}"
        if entity_type in {"crypto_asset", "token", "asset"}:
            _add(hits, "crypto", marker)
        elif entity_type in {"equity", "equity_symbol", "public_company"}:
            _add(hits, "us_equity", marker)
        elif entity_type == "private_company" or _PRIVATE_RE.search(label):
            _add(hits, "private_company", marker)
        elif entity_type == "company":
            _add(hits, "ai_semiconductors" if _AI_SEMI_RE.search(label) else "us_equity", marker)
        elif entity_type in {"regulator", "central_bank"}:
            _add(hits, "macro_rates" if _MACRO_RATES_RE.search(label) else "regulation", marker)
        elif entity_type == "country":
            _add(hits, "energy_geopolitics", marker)
        elif entity_type == "commodity":
            _add(hits, "commodity", marker)
        elif entity_type in {"macro_factor", "macro_indicator"}:
            _add(hits, "macro_rates", marker)
        elif entity_type == "sector" and _AI_SEMI_RE.search(label):
            _add(hits, "ai_semiconductors", marker)

    for fact in fact_candidates:
        event_type = str(fact.get("event_type") or "").strip().lower()
        if event_type in {"macro_data", "macro_policy", "rates", "macro_risk_repricing"}:
            _add(hits, "macro_rates", f"fact:{fact.get('fact_candidate_id') or event_type}")
        if event_type in {"geopolitical_risk", "supply_disruption"}:
            _add(hits, "energy_geopolitics", f"fact:{fact.get('fact_candidate_id') or event_type}")
        if event_type in {"listing", "exchange_listing", "protocol_development"}:
            _add(hits, "crypto", f"fact:{fact.get('fact_candidate_id') or event_type}")

    domains = [domain for domain in _DOMAIN_ORDER if domain in hits]
    if not domains:
        domains = ["unknown"]
        hits["unknown"] = ["fallback:unknown"]
    return NewsMarketScope(domains=domains, basis={domain: hits[domain] for domain in domains})


def _add_if(hits: dict[str, list[str]], domain: str, reason: str, condition: object) -> None:
    if condition:
        _add(hits, domain, reason)


def _add(hits: dict[str, list[str]], domain: str | None, reason: str) -> None:
    if not domain:
        return
    hits.setdefault(domain, [])
    if reason not in hits[domain]:
        hits[domain].append(reason)


def _domain_alias(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "equity": "us_equity",
        "stocks": "us_equity",
        "rates": "macro_rates",
        "macro": "macro_rates",
        "ai_semis": "ai_semiconductors",
        "semiconductors": "ai_semiconductors",
        "energy": "energy_geopolitics",
        "commodities": "commodity",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _DOMAIN_ORDER else None


def _item_text(item: Mapping[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in _json_list(item.get("coverage_tags_json")))
    return " ".join(
        str(value or "")
        for value in (
            item.get("title"),
            item.get("summary"),
            item.get("body_text"),
            item.get("source_domain"),
            item.get("source_name"),
            item.get("content_class"),
            tags,
        )
    )


def _entity_label(entity: Mapping[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            entity.get("raw_value"),
            entity.get("normalized_value"),
            entity.get("display_symbol"),
            entity.get("display_name"),
            entity.get("label"),
        )
    )


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


__all__ = ["NewsMarketScope", "infer_news_market_scope"]
