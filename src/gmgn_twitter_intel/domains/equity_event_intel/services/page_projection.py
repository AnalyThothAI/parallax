from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import (
    EQUITY_EVENT_ALERT_PROJECTION_VERSION,
    EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
    EQUITY_EVENT_PAGE_PROJECTION_VERSION,
    EQUITY_EVENT_TIMELINE_PROJECTION_VERSION,
)

_OFFICIAL_SOURCE_ROLES = frozenset({"official_regulator", "official_issuer"})
_ACTIONABLE_FACT_STATUSES = frozenset({"accepted", "attention"})
_EARNINGS_EVENT_FAMILY = frozenset({"earnings_release", "quarterly_report"})


def build_equity_event_page_row(
    *,
    event: Mapping[str, Any],
    company: Mapping[str, Any] | None,
    story: Mapping[str, Any] | None,
    facts: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    brief: Mapping[str, Any] | None,
    computed_at_ms: int,
) -> dict[str, Any]:
    company_event_id = str(event["company_event_id"])
    ticker = str(event.get("ticker") or (company or {}).get("ticker") or "").upper()
    company_name = str((company or {}).get("company_name") or "")
    fiscal_period = _optional_str(event.get("fiscal_period"))
    event_type = str(event["event_type"])
    return _with_payload_hash(
        {
            "row_id": _stable_id("equity-event-page-row", EQUITY_EVENT_PAGE_PROJECTION_VERSION, company_event_id),
            "company_event_id": company_event_id,
            "story_id": _optional_str((story or {}).get("story_id")),
            "company_id": str(event["company_id"]),
            "ticker": ticker,
            "company_name": company_name,
            "event_type": event_type,
            "priority": str(event["priority"]),
            "source_role": str(event["source_role"]),
            "latest_event_at_ms": int(event.get("event_time_ms") or computed_at_ms),
            "lifecycle_status": str(event.get("lifecycle_status") or "raw"),
            "evidence_status": str(event.get("evidence_status") or "pending"),
            "evidence_reason": str(event.get("evidence_reason") or ""),
            "fact_extraction_status": _document_fact_status(documents, "fact_extraction_status", "pending"),
            "fact_extraction_reason": _document_fact_status(documents, "fact_extraction_reason", ""),
            "headline": _event_headline(ticker=ticker, fiscal_period=fiscal_period, event_type=event_type),
            "summary": str(event.get("summary") or ""),
            "facts_json": [_fact_payload(row) for row in facts],
            "documents_json": [_document_payload(row) for row in documents],
            "brief_json": _brief_payload(brief),
            "freshness_json": _freshness_payload(
                event=event,
                documents=documents,
                brief=brief,
                computed_at_ms=computed_at_ms,
            ),
            "computed_at_ms": int(computed_at_ms),
            "source_watermark_ms": _source_watermark(event, computed_at_ms=computed_at_ms),
            "projection_version": EQUITY_EVENT_PAGE_PROJECTION_VERSION,
        }
    )


def build_equity_event_calendar_row(
    *,
    expected_event: Mapping[str, Any],
    observed_event: Mapping[str, Any] | None,
    company: Mapping[str, Any] | None,
    now_ms: int,
    computed_at_ms: int,
) -> dict[str, Any]:
    expected_event_id = str(expected_event["expected_event_id"])
    ticker = str(expected_event.get("ticker") or (company or {}).get("ticker") or "").upper()
    event_type = str(expected_event["event_type"])
    fiscal_period = _optional_str(expected_event.get("fiscal_period"))
    status = _calendar_status(expected_event=expected_event, observed_event=observed_event, now_ms=now_ms)
    return _with_payload_hash(
        {
            "row_id": _stable_id(
                "equity-event-calendar-row", EQUITY_EVENT_CALENDAR_PROJECTION_VERSION, expected_event_id
            ),
            "expected_event_id": expected_event_id,
            "company_id": str(expected_event["company_id"]),
            "ticker": ticker,
            "company_name": str((company or {}).get("company_name") or ""),
            "event_type": event_type,
            "priority": str((company or {}).get("priority") or "P2"),
            "source_role": str(expected_event["source_role"]),
            "fiscal_period": fiscal_period,
            "expected_at_ms": int(expected_event["expected_at_ms"]),
            "status": status,
            "headline": _calendar_headline(
                ticker=ticker,
                fiscal_period=fiscal_period,
                event_type=event_type,
                status=status,
            ),
            "calendar_json": {
                "source_id": expected_event.get("source_id"),
                "expected_status": expected_event.get("status"),
                "observed_company_event_id": (observed_event or {}).get("company_event_id"),
                "observed_event_type": (observed_event or {}).get("event_type"),
                "observed_event_time_ms": _optional_int((observed_event or {}).get("event_time_ms")),
            },
            "computed_at_ms": int(computed_at_ms),
            "source_watermark_ms": _source_watermark(expected_event, computed_at_ms=computed_at_ms),
            "projection_version": EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
        }
    )


