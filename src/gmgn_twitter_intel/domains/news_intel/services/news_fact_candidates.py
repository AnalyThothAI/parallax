from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_FACT_POLICY_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_token_mentions import NewsTokenMention
from gmgn_twitter_intel.domains.news_intel.services.source_authority import validate_source_authority

_EVENT_PATTERNS = (
    ("exchange_listing", re.compile(r"\b(?:lists?|listing|goes live|launches trading)\b", re.IGNORECASE)),
    ("exchange_delisting", re.compile(r"\b(?:delists?|delisting|suspend trading)\b", re.IGNORECASE)),
    ("security_incident", re.compile(r"\b(?:hack|hacked|exploit|exploited|drained)\b", re.IGNORECASE)),
    (
        "etf_fund_flow",
        re.compile(r"\bETF\b|\bexchange-traded fund\b|\b(?:inflow|outflow|net flow)\b", re.IGNORECASE),
    ),
    (
        "regulatory_action",
        re.compile(r"\b(?:sec|cftc|regulator|court|lawsuit|settlement|approval|approved)\b", re.IGNORECASE),
    ),
    ("governance_tokenomics", re.compile(r"\b(?:unlock|governance|proposal)\b", re.IGNORECASE)),
    ("protocol_upgrade", re.compile(r"\b(?:upgrade|mainnet|hard fork)\b", re.IGNORECASE)),
)
_PRODUCTION_TARGET_TYPES = frozenset({"Asset", "CexToken"})
_PRODUCTION_RESOLUTION_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})


@dataclass(frozen=True, slots=True)
class NewsFactCandidate:
    fact_candidate_id: str
    news_item_id: str
    event_type: str
    claim: str
    realis: str
    evidence_quote: str
    evidence_span_start: int
    evidence_span_end: int
    source_role: str
    required_slots: dict[str, bool]
    affected_targets: list[dict[str, object]]
    validation_status: str
    rejection_reasons: list[str]
    extraction_method: str
    policy_version: str
    created_at_ms: int
    updated_at_ms: int


def build_fact_candidates(
    *,
    news_item_id: str,
    source_role: str,
    source_domain: str = "",
    authority_scope: Mapping[str, Any] | None = None,
    title: str,
    summary: str,
    body_text: str,
    token_mentions: list[NewsTokenMention],
    now_ms: int,
) -> list[NewsFactCandidate]:
    text = " ".join(part for part in (title, summary, body_text) if part).strip()
    if not text:
        return []

    candidates: list[NewsFactCandidate] = []
    for event_type, pattern in _EVENT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        targets = _affected_targets(token_mentions)
        realis = _realis_for_match(text, event_type=event_type)
        required_slots = _required_slots(event_type=event_type, targets=targets, text=text)
        authority = validate_source_authority(
            source_role=source_role,
            authority_scope=authority_scope or {},
            event_type=event_type,
            source_domain=source_domain,
            affected_targets=targets,
            realis=realis,
        )
        rejection_reasons = _rejection_reasons(
            required_slots=required_slots,
            authority_reasons=authority.rejection_reasons,
        )
        candidates.append(
            NewsFactCandidate(
                fact_candidate_id=_stable_id("news-fact", news_item_id, event_type, str(match.start())),
                news_item_id=news_item_id,
                event_type=event_type,
                claim=(title or text)[:240],
                realis=realis,
                evidence_quote=_evidence_quote(text, start=match.start(), end=match.end()),
                evidence_span_start=max(0, match.start() - 80),
                evidence_span_end=min(len(text), match.end() + 160),
                source_role=source_role,
                required_slots=required_slots,
                affected_targets=targets,
                validation_status="accepted" if not rejection_reasons else "attention",
                rejection_reasons=rejection_reasons,
                extraction_method="deterministic_rules_v1",
                policy_version=NEWS_FACT_POLICY_VERSION,
                created_at_ms=int(now_ms),
                updated_at_ms=int(now_ms),
            )
        )
    return _suppress_redundant_attention_candidates(candidates)[:3]


def _affected_targets(mentions: list[NewsTokenMention]) -> list[dict[str, object]]:
    return [
        {
            "resolution_status": mention.resolution_status,
            "target_type": mention.target_type,
            "target_id": mention.target_id,
            "display_symbol": mention.display_symbol or mention.observed_symbol,
            "evidence_strength": mention.evidence_strength,
            "production_eligible": _is_production_eligible_mention(mention),
        }
        for mention in mentions
    ]


def _required_slots(*, event_type: str, targets: list[dict[str, object]], text: str) -> dict[str, bool]:
    has_production_target = any(bool(target.get("production_eligible")) for target in targets)
    if event_type in {"exchange_listing", "exchange_delisting"}:
        return {
            "asset": has_production_target,
            "venue": bool(re.search(r"\b(?:coinbase|binance|kraken|okx|bybit)\b", text, re.IGNORECASE)),
        }
    if event_type == "security_incident":
        return {"asset_or_protocol": has_production_target, "incident": True}
    if event_type == "regulatory_action":
        return {
            "actor": bool(re.search(r"\b(?:sec|cftc|court|regulator|treasury)\b", text, re.IGNORECASE)),
            "action": True,
        }
    return {"asset": has_production_target}


def _rejection_reasons(
    *,
    required_slots: dict[str, bool],
    authority_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    for slot, present in required_slots.items():
        if not present:
            reasons.append(f"missing_slot:{slot}")
    for reason in authority_reasons:
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _suppress_redundant_attention_candidates(candidates: list[NewsFactCandidate]) -> list[NewsFactCandidate]:
    accepted_event_types = {
        candidate.event_type for candidate in candidates if candidate.validation_status == "accepted"
    }
    if not accepted_event_types:
        return candidates
    suppressed_attention_types: set[str] = set()
    if "etf_fund_flow" in accepted_event_types:
        suppressed_attention_types.add("regulatory_action")
    if "regulatory_action" in accepted_event_types:
        suppressed_attention_types.add("etf_fund_flow")
    if not suppressed_attention_types:
        return candidates
    return [
        candidate
        for candidate in candidates
        if candidate.validation_status != "attention" or candidate.event_type not in suppressed_attention_types
    ]


def _realis_for_match(text: str, *, event_type: str) -> str:
    if event_type == "governance_tokenomics" and re.search(r"\b(?:proposal|proposes?|vote)\b", text, re.IGNORECASE):
        return "official_proposed"
    if re.search(r"\b(?:scheduled|will|starts?|begins?|launch(?:es)? on|effective)\b", text, re.IGNORECASE):
        return "scheduled"
    return "actual"


def _is_production_eligible_mention(mention: NewsTokenMention) -> bool:
    return (
        bool(mention.target_id)
        and mention.target_type in _PRODUCTION_TARGET_TYPES
        and mention.resolution_status in _PRODUCTION_RESOLUTION_STATUSES
    )


def _evidence_quote(text: str, *, start: int, end: int) -> str:
    return text[max(0, start - 80) : min(len(text), end + 160)].strip()[:240]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
