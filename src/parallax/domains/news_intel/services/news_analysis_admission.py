from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from parallax.domains.news_intel._constants import NEWS_ANALYSIS_ADMISSION_VERSION

NewsAnalysisAdmissionStatus = Literal["admitted", "page_only", "research_context", "suppressed", "needs_review"]

_ADMISSION_CONTENT_CLASSES = frozenset(
    {
        "crypto_market",
        "security_hack",
        "regulation",
        "etf_fund_flow",
        "exchange_listing",
        "protocol_development",
        "market_structure",
    }
)
_RESEARCH_CONTEXT_CONTENT_CLASSES = frozenset({"macro_policy", "rates_fed", "energy_geopolitics", "consumer_macro"})
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
_CRYPTO_SUBJECT_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|crypto|blockchain|tokeni[sz]ed|tokeni[sz]ation|stablecoin|"
    r"defi|dex|cex|coinbase|binance|kraken|okx|bybit|zcash|orchard)\b",
    re.IGNORECASE,
)
_NON_CRYPTO_SUBJECT_RE = re.compile(
    r"\b(?:shares?|stocks?|equity|private company|space company|semiconductor|memory chip|dram|hard drives?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NewsAnalysisAdmission:
    status: NewsAnalysisAdmissionStatus
    reason: str
    basis: dict[str, Any]
    version: str


def decide_news_analysis_admission(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> NewsAnalysisAdmission:
    basis = _basis(item=item, token_mentions=token_mentions, fact_candidates=fact_candidates)
    if _is_suppressed(item):
        return _admission("suppressed", "source_policy_suppressed", basis)

    content_class = str(item.get("content_class") or "").strip()
    allowed_content_class = content_class in _ADMISSION_CONTENT_CLASSES
    crypto_evidence = basis["crypto_evidence"]
    negative_evidence = basis["negative_evidence"]
    research_context = content_class in _RESEARCH_CONTEXT_CONTENT_CLASSES

    if crypto_evidence and _has_conflicting_strong_signals(basis):
        return _admission("needs_review", "conflicting_crypto_and_non_crypto_evidence", basis)
    if (
        _has_accepted_crypto_fact(basis)
        or (allowed_content_class and crypto_evidence)
        or (research_context and crypto_evidence)
    ):
        return _admission("admitted", "crypto_native_evidence", basis)
    if research_context and not crypto_evidence and not negative_evidence:
        return _admission("research_context", "macro_context_without_crypto_fact", basis)
    if negative_evidence or _looks_non_crypto_subject(item):
        return _admission("page_only", "non_crypto_subject", basis)
    if basis["provider_evidence"] and not crypto_evidence:
        return _admission("page_only", "provider_evidence_only", basis)
    return _admission("page_only", "no_crypto_native_evidence", basis)


def _basis(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    basis: dict[str, Any] = {
        "content_class": str(item.get("content_class") or "").strip(),
        "crypto_evidence": [],
        "negative_evidence": [],
        "strong_negative_evidence": [],
        "provider_evidence": [],
    }
    _add_provider_evidence(item=item, basis=basis)
    _add_token_evidence(token_mentions=token_mentions, basis=basis)
    _add_fact_evidence(fact_candidates=fact_candidates, basis=basis)
    if _has_crypto_subject_text(item):
        basis["crypto_evidence"].append("text:crypto_subject")
    if _looks_non_crypto_subject(item):
        basis["negative_evidence"].append("text:non_crypto_subject")
    basis["crypto_evidence"] = _dedupe(basis["crypto_evidence"])
    basis["negative_evidence"] = _dedupe(basis["negative_evidence"])
    basis["strong_negative_evidence"] = _dedupe(basis["strong_negative_evidence"])
    basis["provider_evidence"] = _dedupe(basis["provider_evidence"])
    return basis


def _add_provider_evidence(*, item: Mapping[str, Any], basis: dict[str, Any]) -> None:
    provider_signal = _json_object(item.get("provider_signal_json"))
    provider_score = _optional_int(provider_signal.get("score"))
    if provider_score is not None:
        basis["provider_evidence"].append(f"provider_score:{provider_score}")
    for impact in _json_list(item.get("provider_token_impacts_json")):
        if not isinstance(impact, Mapping):
            continue
        symbol = str(impact.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        market_type = str(impact.get("market_type") or "").strip().lower()
        basis["provider_evidence"].append(f"provider_impact:{symbol}")
        if market_type and market_type not in _CRYPTO_MARKET_TYPES:
            basis["negative_evidence"].append(f"provider_market_type:{market_type}:{symbol}")


def _add_token_evidence(*, token_mentions: Sequence[Mapping[str, Any]], basis: dict[str, Any]) -> None:
    for mention in token_mentions:
        symbol = str(mention.get("display_symbol") or mention.get("observed_symbol") or "").strip().upper()
        resolution_status = str(mention.get("resolution_status") or "").strip()
        target_type = str(mention.get("target_type") or "").strip()
        target_id = str(mention.get("target_id") or "").strip()
        reason_codes = [str(reason) for reason in _current_reason_codes(mention)]
        market_type = str(mention.get("market_type") or "").strip().lower()
        evidence_strength = str(mention.get("evidence_strength") or "").strip().lower()
        if resolution_status == "non_crypto" or target_type not in {"", *_CRYPTO_TARGET_TYPES}:
            evidence = _target_evidence("non_crypto_target", symbol, target_id)
            basis["negative_evidence"].append(evidence)
            if evidence_strength == "strong":
                basis["strong_negative_evidence"].append(evidence)
        if market_type and market_type not in _CRYPTO_MARKET_TYPES:
            evidence = _target_evidence(f"market_type:{market_type}", symbol, target_id)
            basis["negative_evidence"].append(evidence)
            if evidence_strength == "strong":
                basis["strong_negative_evidence"].append(evidence)
        for reason in reason_codes:
            if any(fragment in reason.upper() for fragment in _COLLISION_REASON_FRAGMENTS):
                basis["negative_evidence"].append(reason)
                if evidence_strength == "strong":
                    basis["strong_negative_evidence"].append(reason)
        if (
            target_id
            and target_type in _CRYPTO_TARGET_TYPES
            and resolution_status in _RESOLVED_CRYPTO_STATUSES
            and not _has_collision_reason(reason_codes)
            and (not market_type or market_type in _CRYPTO_MARKET_TYPES)
        ):
            basis["crypto_evidence"].append(_target_evidence("resolved_crypto_target", symbol, target_id))


def _add_fact_evidence(*, fact_candidates: Sequence[Mapping[str, Any]], basis: dict[str, Any]) -> None:
    for candidate in fact_candidates:
        if str(candidate.get("validation_status") or "").strip() != "accepted":
            continue
        event_type = str(candidate.get("event_type") or "").strip()
        affected_targets = _current_affected_targets(candidate)
        if _fact_has_crypto_target(affected_targets):
            basis["crypto_evidence"].append(f"accepted_fact:{event_type}")


def _fact_has_crypto_target(affected_targets: Sequence[Any]) -> bool:
    for target in affected_targets:
        if not isinstance(target, Mapping):
            continue
        target_type = str(target.get("target_type") or "").strip()
        target_id = str(target.get("target_id") or "").strip()
        market_type = str(target.get("market_type") or "").strip().lower()
        if (
            target_id
            and target_type in _CRYPTO_TARGET_TYPES
            and (not market_type or market_type in _CRYPTO_MARKET_TYPES)
        ):
            return True
    return False


def _is_suppressed(item: Mapping[str, Any]) -> bool:
    if item.get("enabled") is False or item.get("source_enabled") is False:
        return True
    policy_status = str(item.get("source_policy_status") or "").strip().lower()
    if policy_status in {"disabled", "suppressed", "blocked"}:
        return True
    policy = _json_object(item.get("source_policy_json"))
    return str(policy.get("status") or "").strip().lower() in {"disabled", "suppressed", "blocked"}


def _has_conflicting_strong_signals(basis: Mapping[str, Any]) -> bool:
    return _has_strong_crypto_evidence(basis) and bool(basis.get("strong_negative_evidence"))


def _has_strong_crypto_evidence(basis: Mapping[str, Any]) -> bool:
    return any(
        str(evidence).startswith(("accepted_fact:", "resolved_crypto_target:"))
        for evidence in basis.get("crypto_evidence") or []
    )


def _has_accepted_crypto_fact(basis: Mapping[str, Any]) -> bool:
    return any(str(evidence).startswith("accepted_fact:") for evidence in basis.get("crypto_evidence") or [])


def _has_collision_reason(reason_codes: Sequence[str]) -> bool:
    return any(
        any(fragment in str(reason).upper() for fragment in _COLLISION_REASON_FRAGMENTS) for reason in reason_codes
    )


def _has_crypto_subject_text(item: Mapping[str, Any]) -> bool:
    return bool(_CRYPTO_SUBJECT_RE.search(_item_text(item)))


def _looks_non_crypto_subject(item: Mapping[str, Any]) -> bool:
    return bool(_NON_CRYPTO_SUBJECT_RE.search(_item_text(item)))


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


def _admission(status: NewsAnalysisAdmissionStatus, reason: str, basis: dict[str, Any]) -> NewsAnalysisAdmission:
    return NewsAnalysisAdmission(
        status=status,
        reason=reason,
        basis=basis,
        version=NEWS_ANALYSIS_ADMISSION_VERSION,
    )


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