def build_equity_event_alert_candidate(
    *,
    event: Mapping[str, Any],
    page_row: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    computed_at_ms: int,
) -> dict[str, Any] | None:
    if str(event.get("priority") or page_row.get("priority")) != "P0":
        return None
    if str(event.get("source_role") or page_row.get("source_role")) not in _OFFICIAL_SOURCE_ROLES:
        return None
    actionable_facts = [
        dict(fact) for fact in facts if str(fact.get("validation_status") or "") in _ACTIONABLE_FACT_STATUSES
    ]
    if not actionable_facts:
        return None

    company_event_id = str(event["company_event_id"])
    validation_status = str(event.get("validation_status") or "pending")
    return _with_payload_hash(
        {
            "alert_candidate_id": _stable_id(
                "equity-event-alert-candidate",
                EQUITY_EVENT_ALERT_PROJECTION_VERSION,
                company_event_id,
            ),
            "company_event_id": company_event_id,
            "company_id": str(event["company_id"]),
            "ticker": str(event.get("ticker") or page_row.get("ticker") or "").upper(),
            "event_type": str(event["event_type"]),
            "priority": str(event["priority"]),
            "lifecycle_status": str(event.get("lifecycle_status") or page_row.get("lifecycle_status") or "raw"),
            "validation_status": validation_status,
            "alert_status": "pending",
            "reason_codes_json": ["official_p0_event", "actionable_fact"],
            "payload_json": {
                "headline": page_row.get("headline"),
                "summary": page_row.get("summary"),
                "facts": actionable_facts[:5],
                "brief": _json_object(page_row.get("brief_json")),
            },
            "computed_at_ms": int(computed_at_ms),
            "source_watermark_ms": int(page_row.get("source_watermark_ms") or computed_at_ms),
            "projection_version": EQUITY_EVENT_ALERT_PROJECTION_VERSION,
        }
    )


def build_equity_company_timeline_row(*, page_row: Mapping[str, Any], computed_at_ms: int) -> dict[str, Any]:
    company_event_id = str(page_row["company_event_id"])
    return _with_payload_hash(
        {
            "row_id": _stable_id(
                "equity-company-timeline-row", EQUITY_EVENT_TIMELINE_PROJECTION_VERSION, company_event_id
            ),
            "company_id": str(page_row["company_id"]),
            "ticker": str(page_row["ticker"]).upper(),
            "company_event_id": company_event_id,
            "story_id": _optional_str(page_row.get("story_id")),
            "event_type": str(page_row["event_type"]),
            "priority": str(page_row["priority"]),
            "source_role": str(page_row["source_role"]),
            "event_time_ms": int(page_row["latest_event_at_ms"]),
            "lifecycle_status": str(page_row["lifecycle_status"]),
            "headline": str(page_row["headline"]),
            "summary": str(page_row.get("summary") or ""),
            "payload_json": {
                "company_name": page_row.get("company_name") or "",
                "facts": [_timeline_fact_payload(fact) for fact in _json_list(page_row.get("facts_json"))[:8]],
                "documents": _json_list(page_row.get("documents_json"))[:5],
                "brief": _json_object(page_row.get("brief_json")),
            },
            "computed_at_ms": int(computed_at_ms),
            "source_watermark_ms": int(page_row.get("source_watermark_ms") or computed_at_ms),
            "projection_version": EQUITY_EVENT_TIMELINE_PROJECTION_VERSION,
        }
    )


