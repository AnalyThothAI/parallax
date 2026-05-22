from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_FACT_POLICY_VERSION
from gmgn_twitter_intel.domains.equity_event_intel.types import EquityFactCandidate, EquitySourceSpan

_OFFICIAL_SOURCE_ROLES = frozenset({"official_regulator", "official_issuer"})
_REVENUE_VALUE_RE = r"(?P<value>(?:\$\s*)?-?\d+(?:\.\d+)?\s*(?:billion|million|bn|m)|\$\s*-?\d+(?:\.\d+)?)"
_REVENUE_RE = re.compile(
    rf"\b(?:total\s+)?revenue(?:s)?\b[^.\n]{{0,80}}?{_REVENUE_VALUE_RE}",
    re.IGNORECASE,
)
_EPS_RE = re.compile(
    r"\b(?:diluted\s+)?(?:earnings\s+per\s+share|eps)\b[^.\n]{0,80}?(?P<value>-?\$?\d+(?:\.\d+)?|\$-?\d+(?:\.\d+)?)",
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
    company_id: str,
    ticker: str,
    event_type: str,
    period: str | None,
    source_role: str,
    title: str = "",
    body_text: str = "",
    now_ms: int,
) -> list[EquityFactCandidate]:
    text = " ".join(part.strip() for part in (title, body_text) if part and part.strip()).strip()
    if not text:
        return []

    candidates: list[EquityFactCandidate] = []
    for fact_type, metric_name, pattern in (
        ("revenue_actual", "revenue", _REVENUE_RE),
        ("eps_actual", "eps", _EPS_RE),
    ):
        match = pattern.search(text)
        if match is None:
            continue
        value = match.group("value").strip()
        value_numeric, value_unit = _typed_value(metric_name=metric_name, value=value)
        required_slots = _required_slots(
            metric_name=metric_name,
            value_numeric=value_numeric,
            value_unit=value_unit,
            period=period,
        )
        validation_status, rejection_reasons = _validation(source_role=source_role, required_slots=required_slots)
        candidates.append(
            EquityFactCandidate(
                fact_candidate_id=_stable_id("equity-fact", company_event_id, event_document_id, fact_type, value),
                company_event_id=company_event_id,
                event_document_id=event_document_id,
                source_span_id=source_span_id,
                company_id=company_id,
                ticker=ticker.upper(),
                event_type=event_type,
                fact_type=fact_type,
                metric_name=metric_name,
                value_numeric=value_numeric,
                value_unit=value_unit,
                period=period,
                direction="actual",
                required_slots_json=required_slots,
                claim=f"{fact_type}: {value}",
                evidence_quote=_evidence_quote(text, start=match.start(), end=match.end()),
                evidence_span_start=match.start(),
                evidence_span_end=match.end(),
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


def _typed_value(*, metric_name: str, value: str) -> tuple[float | None, str]:
    unit = "USD_per_share" if metric_name == "eps" else _revenue_unit(value)
    numeric_text = value.replace("$", "").replace(",", "").strip().casefold()
    numeric_text = re.sub(r"\s*(billion|million|bn|m)\s*$", "", numeric_text)
    try:
        return float(numeric_text), unit
    except ValueError:
        return None, unit


def _revenue_unit(value: str) -> str:
    normalized = value.casefold()
    if "billion" in normalized or re.search(r"\bbn\b", normalized):
        return "USD_billion"
    if "million" in normalized or re.search(r"\bm\b", normalized):
        return "USD_million"
    return "USD"


def _required_slots(
    *,
    metric_name: str,
    value_numeric: float | None,
    value_unit: str,
    period: str | None,
) -> dict[str, bool]:
    return {
        "metric_name": bool(metric_name),
        "value_numeric": value_numeric is not None,
        "value_unit": bool(value_unit),
        "period": bool(period),
    }


def _validation(*, source_role: str, required_slots: dict[str, bool]) -> tuple[str, list[str]]:
    reasons = [f"missing_slot:{slot}" for slot, present in required_slots.items() if not present]
    if source_role in _OFFICIAL_SOURCE_ROLES:
        return ("attention", reasons) if reasons else ("accepted", [])
    reasons.append("source_not_authoritative_for_acceptance")
    return "attention", reasons


def _evidence_quote(text: str, *, start: int, end: int) -> str:
    return text[max(0, start - 80) : min(len(text), end + 160)].strip()[:240]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
