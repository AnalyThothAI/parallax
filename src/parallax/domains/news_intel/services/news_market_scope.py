from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel._constants import NEWS_MARKET_SCOPE_VERSION
from parallax.domains.news_intel.types.news_market_scope import (
    NewsMarketScope,
    NewsMarketScopeName,
    NewsMarketScopeStatus,
)

_RESOLVED_CRYPTO_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})
_CRYPTO_TARGET_TYPES = frozenset({"Asset", "CexToken"})
_CRYPTO_MARKET_TYPES = frozenset({"", "crypto", "cex", "dex", "spot", "perp", "perpetual", "onchain"})
_COLLISION_REASON_FRAGMENTS = (
    "COMMON_WORD",
    "EQUITY",
    "PRIVATE_COMPANY",
    "STOCK",
    "COMMODITY",
)
_PRIMARY_PRIORITY: tuple[NewsMarketScopeName, ...] = (
    "crypto",
    "private_company",
    "us_equity",
    "macro_rates",
    "energy_geopolitics",
    "commodities",
    "fx",
    "ai_semiconductors",
    "broad_risk",
    "unknown",
)
_SCOPE_ORDER = {scope: index for index, scope in enumerate(_PRIMARY_PRIORITY)}

_CRYPTO_SUBJECT_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|crypto|blockchain|tokeni[sz]ed|tokeni[sz]ation|stablecoin|"
    r"defi|dex|cex|coinbase|binance|kraken|okx|bybit|zcash|orchard|solana|altcoin)\b",
    re.IGNORECASE,
)
_PRIVATE_COMPANY_RE = re.compile(
    r"\b(?:private company|privately held|tender offer|share sale|spacex|openai|anthropic|xai|starship)\b",
    re.IGNORECASE,
)
_US_EQUITY_RE = re.compile(
    r"\b(?:u\.?s\.?\s+equity|us equity|shares?|stocks?|nasdaq|nyse|dow jones|s&p|spx|"
    r"nvidia|nvda|apple|aapl|microsoft|msft|tesla|tsla|meta|amazon|amzn|google|googl)\b",
    re.IGNORECASE,
)
_MACRO_RATES_RE = re.compile(
    r"\b(?:fed|fomc|rate cut|rate hike|interest rates?|treasury yields?|dot plot|cpi|pce|"
    r"inflation|payrolls?|jobs report|gdp|central bank|liquidity)\b",
    re.IGNORECASE,
)
_ENERGY_GEOPOLITICS_RE = re.compile(
    r"\b(?:oil|opec|crude|brent|wti|hormuz|middle east|sanctions?|geopolitical|shipping risk)\b",
    re.IGNORECASE,
)
_COMMODITIES_RE = re.compile(r"\b(?:gold|silver|copper|oil|crude|brent|wti|commodity|commodities)\b", re.I)
_FX_RE = re.compile(
    r"\b(?:fx|foreign exchange|currency|currencies|dollar|usd|yen|jpy|euro|eur|yuan|cny|dxy)\b",
    re.IGNORECASE,
)
_AI_SEMICONDUCTORS_RE = re.compile(
    r"\b(?:ai|nvidia|semiconductor|chip|gpu|ai server|accelerator|dram|memory chip|hard drives?)\b",
    re.IGNORECASE,
)
_BROAD_RISK_RE = re.compile(
    r"\b(?:broad risk|risk assets?|markets?|equities|futures|nasdaq|s&p|spx|vix|rally|selloff)\b",
    re.IGNORECASE,
)