def event_matches_expected_calendar(*, expected_event: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    if str(expected_event.get("ticker") or "").upper() != str(event.get("ticker") or "").upper():
        return False
    expected_period = _optional_str(expected_event.get("fiscal_period"))
    event_period = _optional_str(event.get("fiscal_period"))
    if expected_period is not None and event_period is not None and expected_period != event_period:
        return False
    return _event_family(str(expected_event.get("event_type") or "")) == _event_family(
        str(event.get("event_type") or "")
    )


def _calendar_status(
    *,
    expected_event: Mapping[str, Any],
    observed_event: Mapping[str, Any] | None,
    now_ms: int,
) -> str:
    if observed_event is not None and event_matches_expected_calendar(
        expected_event=expected_event,
        event=observed_event,
    ):
        return "matched"
    if int(expected_event["expected_at_ms"]) < int(now_ms):
        return "missed"
    return "expected"


def _event_headline(*, ticker: str, fiscal_period: str | None, event_type: str) -> str:
    parts = [ticker]
    if fiscal_period:
        parts.append(fiscal_period)
    parts.append(event_type.replace("_", " "))
    return " ".join(part for part in parts if part).strip()


def _calendar_headline(*, ticker: str, fiscal_period: str | None, event_type: str, status: str) -> str:
    event_label = event_type.replace("_", " ")
    period_prefix = f" {fiscal_period}" if fiscal_period else ""
    if status == "matched":
        return f"{ticker}{period_prefix} {event_label} matched".strip()
    if status == "missed":
        return f"{ticker} missed{period_prefix} {event_label}".strip()
    return f"{ticker} expected{period_prefix} {event_label}".strip()


def _fact_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return _compact_mapping(
        {
            "fact_candidate_id": row.get("fact_candidate_id"),
            "fact_type": row.get("fact_type"),
            "metric_name": row.get("metric_name"),
            "value_numeric": row.get("value_numeric"),
            "value_unit": row.get("value_unit"),
            "period": row.get("period"),
            "direction": row.get("direction"),
            "claim": row.get("claim"),
            "evidence_quote": row.get("evidence_quote"),
            "source_role": row.get("source_role"),
            "validation_status": row.get("validation_status"),
            "rejection_reasons": _json_list(row.get("rejection_reasons_json") or row.get("rejection_reasons")),
        }
    )


def _document_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return _compact_mapping(
        {
            "event_document_id": row.get("event_document_id"),
            "document_type": row.get("document_type"),
            "form_type": row.get("form_type"),
            "accession_number": row.get("accession_number"),
            "fiscal_period": row.get("fiscal_period"),
            "document_url": row.get("document_url"),
            "event_time_ms": _optional_int(row.get("event_time_ms")),
            "source_role": row.get("source_role"),
            "source_id": row.get("source_id"),
            "evidence_status": row.get("evidence_status"),
            "evidence_reason": row.get("evidence_reason"),
            "fact_extraction_status": row.get("fact_extraction_status"),
            "fact_extraction_reason": row.get("fact_extraction_reason"),
        }
    )


def _timeline_fact_payload(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return {}
    return {str(key): item for key, item in row.items() if item not in (None, [], {})}


def _brief_payload(brief: Mapping[str, Any] | None) -> dict[str, Any]:
    if brief is None:
        return {"status": "pending_due", "reason_code": "brief_state_missing"}
    payload = _json_object(brief.get("brief_json") if isinstance(brief, Mapping) else None)
    status = (
        brief.get("brief_readiness_status") or brief.get("readiness_status") or brief.get("status")
        if isinstance(brief, Mapping)
        else None
    )
    if status:
        payload["status"] = status
    if isinstance(brief, Mapping):
        for key in ("reason_code", "reason_detail", "next_retry_after_ms", "source_updated_at_ms", "updated_at_ms"):
            value = brief.get(key)
            if value is not None:
                payload[key] = value
        if brief.get("status") and "agent_status" not in payload:
            payload["agent_status"] = brief.get("status")
    return payload or {"status": "pending_due", "reason_code": "brief_state_missing"}


def _document_fact_status(documents: Sequence[Mapping[str, Any]], key: str, fallback: str) -> str:
    for row in documents:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return fallback


def _freshness_payload(
    *,
    event: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
    brief: Mapping[str, Any] | None,
    computed_at_ms: int,
) -> dict[str, Any]:
    document_updated_at_ms = max((_optional_int(row.get("updated_at_ms")) or 0 for row in documents), default=0)
    evidence_ready_at_ms = max((_optional_int(row.get("evidence_ready_at_ms")) or 0 for row in documents), default=0)
    fact_extracted_at_ms = max((_optional_int(row.get("fact_extracted_at_ms")) or 0 for row in documents), default=0)
    brief_updated_at_ms = _optional_int((brief or {}).get("updated_at_ms") if isinstance(brief, Mapping) else None)
    return _compact_mapping(
        {
            "material_event_at_ms": _optional_int(event.get("event_time_ms")),
            "document_updated_at_ms": document_updated_at_ms or None,
            "evidence_ready_at_ms": evidence_ready_at_ms or None,
            "fact_extracted_at_ms": fact_extracted_at_ms or None,
            "brief_updated_at_ms": brief_updated_at_ms,
            "projection_at_ms": int(computed_at_ms),
        }
    )


def _event_family(event_type: str) -> str:
    if event_type in _EARNINGS_EVENT_FAMILY:
        return "earnings"
    return event_type


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item is not None}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _with_payload_hash(row: dict[str, Any]) -> dict[str, Any]:
    row["payload_hash"] = _payload_hash(row)
    return row


def _payload_hash(row: Mapping[str, Any]) -> str:
    payload = {
        str(key): _hash_value(key=str(key), value=value)
        for key, value in row.items()
        if key not in {"computed_at_ms", "payload_hash", "source_watermark_ms", "freshness_json"}
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash_value(*, key: str, value: Any) -> Any:
    if key != "freshness_json" or not isinstance(value, Mapping):
        return value
    return {str(child_key): child for child_key, child in value.items() if str(child_key) != "projection_at_ms"}


def _source_watermark(row: Mapping[str, Any], *, computed_at_ms: int) -> int:
    return int(row.get("source_watermark_ms") or computed_at_ms)


__all__ = [
    "build_equity_company_timeline_row",
    "build_equity_event_alert_candidate",
    "build_equity_event_calendar_row",
    "build_equity_event_page_row",
    "event_matches_expected_calendar",
]
