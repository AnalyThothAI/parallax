from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_FACT_POLICY_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_token_mentions import NewsTokenMention

_EVENT_PATTERNS = (
    ("listing", re.compile(r"\b(?:lists?|listing|goes live|launches trading)\b", re.IGNORECASE)),
    ("delisting", re.compile(r"\b(?:delists?|delisting|suspend trading)\b", re.IGNORECASE)),
    ("hack", re.compile(r"\b(?:hack|hacked|exploit|exploited|drained)\b", re.IGNORECASE)),
    (
        "regulatory",
        re.compile(r"\b(?:sec|cftc|regulator|court|lawsuit|settlement|approval|approved)\b", re.IGNORECASE),
    ),
    ("etf", re.compile(r"\bETF\b|\bexchange-traded fund\b", re.IGNORECASE)),
    ("fund_flow", re.compile(r"\b(?:inflow|outflow|net flow|whale|accumulat)\b", re.IGNORECASE)),
    ("unlock", re.compile(r"\bunlock\b", re.IGNORECASE)),
    ("protocol_upgrade", re.compile(r"\b(?:upgrade|mainnet|hard fork)\b", re.IGNORECASE)),
)
_ACCEPTING_SOURCE_ROLES = frozenset(
    {"official_exchange", "official_regulator", "official_protocol", "official_issuer"}
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
        required_slots = _required_slots(event_type=event_type, targets=targets, text=text)
        rejection_reasons = _rejection_reasons(
            targets=targets,
            required_slots=required_slots,
            realis="reported_claim",
            source_role=source_role,
        )
        candidates.append(
            NewsFactCandidate(
                fact_candidate_id=_stable_id("news-fact", news_item_id, event_type, str(match.start())),
                news_item_id=news_item_id,
                event_type=event_type,
                claim=(title or text)[:240],
                realis="reported_claim",
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
    return candidates[:3]


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
    if event_type in {"listing", "delisting"}:
        return {
            "asset": has_production_target,
            "venue": bool(re.search(r"\b(?:coinbase|binance|kraken|okx|bybit)\b", text, re.IGNORECASE)),
        }
    if event_type == "hack":
        return {"asset_or_protocol": has_production_target, "incident": True}
    if event_type == "regulatory":
        return {
            "actor": bool(re.search(r"\b(?:sec|cftc|court|regulator|treasury)\b", text, re.IGNORECASE)),
            "action": True,
        }
    return {"asset": has_production_target}


def _rejection_reasons(
    *,
    targets: list[dict[str, object]],
    required_slots: dict[str, bool],
    realis: str,
    source_role: str,
) -> list[str]:
    reasons: list[str] = []
    if not any(bool(target.get("production_eligible")) for target in targets):
        reasons.append("target_identity_not_production_eligible")
    for slot, present in required_slots.items():
        if not present:
            reasons.append(f"missing_slot:{slot}")
    if realis not in {"actual", "scheduled", "official_proposed", "reported_claim"}:
        reasons.append("non_actionable_realis")
    if source_role not in _ACCEPTING_SOURCE_ROLES:
        reasons.append("source_not_authoritative_for_acceptance")
    return reasons


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
