from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_FACT_POLICY_VERSION
from gmgn_twitter_intel.domains.equity_event_intel.types import EquityFactCandidate, EquitySourceSpan

_OFFICIAL_SOURCE_ROLES = frozenset({"official_regulator", "official_issuer"})
_MONEY_RE = r"\$?\d+(?:\.\d+)?\s*(?:billion|million|bn|m)?"
_REVENUE_RE = re.compile(
    rf"\b(?:total\s+)?revenue(?:s)?\b[^.\n]{{0,80}}?(?P<value>{_MONEY_RE})",
    re.IGNORECASE,
)
_EPS_RE = re.compile(
    r"\b(?:diluted\s+)?(?:earnings\s+per\s+share|eps)\b[^.\n]{0,80}?(?P<value>\$?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def build_source_spans(
    *,
    company_event_id: str,
    event_document_id: str,
    source_id: str | None,
    text: str,
    now_ms: int,
) -> list[EquitySourceSpan]:
    normalized_text = text.strip()
    if not normalized_text:
        return []
    return [
        EquitySourceSpan(
            span_id=_stable_id("equity-source-span", company_event_id, event_document_id, normalized_text[:200]),
            company_event_id=company_event_id,
            event_document_id=event_document_id,
            source_id=source_id,
            span_type="document_text",
            section_key="body",
            span_start=0,
            span_end=len(normalized_text),
            evidence_quote=normalized_text[:500],
            confidence=1.0,
            created_at_ms=int(now_ms),
        )
    ]


def build_fact_candidates(
    *,
    company_event_id: str,
    event_document_id: str,
    source_span_id: str,
    source_role: str,
    title: str = "",
    body_text: str = "",
    now_ms: int,
) -> list[EquityFactCandidate]:
    text = " ".join(part.strip() for part in (title, body_text) if part and part.strip()).strip()
    if not text:
        return []

    candidates: list[EquityFactCandidate] = []
    for fact_type, pattern in (("revenue_actual", _REVENUE_RE), ("eps_actual", _EPS_RE)):
        match = pattern.search(text)
        if match is None:
            continue
        value = match.group("value").strip()
        validation_status, rejection_reasons = _validation(source_role)
        candidates.append(
            EquityFactCandidate(
                fact_candidate_id=_stable_id("equity-fact", company_event_id, event_document_id, fact_type, value),
                company_event_id=company_event_id,
                event_document_id=event_document_id,
                source_span_id=source_span_id,
                fact_type=fact_type,
                claim=f"{fact_type}: {value}",
                evidence_quote=_evidence_quote(text, start=match.start(), end=match.end()),
                source_role=source_role,
                validation_status=validation_status,
                rejection_reasons_json=rejection_reasons,
                extraction_method="deterministic_rules_v1",
                policy_version=EQUITY_EVENT_FACT_POLICY_VERSION,
                created_at_ms=int(now_ms),
                updated_at_ms=int(now_ms),
            )
        )
    return candidates


def document_text(document: Mapping[str, Any]) -> str:
    raw_payload = document.get("raw_payload_json")
    parts: list[str] = []
    if isinstance(raw_payload, Mapping):
        for key in ("title", "description", "summary", "body_text", "press_release_text", "text"):
            value = str(raw_payload.get(key) or "").strip()
            if value:
                parts.append(value)
    return " ".join(parts).strip()


def _validation(source_role: str) -> tuple[str, list[str]]:
    if source_role in _OFFICIAL_SOURCE_ROLES:
        return "accepted", []
    return "attention", ["source_not_authoritative_for_acceptance"]


def _evidence_quote(text: str, *, start: int, end: int) -> str:
    return text[max(0, start - 80) : min(len(text), end + 160)].strip()[:240]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