def classify_news_market_scope(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> NewsMarketScope:
    basis: dict[str, Any] = {
        "content_class": _text(item.get("content_class")),
        "crypto_evidence": [],
        "scope_evidence": {},
    }
    scopes: set[NewsMarketScopeName] = set()
    text = _item_text(item)

    _add_token_scopes(scopes=scopes, basis=basis, token_mentions=token_mentions)
    _add_fact_scopes(scopes=scopes, basis=basis, fact_candidates=fact_candidates)
    _add_item_text_scopes(scopes=scopes, basis=basis, item=item, text=text)

    if not scopes:
        scopes.add("unknown")

    ordered_scopes = tuple(sorted(scopes, key=lambda scope: _SCOPE_ORDER[scope]))
    primary = _primary_scope(ordered_scopes)
    status: NewsMarketScopeStatus = "unknown" if primary == "unknown" else "classified"
    return NewsMarketScope(
        scope=ordered_scopes,
        primary=primary,
        status=status,
        reason=_reason(primary=primary, basis=basis),
        basis=_finalize_basis(basis),
    )


def _add_token_scopes(
    *,
    scopes: set[NewsMarketScopeName],
    basis: dict[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
) -> None:
    for mention in token_mentions:
        symbol = _text(mention.get("display_symbol") or mention.get("observed_symbol")).upper()
        resolution_status = _text(mention.get("resolution_status"))
        target_type = _text(mention.get("target_type"))
        target_id = _text(mention.get("target_id"))
        market_type = _text(mention.get("market_type")).lower()
        reason_codes = [str(reason) for reason in _current_reason_codes(mention)]

        if _is_resolved_crypto_target(
            target_type=target_type,
            target_id=target_id,
            resolution_status=resolution_status,
            market_type=market_type,
            reason_codes=reason_codes,
        ):
            scopes.add("crypto")
            basis["crypto_evidence"].append(_target_evidence("resolved_crypto_target", symbol, target_id))
            continue
        if market_type == "equity" or target_id.startswith("equity:"):
            scopes.add("us_equity")
            _append_scope_evidence(basis, "us_equity", _target_evidence("market_instrument", symbol, target_id))
        elif market_type in {"commodity", "commodities"} or target_id.startswith("commodity:"):
            scopes.add("commodities")
            _append_scope_evidence(basis, "commodities", _target_evidence("market_instrument", symbol, target_id))
        elif market_type in {"fx", "currency"} or target_id.startswith(("fx:", "currency:")):
            scopes.add("fx")
            _append_scope_evidence(basis, "fx", _target_evidence("market_instrument", symbol, target_id))


def _add_fact_scopes(
    *,
    scopes: set[NewsMarketScopeName],
    basis: dict[str, Any],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> None:
    for candidate in fact_candidates:
        if _text(candidate.get("validation_status")) != "accepted":
            continue
        event_type = _text(candidate.get("event_type"))
        affected_targets = _current_affected_targets(candidate)
        if _fact_has_crypto_target(affected_targets):
            scopes.add("crypto")
            basis["crypto_evidence"].append(f"accepted_fact:{event_type}")


def _add_item_text_scopes(
    *,
    scopes: set[NewsMarketScopeName],
    basis: dict[str, Any],
    item: Mapping[str, Any],
    text: str,
) -> None:
    content_class = _text(item.get("content_class"))
    if _CRYPTO_SUBJECT_RE.search(text):
        scopes.add("crypto")
        basis["crypto_evidence"].append("text:crypto_subject")
    if _PRIVATE_COMPANY_RE.search(text):
        scopes.add("private_company")
        _append_scope_evidence(basis, "private_company", "text:private_company_context")
    if content_class == "ai_semiconductors" or _AI_SEMICONDUCTORS_RE.search(text):
        scopes.add("ai_semiconductors")
        _append_scope_evidence(basis, "ai_semiconductors", _scope_evidence(content_class, "text:ai_semiconductors"))
    if content_class in {"rates_fed", "macro_policy", "consumer_macro"} or _MACRO_RATES_RE.search(text):
        scopes.add("macro_rates")
        _append_scope_evidence(basis, "macro_rates", _scope_evidence(content_class, "text:macro_rates"))
    if content_class == "energy_geopolitics" or _ENERGY_GEOPOLITICS_RE.search(text):
        scopes.add("energy_geopolitics")
        _append_scope_evidence(
            basis,
            "energy_geopolitics",
            _scope_evidence(content_class, "text:energy_geopolitics"),
        )
    if _COMMODITIES_RE.search(text):
        scopes.add("commodities")
        _append_scope_evidence(basis, "commodities", "text:commodities")
    if _FX_RE.search(text):
        scopes.add("fx")
        _append_scope_evidence(basis, "fx", "text:fx")
    if _BROAD_RISK_RE.search(text):
        scopes.add("broad_risk")
        _append_scope_evidence(basis, "broad_risk", "text:broad_risk")
    if "private_company" not in scopes and _US_EQUITY_RE.search(text):
        scopes.add("us_equity")
        _append_scope_evidence(basis, "us_equity", "text:us_equity")


def _is_resolved_crypto_target(
    *,
    target_type: str,
    target_id: str,
    resolution_status: str,
    market_type: str,
    reason_codes: Sequence[str],
) -> bool:
    return (
        bool(target_id)
        and target_type in _CRYPTO_TARGET_TYPES
        and resolution_status in _RESOLVED_CRYPTO_STATUSES
        and not _has_collision_reason(reason_codes)
        and market_type in _CRYPTO_MARKET_TYPES
    )


def _fact_has_crypto_target(affected_targets: Sequence[Any]) -> bool:
    for target in affected_targets:
        if not isinstance(target, Mapping):
            continue
        target_type = _text(target.get("target_type"))
        target_id = _text(target.get("target_id"))
        market_type = _text(target.get("market_type")).lower()
        if target_id and target_type in _CRYPTO_TARGET_TYPES and market_type in _CRYPTO_MARKET_TYPES:
            return True
    return False


def _has_collision_reason(reason_codes: Sequence[str]) -> bool:
    return any(
        any(fragment in str(reason).upper() for fragment in _COLLISION_REASON_FRAGMENTS) for reason in reason_codes
    )


def _primary_scope(scopes: Sequence[NewsMarketScopeName]) -> NewsMarketScopeName:
    for candidate in _PRIMARY_PRIORITY:
        if candidate in scopes:
            return candidate
    return "unknown"


def _reason(*, primary: NewsMarketScopeName, basis: Mapping[str, Any]) -> str:
    if primary == "unknown":
        return "insufficient_market_context"
    if primary == "crypto" and basis.get("crypto_evidence"):
        return "crypto_evidence"
    return f"{primary}_context"


def _finalize_basis(basis: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(basis)
    finalized["crypto_evidence"] = _dedupe([str(value) for value in basis.get("crypto_evidence") or []])
    scope_evidence = basis.get("scope_evidence")
    finalized["scope_evidence"] = {
        str(scope): _dedupe([str(value) for value in evidence])
        for scope, evidence in sorted(dict(scope_evidence or {}).items())
    }
    return finalized


def _append_scope_evidence(basis: dict[str, Any], scope: NewsMarketScopeName, evidence: str) -> None:
    scope_evidence = basis.setdefault("scope_evidence", {})
    if not isinstance(scope_evidence, dict):
        return
    values = scope_evidence.setdefault(scope, [])
    if isinstance(values, list):
        values.append(evidence)


def _scope_evidence(content_class: str, fallback: str) -> str:
    return f"content_class:{content_class}" if content_class else fallback


def _item_text(item: Mapping[str, Any]) -> str:
    coverage_tags = " ".join(str(tag) for tag in _json_list(item.get("coverage_tags_json")))
    return " ".join(
        str(part)
        for part in (
            item.get("title") or "",
            item.get("summary") or "",
            item.get("body_text") or "",
            item.get("source_domain") or "",
            item.get("source_name") or "",
            item.get("source_role") or "",
            coverage_tags,
        )
    )


def _current_reason_codes(mention: Mapping[str, Any]) -> list[Any]:
    if "reason_codes" in mention:
        return _json_list(mention.get("reason_codes"))
    if "reason_codes_json" in mention:
        return _json_list(mention.get("reason_codes_json"))
    return []


def _current_affected_targets(candidate: Mapping[str, Any]) -> list[Any]:
    if "affected_targets" in candidate:
        return _json_list(candidate.get("affected_targets"))
    if "affected_targets_json" in candidate:
        return _json_list(candidate.get("affected_targets_json"))
    return []


def _target_evidence(kind: str, symbol: str, target_id: str) -> str:
    suffix = target_id or symbol
    return f"{kind}:{suffix}" if suffix else kind


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []
    return []


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "NEWS_MARKET_SCOPE_VERSION",
    "NewsMarketScope",
    "NewsMarketScopeName",
    "NewsMarketScopeStatus",
    "classify_news_market_scope",
]
