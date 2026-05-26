from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, cast

from gmgn_twitter_intel.domains.equity_event_intel.types import EquityCompanyEvent, Priority, SourceRole

_EARNINGS_8K_TEXT = (
    "results of operations and financial condition",
    "earnings release",
    "quarterly results",
    "financial results",
)


def classify_equity_event(document: Mapping[str, Any]) -> EquityCompanyEvent:
    form_type = _text(document.get("form_type")).upper()
    event_type, priority = _event_type_and_priority(form_type=form_type, title=_document_title(document))
    summary = _summary(document=document, event_type=event_type)
    return EquityCompanyEvent(
        company_event_id=_company_event_id(document=document, event_type=event_type),
        company_id=_required_text(document, "company_id"),
        ticker=_required_text(document, "ticker").upper(),
        primary_document_id=_required_text(document, "event_document_id"),
        event_type=event_type,
        priority=priority,
        source_role=cast(SourceRole, _text(document.get("source_role")) or "observed_source"),
        fiscal_period=_optional_text(document.get("fiscal_period")),
        event_time_ms=_int_or(document.get("event_time_ms"), 0),
        discovered_at_ms=_int_or(document.get("discovered_at_ms"), _int_or(document.get("event_time_ms"), 0)),
        lifecycle_status="raw",
        validation_status="pending",
        summary=summary,
    )


def _event_type_and_priority(*, form_type: str, title: str) -> tuple[str, Priority]:
    if form_type in {"10-Q", "10-Q/A"}:
        return "quarterly_report", "P0"
    if form_type in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
        return "annual_report", "P0"
    if form_type == "8-K" and any(needle in title.casefold() for needle in _EARNINGS_8K_TEXT):
        return "earnings_release", "P0"
    if form_type in {"8-K", "6-K"}:
        return "current_report", "P1"
    return "company_update", "P2"


def _company_event_id(*, document: Mapping[str, Any], event_type: str) -> str:
    seed = "|".join(
        (
            _required_text(document, "company_id"),
            event_type,
            _text(document.get("fiscal_period")),
            _text(document.get("accession_number")),
            _required_text(document, "event_document_id"),
        )
    )
    return "equity-event-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _document_title(document: Mapping[str, Any]) -> str:
    raw_payload = document.get("raw_payload_json")
    if isinstance(raw_payload, Mapping):
        for key in ("title", "description", "primary_document"):
            value = _text(raw_payload.get(key))
            if value:
                return value
    return _text(document.get("title"))


def _summary(*, document: Mapping[str, Any], event_type: str) -> str:
    title = _document_title(document)
    if title:
        return title[:240]
    ticker = _required_text(document, "ticker").upper()
    fiscal_period = _optional_text(document.get("fiscal_period"))
    if fiscal_period:
        return f"{ticker} {event_type.replace('_', ' ')} {fiscal_period}"
    form_type = _optional_text(document.get("form_type"))
    return f"{ticker} {form_type or event_type}".strip()


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = _text(document.get(key))
    if not value:
        raise ValueError(f"equity event document missing {key}")
    return value


def _optional_text(value: Any) -> str | None:
    normalized = _text(value)
    return normalized or None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)
